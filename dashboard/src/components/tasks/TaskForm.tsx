import { useState } from 'react';
import { Send } from 'lucide-react';
import { api } from '../../api/client';

export default function TaskForm({ onCreated }: { onCreated: () => void }) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    setLoading(true);
    try {
      await api.createTask(title, description || title);
      setTitle('');
      setDescription('');
      onCreated();
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow p-5">
      <h3 className="font-semibold mb-3">New Task</h3>
      <input
        className="w-full border rounded-lg px-3 py-2 mb-3 focus:outline-none focus:ring-2 focus:ring-cyan-400"
        placeholder="Task title (e.g. Finde 5 Unternehmen in Zurich)"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <textarea
        className="w-full border rounded-lg px-3 py-2 mb-3 h-20 focus:outline-none focus:ring-2 focus:ring-cyan-400"
        placeholder="Optional: detailed description..."
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <button
        type="submit"
        disabled={loading || !title.trim()}
        className="flex items-center gap-2 bg-cyan-500 text-white px-4 py-2 rounded-lg hover:bg-cyan-600 disabled:opacity-50 transition-colors"
      >
        <Send className="w-4 h-4" /> {loading ? 'Creating...' : 'Create Task'}
      </button>
    </form>
  );
}
