import { Link } from 'react-router-dom';
import type { Task } from '../../api/types';
import { CheckCircle, Clock, Loader, XCircle, AlertTriangle } from 'lucide-react';

const statusIcons: Record<string, any> = {
  pending: Clock,
  planning: Loader,
  in_progress: Loader,
  completed: CheckCircle,
  failed: XCircle,
};

const statusColors: Record<string, string> = {
  pending: 'text-gray-400',
  planning: 'text-blue-500',
  in_progress: 'text-amber-500',
  completed: 'text-green-500',
  failed: 'text-red-500',
};

export default function TaskListComponent({ tasks }: { tasks?: Task[] }) {
  if (!tasks || tasks.length === 0) return <p className="text-gray-400">No tasks yet.</p>;
  return (
    <div className="space-y-2">
      {tasks.map((t) => {
        const Icon = statusIcons[t.status] || AlertTriangle;
        const color = statusColors[t.status] || 'text-gray-400';
        return (
          <Link
            key={t.id}
            to={`/tasks/${t.id}`}
            className="flex items-center gap-3 bg-white rounded-lg shadow p-4 hover:shadow-md transition-shadow"
          >
            <Icon className={`w-5 h-5 ${color}`} />
            <div className="flex-1">
              <p className="font-medium text-gray-800">{t.title}</p>
              <p className="text-xs text-gray-400">{new Date(t.created_at).toLocaleString()}</p>
            </div>
            {t.status === 'in_progress' && (
              <div className="w-24 bg-gray-200 rounded-full h-2">
                <div className="bg-cyan-500 h-2 rounded-full" style={{ width: `${t.progress_pct}%` }} />
              </div>
            )}
            <span className={`text-xs ${color} capitalize`}>{t.status}</span>
          </Link>
        );
      })}
    </div>
  );
}
