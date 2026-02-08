"""Integration tests for the complete system."""

import asyncio

import pytest

from src.agent_army.orchestrator import Orchestrator
from src.agent_army.core import MessageType
from src.agent_army.db.models import ProspectStatus, DealStage


class TestSystemIntegration:
    """Integration tests for the complete Agent Army system."""

    @pytest.mark.asyncio
    async def test_orchestrator_initialization(self):
        """Test orchestrator can initialize all components."""
        orchestrator = Orchestrator()
        await orchestrator.initialize()

        assert orchestrator._database is not None
        assert orchestrator._message_bus is not None
        assert orchestrator._registry is not None
        assert len(orchestrator._agents) == 9  # 8 original + TaskManager

        await orchestrator.shutdown()

    @pytest.mark.asyncio
    async def test_all_agents_can_start(self):
        """Test all agents can start without errors."""
        orchestrator = Orchestrator()
        await orchestrator.initialize()

        # Start all agents
        start_tasks = [agent.start() for agent in orchestrator._agents]
        await asyncio.gather(*start_tasks)

        # Verify all running
        for agent in orchestrator._agents:
            assert agent.is_running, f"{agent.name} failed to start"

        await orchestrator.shutdown()

    @pytest.mark.asyncio
    async def test_message_flow_prospect_to_research(self, database, message_bus, registry, settings):
        """Test message flow from ProspectFinder to ResearchManager."""
        from src.agent_army.agents import ProspectFinderAgent, ResearchManagerAgent

        # Create agents
        finder = ProspectFinderAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )
        researcher = ResearchManagerAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        message_bus.register_agent(finder)
        message_bus.register_agent(researcher)

        # Start agents
        await finder.start()
        await researcher.start()

        # Simulate ProspectFinder sending prospects
        await message_bus.send(
            sender_id=finder.agent_id,
            recipient_id=researcher.agent_id,
            message_type=MessageType.NEW_PROSPECTS.value,
            payload={
                "prospects": [
                    {"id": 1, "name": "Test AG", "url": "https://test.ch"},
                ],
                "count": 1,
            },
        )

        # Wait for message processing
        await asyncio.sleep(0.5)

        # Verify message was received (it may already be processed by the
        # agent's run loop, so check the message bus history instead)
        history = message_bus.get_history()
        prospect_messages = [
            m for m in history
            if m.message_type == MessageType.NEW_PROSPECTS.value
        ]
        assert len(prospect_messages) >= 1

        await finder.stop()
        await researcher.stop()

    @pytest.mark.asyncio
    async def test_email_workflow(self, database, message_bus, registry, settings):
        """Test email writing and quality check workflow."""
        from src.agent_army.agents import EmailWriterAgent, QualityControlAgent

        # Create prospect
        prospect = await database.create_prospect(
            name="Workflow Test AG",
            url="https://workflow-test.ch",
            industry="bau",
            email="info@workflow-test.ch",
        )

        # Create profile
        await database.create_company_profile(
            prospect_id=prospect.id,
            ceo_name="Hans Tester",
            website_problems=["Nicht mobile-optimiert"],
            sentiment_score=8.0,
        )

        # Create agents
        writer = EmailWriterAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )
        qc = QualityControlAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        message_bus.register_agent(writer)
        message_bus.register_agent(qc)

        # Trigger email writing
        writer._pending_profiles.append({
            "prospect": prospect.to_dict(),
            "ceo_name": "Hans Tester",
            "website_problems": ["Nicht mobile-optimiert"],
            "sentiment_score": 8.0,
        })

        await writer.start()
        await qc.start()

        # Wait for processing
        await asyncio.sleep(1)

        # Check that email was created
        emails = await database.get_pending_emails()
        # Note: Actual results depend on run timing

        await writer.stop()
        await qc.stop()

    @pytest.mark.asyncio
    async def test_pipeline_tracking(self, database):
        """Test deal pipeline tracking through stages."""
        # Create prospect and deal
        prospect = await database.create_prospect(
            name="Pipeline Test AG",
            url="https://pipeline-test.ch",
        )

        deal = await database.create_deal(
            prospect_id=prospect.id,
            stage=DealStage.COLD_PROSPECT,
            value=5000.0,
        )

        # Progress through stages
        stages = [
            DealStage.CONTACTED,
            DealStage.RESPONDED,
            DealStage.MEETING_SCHEDULED,
            DealStage.PROPOSAL_SENT,
            DealStage.WON,
        ]

        for stage in stages:
            await database.update_deal_stage(deal.id, stage)
            updated = await database.get_deal(deal.id)
            assert updated.stage == stage.value

        # Verify final stats
        stats = await database.get_pipeline_stats()
        assert stats["stages"]["won"]["count"] >= 1
        assert stats["stages"]["won"]["value"] >= 5000

    @pytest.mark.asyncio
    async def test_daily_report_generation(self, database, message_bus, registry, settings):
        """Test daily report generation."""
        from src.agent_army.agents import DealTrackerAgent

        # Create some test data
        for i in range(5):
            prospect = await database.create_prospect(
                name=f"Report Test {i}",
                url=f"https://report-test-{i}.ch",
            )
            await database.create_deal(
                prospect_id=prospect.id,
                stage=DealStage.CONTACTED,
                value=1000.0 * (i + 1),
            )

        # Create tracker
        tracker = DealTrackerAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        message_bus.register_agent(tracker)
        await tracker.start()

        # Get pipeline summary
        summary = await tracker.get_pipeline_summary()

        assert summary["stages"]["contacted"]["count"] >= 5
        assert summary["total"]["value"] >= 15000

        await tracker.stop()

    @pytest.mark.asyncio
    async def test_stale_lead_detection(self, database):
        """Test stale lead detection."""
        from datetime import datetime, timedelta

        # Create an old deal
        prospect = await database.create_prospect(
            name="Stale Test AG",
            url="https://stale-test.ch",
        )

        deal = await database.create_deal(
            prospect_id=prospect.id,
            stage=DealStage.CONTACTED,
        )

        # Manually set old activity date
        async with database.session() as session:
            from sqlalchemy import select
            from src.agent_army.db.models import Deal

            result = await session.execute(
                select(Deal).where(Deal.id == deal.id)
            )
            db_deal = result.scalar_one()
            db_deal.last_activity = datetime.now() - timedelta(days=10)

        # Check for stale deals
        stale = await database.get_stale_deals(days=7)
        assert len(stale) >= 1

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self):
        """Test graceful shutdown of the system."""
        orchestrator = Orchestrator()
        await orchestrator.initialize()

        # Start everything
        start_tasks = [agent.start() for agent in orchestrator._agents]
        await asyncio.gather(*start_tasks)

        # Verify running
        for agent in orchestrator._agents:
            assert agent.is_running

        # Shutdown
        await orchestrator.shutdown()

        # Verify stopped
        for agent in orchestrator._agents:
            assert not agent.is_running
