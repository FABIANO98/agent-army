import type { DashboardStats, Communication, Agent, Task } from './types';

const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) throw new Error(`API Error: ${res.status}`);
  return res.json();
}

export const api = {
  getDashboardStats: () => request<DashboardStats>('/dashboard/stats'),
  getCommunications: (limit = 50) => request<Communication[]>(`/dashboard/communications?limit=${limit}`),
  getAgents: () => request<Agent[]>('/agents'),
  getTasks: (status?: string) => request<Task[]>(`/tasks${status ? `?status=${status}` : ''}`),
  getTask: (id: number) => request<Task>(`/tasks/${id}`),
  createTask: (title: string, description: string, priority?: number) =>
    request<Task>('/tasks', {
      method: 'POST',
      body: JSON.stringify({ title, description, priority: priority ?? 5 }),
    }),
  cancelTask: (id: number) => request<any>(`/tasks/${id}/cancel`, { method: 'POST' }),
};
