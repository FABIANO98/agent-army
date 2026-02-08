import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import StatsCards from '../components/dashboard/StatsCards';
import ActivityFeed from '../components/dashboard/ActivityFeed';

export default function DashboardPage() {
  const { data: stats } = useQuery({ queryKey: ['stats'], queryFn: api.getDashboardStats, refetchInterval: 5000 });
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-800">Dashboard</h1>
      <StatsCards stats={stats} />
      <ActivityFeed />
    </div>
  );
}
