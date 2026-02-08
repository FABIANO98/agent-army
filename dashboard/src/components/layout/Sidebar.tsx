import { Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, Bot, ListTodo, Activity } from 'lucide-react';

const nav = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/agents', label: 'Agents', icon: Bot },
  { to: '/tasks', label: 'Tasks', icon: ListTodo },
];

export default function Sidebar() {
  const { pathname } = useLocation();
  return (
    <aside className="w-64 bg-gray-900 text-white min-h-screen p-4 flex flex-col">
      <div className="text-xl font-bold mb-8 flex items-center gap-2">
        <Activity className="w-6 h-6 text-cyan-400" />
        Agent Army
      </div>
      <nav className="flex flex-col gap-1">
        {nav.map((n) => {
          const active = pathname === n.to;
          return (
            <Link
              key={n.to}
              to={n.to}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${
                active ? 'bg-cyan-600 text-white' : 'text-gray-300 hover:bg-gray-800'
              }`}
            >
              <n.icon className="w-5 h-5" />
              {n.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
