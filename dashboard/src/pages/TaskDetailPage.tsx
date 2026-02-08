import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { CheckCircle, Clock, Loader, XCircle, ArrowLeft, Building2, User, Globe, AlertTriangle, Star } from 'lucide-react';

function ProspectCard({ prospect }: { prospect: any }) {
  return (
    <div className="border rounded-lg p-4 bg-white hover:shadow transition-shadow">
      <div className="flex items-start gap-3">
        <Building2 className="w-5 h-5 text-cyan-500 mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <h4 className="font-semibold text-gray-900 truncate">{prospect.name}</h4>
          {prospect.industry && <span className="text-xs bg-cyan-50 text-cyan-700 px-2 py-0.5 rounded-full">{prospect.industry}</span>}
          {prospect.region && <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full ml-1">{prospect.region}</span>}
          {prospect.url && (
            <div className="mt-1 flex items-center gap-1 text-sm text-blue-600">
              <Globe className="w-3 h-3" />
              <a href={prospect.url} target="_blank" rel="noopener noreferrer" className="hover:underline truncate">{prospect.url}</a>
            </div>
          )}
          {prospect.website_signals && prospect.website_signals.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {prospect.website_signals.map((s: string, i: number) => (
                <span key={i} className="text-xs bg-amber-50 text-amber-700 px-2 py-0.5 rounded-full flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" />{s}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ResearchProfileCard({ profile }: { profile: any }) {
  const prospect = profile.prospect || {};
  return (
    <div className="border rounded-lg p-4 bg-white hover:shadow transition-shadow">
      <div className="flex items-start gap-3">
        <User className="w-5 h-5 text-indigo-500 mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <h4 className="font-semibold text-gray-900">{prospect.name || 'Unbekannt'}</h4>
          {profile.sentiment_score && (
            <div className="flex items-center gap-1 mt-1">
              <Star className="w-4 h-4 text-yellow-500" />
              <span className="text-sm font-medium">{profile.sentiment_score}/10</span>
              <span className="text-xs text-gray-400 ml-1">Score</span>
            </div>
          )}
          {profile.ceo_name && <p className="text-sm text-gray-700 mt-1">CEO: {profile.ceo_name}</p>}
          {profile.employees_count && <p className="text-sm text-gray-500">Mitarbeiter: {profile.employees_count}</p>}
          {profile.budget_estimate && <p className="text-sm text-gray-500">Budget: {profile.budget_estimate}</p>}
          {profile.website_problems && profile.website_problems.length > 0 && (
            <div className="mt-2">
              <p className="text-xs text-gray-400 mb-1">Probleme:</p>
              <div className="flex flex-wrap gap-1">
                {profile.website_problems.map((p: string, i: number) => (
                  <span key={i} className="text-xs bg-red-50 text-red-600 px-2 py-0.5 rounded-full">{p}</span>
                ))}
              </div>
            </div>
          )}
          {profile.buying_signals && profile.buying_signals.length > 0 && (
            <div className="mt-2">
              <p className="text-xs text-gray-400 mb-1">Kaufsignale:</p>
              <div className="flex flex-wrap gap-1">
                {profile.buying_signals.map((s: string, i: number) => (
                  <span key={i} className="text-xs bg-green-50 text-green-600 px-2 py-0.5 rounded-full">{s}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ResultRenderer({ result }: { result: any }) {
  const data = result.data || {};
  const type = data.type || result.result_type;

  if (type === 'prospects' && data.prospects) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-gray-500">{data.count || data.prospects.length} Prospects gefunden</p>
        <div className="grid gap-3 md:grid-cols-2">
          {data.prospects.map((p: any, i: number) => (
            <ProspectCard key={i} prospect={p} />
          ))}
        </div>
      </div>
    );
  }

  if (type === 'research' && data.profiles) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-gray-500">{data.count || data.profiles.length} Profile recherchiert</p>
        <div className="grid gap-3 md:grid-cols-2">
          {data.profiles.map((p: any, i: number) => (
            <ResearchProfileCard key={i} profile={p} />
          ))}
        </div>
      </div>
    );
  }

  // Fallback: raw JSON
  return <pre className="text-xs text-gray-600 mt-1 overflow-auto max-h-40">{JSON.stringify(data, null, 2)}</pre>;
}

export default function TaskDetailPage() {
  const { id } = useParams();
  const { data: task } = useQuery({ queryKey: ['task', id], queryFn: () => api.getTask(Number(id)), refetchInterval: 3000 });

  if (!task) return <p className="text-gray-400">Laden...</p>;

  const statusIcon: Record<string, any> = { pending: Clock, planning: Loader, in_progress: Loader, completed: CheckCircle, failed: XCircle };
  const statusLabel: Record<string, string> = { pending: 'Ausstehend', planning: 'Planung', in_progress: 'In Arbeit', completed: 'Abgeschlossen', failed: 'Fehlgeschlagen' };
  const Icon = statusIcon[task.status] || Clock;

  return (
    <div className="space-y-6">
      <Link to="/tasks" className="flex items-center gap-1 text-cyan-600 hover:underline"><ArrowLeft className="w-4 h-4" /> Zurueck</Link>
      <div className="bg-white rounded-xl shadow p-6">
        <div className="flex items-center gap-3 mb-4">
          <Icon className="w-6 h-6" />
          <h1 className="text-2xl font-bold">{task.title}</h1>
          <span className="ml-auto text-sm text-gray-500">{statusLabel[task.status] || task.status}</span>
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
            {task.subtasks.map((st) => {
              const stIcon = statusIcon[st.status] || Clock;
              const StIcon = stIcon;
              return (
                <div key={st.id} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                  <StIcon className="w-4 h-4 text-gray-400" />
                  <span className="text-xs text-gray-400">#{st.sequence_order}</span>
                  <span className="font-medium flex-1">{st.title}</span>
                  <span className="text-xs text-gray-500">{st.assigned_agent}</span>
                  <span className="text-xs">{statusLabel[st.status] || st.status}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {task.results && task.results.length > 0 && (
        <div className="bg-white rounded-xl shadow p-6">
          <h2 className="font-semibold mb-3">Ergebnisse</h2>
          {task.results.map((r) => (
            <div key={r.id} className="mb-4 p-4 bg-gray-50 rounded-lg">
              <p className="font-medium mb-2">{r.title}</p>
              <ResultRenderer result={r} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
