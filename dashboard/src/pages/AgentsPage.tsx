import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import AgentCard from '../components/agents/AgentCard';

export default function AgentsPage() {
  const { data: agents } = useQuery({ queryKey: ['agents'], queryFn: api.getAgents, refetchInterval: 3000 });
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-800">Agents</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents?.map((a) => <AgentCard key={a.agent_type} agent={a} />)}
      </div>
    </div>
  );
}
