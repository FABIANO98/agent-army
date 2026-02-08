import { useState } from 'react';
import { Send, AlertCircle } from 'lucide-react';
import { api } from '../../api/client';

const EXAMPLE_TASKS = [
  'Finde 5 Bauunternehmen in Zuerich',
  'Finde 10 Transportunternehmen in Bern',
  'Finde Handwerksbetriebe in Basel',
  'Pipeline-Report erstellen',
];

export default function TaskForm({ onCreated }: { onCreated: () => void }) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await api.createTask(title, description || title);
      setTitle('');
      setDescription('');
      onCreated();
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Task konnte nicht erstellt werden';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const selectExample = (example: string) => {
    setTitle(example);
    setError(null);
  };

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow p-5">
      <h3 className="font-semibold mb-3">Neuer Task</h3>

      <div className="flex flex-wrap gap-2 mb-3">
        {EXAMPLE_TASKS.map((ex) => (
          <button
            key={ex}
            type="button"
            onClick={() => selectExample(ex)}
            className="text-xs bg-cyan-50 text-cyan-700 px-3 py-1 rounded-full hover:bg-cyan-100 transition-colors"
          >
            {ex}
          </button>
        ))}
      </div>

      <input
        className="w-full border rounded-lg px-3 py-2 mb-3 focus:outline-none focus:ring-2 focus:ring-cyan-400"
        placeholder="Task-Titel (z.B. Finde 5 Unternehmen in Zuerich)"
        value={title}
        onChange={(e) => { setTitle(e.target.value); setError(null); }}
      />
      <textarea
        className="w-full border rounded-lg px-3 py-2 mb-3 h-20 focus:outline-none focus:ring-2 focus:ring-cyan-400"
        placeholder="Optional: Detaillierte Beschreibung..."
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />

      {error && (
        <div className="flex items-center gap-2 text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <button
        type="submit"
        disabled={loading || !title.trim()}
        className="flex items-center gap-2 bg-cyan-500 text-white px-4 py-2 rounded-lg hover:bg-cyan-600 disabled:opacity-50 transition-colors"
      >
        <Send className="w-4 h-4" /> {loading ? 'Erstelle...' : 'Task erstellen'}
      </button>
    </form>
  );
}
