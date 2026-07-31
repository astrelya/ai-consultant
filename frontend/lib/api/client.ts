export interface Project {
  id: string;
  name?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ProjectCreate {
  name: string;
  description?: string;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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
};
