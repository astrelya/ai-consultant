export interface ChatMessage {
  id: string;
  role: 'user' | 'agent' | 'system';
  content: string;
  created_at?: string;
  metadata?: Record<string, unknown>;
}

export interface Project {
  id: string;
  name?: string;
  created_at?: string;
  updated_at?: string;
  jira_configured?: boolean;
  spec?: string | null;
  chat_history?: ChatMessage[];
  cost_ledger?: {
    total_prompt_tokens?: number;
    total_completion_tokens?: number;
    total_tokens?: number;
    total_cost_usd?: number;
    last_updated?: string;
  };
}

export interface ProjectCreate {
  name: string;
  description?: string;
}

// Story 6.3 — Dev View workspace shapes.
export interface WorkspaceEntry {
  path: string;
  type: 'file' | 'dir';
}

export interface WorkspaceTree {
  root: string | null;
  entries: WorkspaceEntry[];
}

export interface WorkspaceFile {
  path: string;
  content: string;
  truncated: boolean;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8050';

class ApiClientError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiClientError';
  }
}

async function fetchApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  
  const headers = new Headers(options.headers);
  if (!headers.has('Content-Type') && options.method && options.method !== 'GET') {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorDetail = `API Error: ${response.status} ${response.statusText || 'Unknown'}`;
    try {
      const errorBody = await response.json();
      if (errorBody && errorBody.detail) {
        errorDetail = typeof errorBody.detail === 'string' ? errorBody.detail : JSON.stringify(errorBody.detail);
      }
    } catch {
      // Ignore if body is not JSON
    }
    throw new ApiClientError(response.status, errorDetail);
  }

  const text = await response.text();
  if (!text) {
    return {} as T;
  }
  return JSON.parse(text);
}

export const apiClient = {
  getProjects: () => fetchApi<Project[]>('/projects'),
  createProject: (data: ProjectCreate) => fetchApi<Project>('/projects', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  getProject: (id: string) => fetchApi<Project>(`/projects/${id}`),
  acceptTicket: (projectId: string, ticketId: string, updates?: Record<string, any>) =>
    fetchApi<{ ok: boolean }>(`/projects/${projectId}/tickets/${ticketId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: 'Accepted', ...updates }),
    }),
  reviseTicket: (projectId: string, ticketId: string, instruction: string) =>
    fetchApi<{ tickets: any[] }>(`/projects/${projectId}/tickets/${ticketId}/revise`, {
      method: 'POST',
      body: JSON.stringify({ instruction }),
    }),
  executeTickets: (projectId: string, ticketIds: string[]) =>
    fetchApi<{ ok: boolean }>(`/projects/${projectId}/execute`, {
      method: 'POST',
      body: JSON.stringify({ ticket_ids: ticketIds }),
    }),
  generateTickets: (projectId: string) =>
    fetchApi<{ tickets: any[] }>(`/projects/${projectId}/tickets/generate`, {
      method: 'POST',
    }),
  getConfig: () => fetchApi<{
    agent_mode: 'local' | 'remote';
    models: { ticket: string; coding: string };
    available_models: string[];
  }>('/config'),
  updateModels: (body: { ticket?: string; coding?: string }) =>
    fetchApi<{
      updated: Record<string, string>;
      models: { ticket: string; coding: string };
    }>('/config/models', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  getWorkspaceTree: (projectId: string) =>
    fetchApi<WorkspaceTree>(`/projects/${projectId}/workspace/tree`),
  getWorkspaceFile: (projectId: string, path: string) =>
    fetchApi<WorkspaceFile>(
      `/projects/${projectId}/workspace/file?path=${encodeURIComponent(path)}`,
    ),
};
