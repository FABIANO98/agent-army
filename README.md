# Agent Army 🤖

Multi-Agent Lead Generation System for B2B Sales Automation

## Overview

Agent Army is a sophisticated multi-agent system designed to automate B2B lead generation and sales outreach for Swiss SMEs. It uses 8 specialized agents that work together to find prospects, research companies, write personalized emails, and track the sales pipeline.

## Features

- **8 Specialized Agents** working in coordination
- **Async/Await Architecture** for high performance
- **Message Bus System** for inter-agent communication
- **SQLite Database** for persistent storage
- **Real-time Status Display** in the CLI
- **Daily Reports** and pipeline tracking
- **Configurable** via YAML configuration

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Orchestrator                             │
├─────────────────────────────────────────────────────────────────┤
│                         Message Bus                              │
├─────────┬─────────┬─────────┬─────────┬─────────┬─────────┬────┤
│Prospect │Research │ Email   │ Quality │ Email   │Response │... │
│ Finder  │ Manager │ Writer  │ Control │ Sender  │ Monitor │    │
└─────────┴─────────┴─────────┴─────────┴─────────┴─────────┴────┘
                              │
                    ┌─────────┴─────────┐
                    │   SQLite Database  │
                    └───────────────────┘
```

## Agents

### 1. ProspectFinder
Finds new Swiss SME prospects daily by searching for companies with "bad website" signals.

### 2. ResearchManager
Performs deep research on prospects including CEO identification, website analysis, and buying signal detection.

### 3. EmailWriter
Creates highly personalized cold outreach emails using templates and research data.

### 4. QualityControl
Validates email quality including grammar, spam score, personalization level, and call-to-action presence.

### 5. EmailSender
Handles strategic email sending with optimal timing, rate limiting, and tracking.

### 6. ResponseMonitor
Monitors inbox for responses and categorizes them (positive, negative, question, etc.).

### 7. ResponseWriter
Drafts appropriate responses based on the type of reply received.

### 8. DealTracker
Tracks the entire sales pipeline and generates daily reports.

## Installation

### Prerequisites

- Python 3.11+
- Poetry

### Setup

```bash
# Clone the repository
git clone https://github.com/frascati-systems/agent-army.git
cd agent-army

# Install dependencies with Poetry
poetry install

# Create configuration
poetry run agent-army init

# Edit config.yaml with your settings
nano config.yaml
```

## Configuration

Edit `config.yaml` to set up:

- **Email credentials** (SMTP/IMAP for sending/receiving)
- **API keys** (Hunter.io, OpenAI, etc.)
- **Agent settings** (intervals, limits, targets)
- **Database path**
- **Logging settings**

### Required Settings

```yaml
email:
  smtp_username: "your-email@gmail.com"
  smtp_password: "your-app-specific-password"
  from_email: "your-email@gmail.com"

api:
  hunter_api_key: "your-hunter-api-key"  # Optional but recommended
```

## Usage

### Start the System

```bash
# Start all agents
poetry run agent-army start

# Or with custom config
poetry run agent-army start --config /path/to/config.yaml
```

### Monitor Status

```bash
# Show agent status
poetry run agent-army status

# Show daily report
poetry run agent-army report

# View logs
poetry run agent-army logs --follow
```

### Stop the System

```bash
# Graceful shutdown
poetry run agent-army stop

# Or press Ctrl+C in the running terminal
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `start` | Start all agents |
| `stop` | Stop all agents |
| `status` | Show agent status |
| `report` | Show daily report |
| `logs` | View agent logs |
| `init` | Create configuration file |
| `version` | Show version info |

## Database Schema

- **prospects** - Basic company information
- **company_profiles** - Detailed research data
- **emails** - Sent and draft emails
- **responses** - Incoming email responses
- **deals** - Sales pipeline tracking
- **agent_logs** - Agent activity logs

## Message Types

Agents communicate via typed messages:

- `new_prospects` - New prospects found
- `prospect_research_complete` - Research finished
- `email_draft_request` - Request email draft
- `email_quality_check` - Request quality review
- `email_approved` / `email_rejected` - Quality verdict
- `response_received` - New response detected
- `deal_stage_update` - Pipeline update

## Development

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=src/agent_army

# Run specific test file
poetry run pytest tests/test_core.py
```

### Code Quality

```bash
# Format code
poetry run black src tests

# Lint
poetry run ruff check src tests

# Type check
poetry run mypy src
```

## Project Structure

```
agent-army/
├── src/
│   └── agent_army/
│       ├── agents/          # 8 specialized agents
│       ├── core/            # Base classes, message bus, registry
│       ├── db/              # Database models and handlers
│       ├── templates/       # Email templates
│       ├── utils/           # Config, logging utilities
│       ├── orchestrator.py  # Main coordinator
│       └── cli.py           # CLI interface
├── tests/                   # Test suite
├── config/                  # Configuration files
├── pyproject.toml          # Poetry configuration
└── README.md
```

## Target Industries

The system is optimized for Swiss SMEs in:

- Bau (Construction)
- Transport
- Logistik (Logistics)
- Handwerk (Crafts/Trades)
- Gastronomie (Restaurants/Hospitality)

## Email Templates

Included German email templates for:

- Cold outreach (3 variants)
- Follow-ups (2 variants)
- Positive response handling
- Question answering
- Meeting confirmations

## Safety Features

- **Daily email limits** to prevent spam
- **Quality checks** before sending
- **Bounce handling**
- **Unsubscribe management**
- **Graceful shutdown**
- **Automatic retry with exponential backoff**

## Roadmap

- [ ] Web UI dashboard
- [ ] Calendar integration
- [ ] CRM integrations (HubSpot, Salesforce)
- [ ] A/B testing for emails
- [ ] AI-powered email personalization
- [ ] Multi-language support

## License

MIT License - See LICENSE file for details.

## Author

Fabiano Frascati - [Frascati Systems](https://www.frascati-systems.ch)

---

**Note**: This is an automation tool. Please ensure compliance with Swiss data protection laws (DSG/FADP) and anti-spam regulations when using this system for cold outreach.
