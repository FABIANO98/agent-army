export interface Agent {
  name: string;
  agent_type: string;
  status: string;
  tasks_completed: number;
  success_rate: number;
  queue_size: number;
  uptime: number;
  errors: string[];
  last_activity?: string;
}

export interface Task {
  id: number;
  title: string;
  description: string;
  status: string;
  priority: number;
  progress_pct: number;
  result_summary?: string;
  created_at: string;
  completed_at?: string;
  subtasks?: Subtask[];
  results?: TaskResult[];
}

export interface Subtask {
  id: number;
  task_id: number;
  title: string;
  assigned_agent: string;
  status: string;
  sequence_order: number;
}

export interface TaskResult {
  id: number;
  task_id: number;
  result_type: string;
  title: string;
  data: any;
}

export interface DashboardStats {
  active_agents: number;
  total_agents: number;
  running_tasks: number;
  total_tasks: number;
  prospects_today: number;
  emails_today: number;
  pipeline_value: number;
  llm_available: boolean;
}

export interface Communication {
  id: number;
  sender_agent: string;
  receiver_agent: string;
  message_type: string;
  summary: string;
  task_id?: number;
  timestamp: string;
}
