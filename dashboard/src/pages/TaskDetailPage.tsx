import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { CheckCircle, Clock, Loader, XCircle, ArrowLeft } from 'lucide-react';

export default function TaskDetailPage() {
  const { id } = useParams();
  const { data: task } = useQuery({ queryKey: ['task', id], queryFn: () => api.getTask(Number(id)), refetchInterval: 3000 });

  if (!task) return <p className="text-gray-400">Loading...</p>;

  const statusIcon: Record<string, any> = { pending: Clock, planning: Loader, in_progress: Loader, completed: CheckCircle, failed: XCircle };
  const Icon = statusIcon[task.status] || Clock;

  return (
    <div className="space-y-6">
      <Link to="/tasks" className="flex items-center gap-1 text-cyan-600 hover:underline"><ArrowLeft className="w-4 h-4" /> Back</Link>
      <div className="bg-white rounded-xl shadow p-6">
        <div className="flex items-center gap-3 mb-4">
          <Icon className="w-6 h-6" />
          <h1 className="text-2xl font-bold">{task.title}</h1>
          <span className="ml-auto text-sm capitalize text-gray-500">{task.status}</span>
        </div>
        <p className="text-gray-600 mb-4">{task.description}</p>
        {task.status === 'in_progress' && (
          <div className="w-full bg-gray-200 rounded-full h-3 mb-4">
            <div className="bg-cyan-500 h-3 rounded-full transition-all" style={{ width: `${task.progress_pct}%` }} />
          </div>
        )}
        {task.result_summary && <div className="p-4 bg-green-50 rounded-lg text-green-800 mb-4">{task.result_summary}</div>}
      </div>

      {task.subtasks && task.subtasks.length > 0 && (
        <div className="bg-white rounded-xl shadow p-6">
          <h2 className="font-semibold mb-3">Subtasks</h2>
          <div className="space-y-2">
            {task.subtasks.map((st) => (
              <div key={st.id} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                <span className="text-xs text-gray-400">#{st.sequence_order}</span>
                <span className="font-medium flex-1">{st.title}</span>
                <span className="text-xs text-gray-500">{st.assigned_agent}</span>
                <span className="text-xs capitalize">{st.status}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {task.results && task.results.length > 0 && (
        <div className="bg-white rounded-xl shadow p-6">
          <h2 className="font-semibold mb-3">Results</h2>
          {task.results.map((r) => (
            <div key={r.id} className="mb-3 p-3 bg-gray-50 rounded-lg">
              <p className="font-medium">{r.title}</p>
              <pre className="text-xs text-gray-600 mt-1 overflow-auto max-h-40">{JSON.stringify(r.data, null, 2)}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
