import { useWebSocket } from '../../hooks/useWebSocket';
import { Clock } from 'lucide-react';

export default function ActivityFeed() {
  const { messages } = useWebSocket();
  return (
    <div className="bg-white rounded-xl shadow p-5">
      <h3 className="font-semibold mb-4 flex items-center gap-2">
        <Clock className="w-5 h-5 text-gray-400" /> Live Activity
      </h3>
      <div className="space-y-2 max-h-80 overflow-y-auto">
        {messages.length === 0 && <p className="text-gray-400 text-sm">Waiting for activity...</p>}
        {messages.map((msg, i) => (
          <div key={i} className="text-sm border-l-2 border-cyan-400 pl-3 py-1">
            <span className="text-gray-400 text-xs">{msg.timestamp || new Date().toLocaleTimeString()}</span>
            <span className="ml-2 font-medium text-gray-700">{msg.sender_id || 'system'}</span>
            <span className="ml-2 text-gray-600">{msg.payload?.text || msg.message_type || JSON.stringify(msg).slice(0, 80)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
