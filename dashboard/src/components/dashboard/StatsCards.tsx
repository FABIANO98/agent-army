import { Bot, ListTodo, Mail, DollarSign } from 'lucide-react';
import type { DashboardStats } from '../../api/types';

function Card({ icon: Icon, label, value, color }: { icon: any; label: string; value: string | number; color: string }) {
  return (
    <div className="bg-white rounded-xl shadow p-5 flex items-center gap-4">
      <div className={`p-3 rounded-lg ${color}`}>
        <Icon className="w-6 h-6 text-white" />
      </div>
      <div>
        <p className="text-sm text-gray-500">{label}</p>
        <p className="text-2xl font-bold">{value}</p>
      </div>
    </div>
  );
}

export default function StatsCards({ stats }: { stats?: DashboardStats }) {
  if (!stats) return null;
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <Card icon={Bot} label="Active Agents" value={`${stats.active_agents}/${stats.total_agents}`} color="bg-cyan-500" />
      <Card icon={ListTodo} label="Running Tasks" value={stats.running_tasks} color="bg-violet-500" />
      <Card icon={Mail} label="Emails Today" value={stats.emails_today} color="bg-amber-500" />
      <Card icon={DollarSign} label="Pipeline Value" value={`CHF ${stats.pipeline_value.toLocaleString()}`} color="bg-emerald-500" />
    </div>
  );
}
