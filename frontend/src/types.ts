export interface Project {
  id: string;
  name: string;
  description: string | null;
  implementation_trigger_mode: string | null;
  created_at: string;
  updated_at: string;
}

export interface RepoConfig {
  id: string;
  provider: string;
  org_or_owner: string;
  repo_name: string;
  default_branch: string;
}

export interface JiraConfig {
  id: string;
  site_url: string;
  jira_project_key: string;
  default_issue_type: string;
  auth_email: string;
}

export interface ModelConfig {
  id: string;
  project_id: string | null;
  chat_model: string;
  coding_model: string;
  chat_model_params: Record<string, unknown>;
  coding_model_params: Record<string, unknown>;
}

export interface AppSettings {
  id: string;
  implementation_trigger_mode: string;
  poll_interval_seconds: number;
  auto_trigger_jira_status: string;
  gemini_api_key_set: boolean;
}

export interface ChatSession {
  id: string;
  project_id: string;
  title: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: string;
  content: string;
  created_at: string;
}

export interface TicketDraft {
  id: string;
  project_id: string;
  chat_session_id: string | null;
  title: string;
  description: string;
  acceptance_criteria: string[];
  issue_type: string;
  priority: string;
  labels: string[];
  epic_link: string | null;
  status: string;
  jira_issue_key: string | null;
  push_error: string | null;
  order_index: number;
  created_at: string;
}

export interface AgentRun {
  id: string;
  project_id: string;
  run_type: string;
  related_id: string | null;
  model_used: string | null;
  status: string;
  input_summary: string | null;
  output_summary: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface PullRequest {
  id: string;
  project_id: string;
  jira_issue_key: string;
  pr_url: string | null;
  pr_number: number | null;
  status: string;
  created_at: string;
}

export interface GeminiModel {
  name: string;
  display_name: string;
  input_token_limit: number | null;
  output_token_limit: number | null;
}

export interface GeminiModelsResponse {
  models: GeminiModel[];
  source: "api" | "fallback";
  error?: string;
}

export interface TokenBucket {
  input_tokens: number;
  output_tokens: number;
  total_tokens?: number;
  calls: number;
}

export interface TokenUsage {
  project_id: string;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  by_model: Record<string, TokenBucket>;
  chat_totals: { input_tokens: number; output_tokens: number; calls: number };
  run_totals: Record<string, { input_tokens: number; output_tokens: number; calls: number }>;
}
