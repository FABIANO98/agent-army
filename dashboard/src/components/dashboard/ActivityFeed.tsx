import { useWebSocket } from '../../hooks/useWebSocket';
import { Clock } from 'lucide-react';

const IGNORED_TYPES = new Set(['heartbeat', 'pong', 'ping', 'health_check', 'health_response']);

const TYPE_LABELS: Record<string, string> = {
  task_created: 'Task erstellt',
  task_assigned: 'Task zugewiesen',
  task_plan_ready: 'Plan bereit',
  task_progress: 'Fortschritt',
  task_subtask_complete: 'Subtask fertig',
  task_completed: 'Task abgeschlossen',
  task_failed: 'Task fehlgeschlagen',
  new_prospects: 'Neue Prospects',
  prospect_research_complete: 'Research fertig',
};

function extractText(msg: any): string {
  const p = msg.payload || {};
  if (p.text) return p.text;
  if (p.summary) return p.summary;
  if (p.title) return p.title;
  if (p.error) return `Fehler: ${p.error}`;
  if (p.progress_pct !== undefined) return `${p.progress_pct}% (${p.completed}/${p.total})`;
  if (p.count !== undefined) return `${p.count} Eintraege`;
  const label = TYPE_LABELS[msg.message_type] || msg.message_type;
  return label;
}

export default function ActivityFeed() {
  const { messages } = useWebSocket();

  const filtered = messages.filter(
    (msg) => !IGNORED_TYPES.has(msg.message_type) && !IGNORED_TYPES.has(msg.type)
  );

  return (
    <div className="bg-white rounded-xl shadow p-5">
      <h3 className="font-semibold mb-4 flex items-center gap-2">
        <Clock className="w-5 h-5 text-gray-400" /> Live-Aktivitaet
      </h3>
      <div className="space-y-2 max-h-80 overflow-y-auto">
        {filtered.length === 0 && <p className="text-gray-400 text-sm">Warte auf Aktivitaet...</p>}
        {filtered.map((msg, i) => (
          <div key={i} className="text-sm border-l-2 border-cyan-400 pl-3 py-1">
            <span className="text-gray-400 text-xs">{msg.timestamp || new Date().toLocaleTimeString()}</span>
            <span className="ml-2 font-medium text-gray-700">{msg.sender_id || 'System'}</span>
            <span className="ml-1 text-xs text-cyan-600">{TYPE_LABELS[msg.message_type] || ''}</span>
            <span className="ml-2 text-gray-600">{extractText(msg)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
