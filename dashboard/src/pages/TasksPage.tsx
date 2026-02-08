import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import TaskForm from '../components/tasks/TaskForm';
import TaskListComponent from '../components/tasks/TaskList';

export default function TasksPage() {
  const { data: tasks, refetch } = useQuery({ queryKey: ['tasks'], queryFn: () => api.getTasks(), refetchInterval: 5000 });
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-800">Tasks</h1>
      <TaskForm onCreated={refetch} />
      <TaskListComponent tasks={tasks} />
    </div>
  );
}
