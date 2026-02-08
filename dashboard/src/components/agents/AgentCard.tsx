import type { Agent } from '../../api/types';
import { Bot, CheckCircle, AlertCircle, Clock, Loader } from 'lucide-react';

const statusConfig: Record<string, { color: string; bg: string; icon: any }> = {
  idle: { color: 'text-green-600', bg: 'bg-green-100', icon: CheckCircle },
  working: { color: 'text-amber-600', bg: 'bg-amber-100', icon: Loader },
  waiting: { color: 'text-blue-600', bg: 'bg-blue-100', icon: Clock },
  error: { color: 'text-red-600', bg: 'bg-red-100', icon: AlertCircle },
  stopped: { color: 'text-gray-400', bg: 'bg-gray-100', icon: Bot },
};

export default function AgentCard({ agent }: { agent: Agent }) {
  const cfg = statusConfig[agent.status] || statusConfig.stopped;
  const Icon = cfg.icon;
  return (
    <div className="bg-white rounded-xl shadow p-5 hover:shadow-lg transition-shadow">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-gray-800">{agent.name}</h3>
        <span className={`flex items-center gap-1 text-xs px-2 py-1 rounded-full ${cfg.bg} ${cfg.color}`}>
          <Icon className="w-3 h-3" /> {agent.status}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center text-sm">
        <div>
          <p className="text-gray-400">Tasks</p>
          <p className="font-bold">{agent.tasks_completed}</p>
        </div>
        <div>
          <p className="text-gray-400">Success</p>
          <p className="font-bold">{agent.success_rate.toFixed(0)}%</p>
        </div>
        <div>
          <p className="text-gray-400">Queue</p>
          <p className="font-bold">{agent.queue_size}</p>
        </div>
      </div>
      {agent.errors.length > 0 && (
        <p className="mt-3 text-xs text-red-500 truncate">{agent.errors[agent.errors.length - 1]}</p>
      )}
    </div>
  );
}
