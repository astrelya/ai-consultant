import type {
  AgentRun,
  AppSettings,
  ChatMessage,
  ChatSession,
  GeminiModelsResponse,
  JiraConfig,
  ModelConfig,
  Project,
  PullRequest,
  RepoConfig,
  TicketDraft,
  TokenUsage,
} from "./types";

const BASE = "/api/v1";

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  // Projects
  listProjects: () => req<Project[]>("GET", "/projects"),
  createProject: (name: string, description?: string) =>
    req<Project>("POST", "/projects", { name, description }),
  getProject: (id: string) => req<Project>("GET", `/projects/${id}`),
  updateProject: (id: string, payload: Partial<Project>) =>
    req<Project>("PATCH", `/projects/${id}`, payload),
  deleteProject: (id: string) => req<void>("DELETE", `/projects/${id}`),

  // Repo config
  getRepoConfig: (projectId: string) =>
    req<RepoConfig | null>("GET", `/projects/${projectId}/repo-config`),
  setRepoConfig: (
    projectId: string,
    payload: { org_or_owner: string; repo_name: string; default_branch: string; pat: string }
  ) => req<RepoConfig>("POST", `/projects/${projectId}/repo-config`, payload),
  testRepoConfig: (projectId: string) =>
    req<{ ok: boolean; full_name?: string; default_branch?: string }>(
      "POST",
      `/projects/${projectId}/repo-config/test`
    ),

  // Jira config
  getJiraConfig: (projectId: string) =>
    req<JiraConfig | null>("GET", `/projects/${projectId}/jira-config`),
  setJiraConfig: (
    projectId: string,
    payload: {
      site_url: string;
      jira_project_key: string;
      default_issue_type: string;
      auth_email: string;
      api_token: string;
    }
  ) => req<JiraConfig>("POST", `/projects/${projectId}/jira-config`, payload),
  testJiraConfig: (projectId: string) =>
    req<{ ok: boolean; account_id?: string; project_name?: string }>(
      "POST",
      `/projects/${projectId}/jira-config/test`
    ),

  // Model config
  getDefaultModelConfig: () => req<ModelConfig>("GET", "/model-configs/default"),
  setDefaultModelConfig: (payload: Partial<ModelConfig>) =>
    req<ModelConfig>("PUT", "/model-configs/default", payload),
  getProjectModelConfig: (projectId: string) =>
    req<ModelConfig>("GET", `/projects/${projectId}/model-config`),
  setProjectModelConfig: (projectId: string, payload: Partial<ModelConfig>) =>
    req<ModelConfig>("PUT", `/projects/${projectId}/model-config`, payload),

  // Settings
  getSettings: () => req<AppSettings>("GET", "/settings"),
  setSettings: (payload: {
    implementation_trigger_mode: string;
    poll_interval_seconds: number;
    auto_trigger_jira_status: string;
    gemini_api_key?: string | null;
  }) => req<AppSettings>("PUT", "/settings", payload),
  setProjectTrigger: (projectId: string, mode: string | null) =>
    req("PATCH", `/projects/${projectId}/implementation-trigger`, {
      implementation_trigger_mode: mode,
    }),

  // Chat sessions
  listChatSessions: (projectId: string) =>
    req<ChatSession[]>("GET", `/projects/${projectId}/chat-sessions`),
  createChatSession: (projectId: string, title?: string) =>
    req<ChatSession>("POST", `/projects/${projectId}/chat-sessions`, { title }),
  getChatSession: (sessionId: string) =>
    req<{ session: ChatSession; messages: ChatMessage[] }>(
      "GET",
      `/chat-sessions/${sessionId}`
    ),
  generateTickets: (sessionId: string) =>
    req<AgentRun>("POST", `/chat-sessions/${sessionId}/generate-tickets`),

  // Ticket drafts
  listDrafts: (params: { project_id?: string; session_id?: string; status?: string }) => {
    const q = new URLSearchParams();
    if (params.project_id) q.set("project_id", params.project_id);
    if (params.session_id) q.set("session_id", params.session_id);
    if (params.status) q.set("status", params.status);
    return req<TicketDraft[]>("GET", `/ticket-drafts?${q.toString()}`);
  },
  updateDraft: (id: string, payload: Partial<TicketDraft>) =>
    req<TicketDraft>("PATCH", `/ticket-drafts/${id}`, payload),
  acceptDraft: (id: string) => req<TicketDraft>("POST", `/ticket-drafts/${id}/accept`),
  rejectDraft: (id: string) => req<TicketDraft>("POST", `/ticket-drafts/${id}/reject`),
  pushDrafts: (ids: string[]) =>
    req<TicketDraft[]>("POST", `/ticket-drafts/push`, { draft_ids: ids }),
  retryPush: (id: string) => req<TicketDraft>("POST", `/ticket-drafts/${id}/retry-push`),

  // Runs
  listRuns: (params: { project_id?: string; run_type?: string; status?: string }) => {
    const q = new URLSearchParams();
    if (params.project_id) q.set("project_id", params.project_id);
    if (params.run_type) q.set("run_type", params.run_type);
    if (params.status) q.set("status", params.status);
    return req<AgentRun[]>("GET", `/agent-runs?${q.toString()}`);
  },
  implement: (projectId: string, jiraIssueKey: string) =>
    req<AgentRun>("POST", `/projects/${projectId}/implement`, {
      jira_issue_key: jiraIssueKey,
    }),
  listPRs: (projectId?: string) => {
    const q = new URLSearchParams();
    if (projectId) q.set("project_id", projectId);
    return req<PullRequest[]>("GET", `/pull-requests?${q.toString()}`);
  },

  // Gemini
  listGeminiModels: () => req<GeminiModelsResponse>("GET", "/gemini/models"),

  // Token usage
  getProjectTokenUsage: (projectId: string) =>
    req<TokenUsage>("GET", `/projects/${projectId}/token-usage`),
};
