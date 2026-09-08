import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import type { ChatSession, GeminiModel, JiraConfig, ModelConfig, Project, RepoConfig, TokenUsage } from "../types";

export default function ProjectDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [repo, setRepo] = useState<RepoConfig | null>(null);
  const [jira, setJira] = useState<JiraConfig | null>(null);
  const [model, setModel] = useState<ModelConfig | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [availableModels, setAvailableModels] = useState<GeminiModel[]>([]);
  const [modelsSource, setModelsSource] = useState<"api" | "fallback" | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [usage, setUsage] = useState<TokenUsage | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // form state
  const [repoForm, setRepoForm] = useState({ org_or_owner: "", repo_name: "", default_branch: "main", pat: "" });
  const [jiraForm, setJiraForm] = useState({
    site_url: "", jira_project_key: "", default_issue_type: "Story", auth_email: "", api_token: "",
  });
  const [modelForm, setModelForm] = useState({ chat_model: "gemini-2.5-pro", coding_model: "gemini-2.5-pro" });
  const [triggerMode, setTriggerMode] = useState<string>("");

  async function loadAll() {
    try {
      const [p, r, j, m, ss, models, tu] = await Promise.all([
        api.getProject(id),
        api.getRepoConfig(id),
        api.getJiraConfig(id),
        api.getProjectModelConfig(id),
        api.listChatSessions(id),
        api.listGeminiModels(),
        api.getProjectTokenUsage(id),
      ]);
      setProject(p); setRepo(r); setJira(j); setModel(m); setSessions(ss);
      setAvailableModels(models.models);
      setModelsSource(models.source);
      setModelsError(models.error ?? null);
      setUsage(tu);
      if (r) setRepoForm({ ...repoForm, org_or_owner: r.org_or_owner, repo_name: r.repo_name, default_branch: r.default_branch });
      if (j) setJiraForm({ ...jiraForm, site_url: j.site_url, jira_project_key: j.jira_project_key, default_issue_type: j.default_issue_type, auth_email: j.auth_email });
      if (m) setModelForm({ chat_model: m.chat_model, coding_model: m.coding_model });
      setTriggerMode(p.implementation_trigger_mode || "");
    } catch (e) { setErr(String(e)); }
  }

  useEffect(() => { loadAll(); /* eslint-disable-next-line */ }, [id]);

  async function saveRepo() {
    try { await api.setRepoConfig(id, repoForm); setMsg("Repo config saved."); loadAll(); }
    catch (e) { setErr(String(e)); }
  }
  async function testRepo() {
    try { const r = await api.testRepoConfig(id); setMsg(`Repo OK: ${r.full_name}`); }
    catch (e) { setErr(String(e)); }
  }
  async function saveJira() {
    try { await api.setJiraConfig(id, jiraForm); setMsg("Jira config saved."); loadAll(); }
    catch (e) { setErr(String(e)); }
  }
  async function testJira() {
    try { const r = await api.testJiraConfig(id); setMsg(`Jira OK: ${r.project_name}`); }
    catch (e) { setErr(String(e)); }
  }
  async function saveModel() {
    try {
      await api.setProjectModelConfig(id, { ...modelForm, chat_model_params: {}, coding_model_params: {} });
      setMsg("Model config saved."); loadAll();
    } catch (e) { setErr(String(e)); }
  }
  async function saveTrigger() {
    try { await api.setProjectTrigger(id, triggerMode || null); setMsg("Trigger mode saved."); loadAll(); }
    catch (e) { setErr(String(e)); }
  }
  async function newSession() {
    const s = await api.createChatSession(id);
    window.location.href = `/projects/${id}/chat/${s.id}`;
  }

  async function deleteProject() {
    if (!project) return;
    if (!confirm(`Delete project "${project.name}"?\n\nThis permanently removes its config, chat sessions, ticket drafts, and agent runs. This cannot be undone.`)) return;
    try {
      await api.deleteProject(id);
      navigate("/projects");
    } catch (e) { setErr(String(e)); }
  }

  if (!project) return <div>Loading…</div>;

  return (
    <div>
      <div className="row spread">
        <h2>{project.name}</h2>
        <Link to="/projects"><button className="ghost">← All projects</button></Link>
      </div>
      {project.description && <div className="muted">{project.description}</div>}

      {msg && <div className="ok">{msg}</div>}
      {err && <div className="err">{err}</div>}

      <div className="card">
        <h3>GitHub repo</h3>
        <div className="grid grid-2">
          <div><label>Owner / org</label><input value={repoForm.org_or_owner} onChange={(e) => setRepoForm({ ...repoForm, org_or_owner: e.target.value })} /></div>
          <div><label>Repo name</label><input value={repoForm.repo_name} onChange={(e) => setRepoForm({ ...repoForm, repo_name: e.target.value })} /></div>
          <div><label>Default branch</label><input value={repoForm.default_branch} onChange={(e) => setRepoForm({ ...repoForm, default_branch: e.target.value })} /></div>
          <div><label>Personal Access Token</label><input type="password" placeholder={repo ? "•••• (unchanged)" : "ghp_…"} value={repoForm.pat} onChange={(e) => setRepoForm({ ...repoForm, pat: e.target.value })} /></div>
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <button onClick={saveRepo}>Save</button>
          {repo && <button className="secondary" onClick={testRepo}>Test connection</button>}
        </div>
      </div>

      <div className="card">
        <h3>Jira workspace</h3>
        <div className="grid grid-2">
          <div><label>Site URL</label><input value={jiraForm.site_url} onChange={(e) => setJiraForm({ ...jiraForm, site_url: e.target.value })} placeholder="https://you.atlassian.net" /></div>
          <div><label>Project key</label><input value={jiraForm.jira_project_key} onChange={(e) => setJiraForm({ ...jiraForm, jira_project_key: e.target.value })} placeholder="ENG" /></div>
          <div><label>Default issue type</label><input value={jiraForm.default_issue_type} onChange={(e) => setJiraForm({ ...jiraForm, default_issue_type: e.target.value })} /></div>
          <div><label>Auth email</label><input value={jiraForm.auth_email} onChange={(e) => setJiraForm({ ...jiraForm, auth_email: e.target.value })} /></div>
          <div><label>API token</label><input type="password" placeholder={jira ? "•••• (unchanged)" : "…"} value={jiraForm.api_token} onChange={(e) => setJiraForm({ ...jiraForm, api_token: e.target.value })} /></div>
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <button onClick={saveJira}>Save</button>
          {jira && <button className="secondary" onClick={testJira}>Test connection</button>}
        </div>
      </div>

      <div className="card">
        <h3>Models</h3>
        <div className="grid grid-2">
          <div>
            <label>Chat model</label>
            <select value={modelForm.chat_model} onChange={(e) => setModelForm({ ...modelForm, chat_model: e.target.value })}>
              {availableModels.every((m) => m.name !== modelForm.chat_model) && (
                <option value={modelForm.chat_model}>{modelForm.chat_model} (current)</option>
              )}
              {availableModels.map((m) => (
                <option key={m.name} value={m.name}>{m.display_name} ({m.name})</option>
              ))}
            </select>
          </div>
          <div>
            <label>Coding model</label>
            <select value={modelForm.coding_model} onChange={(e) => setModelForm({ ...modelForm, coding_model: e.target.value })}>
              {availableModels.every((m) => m.name !== modelForm.coding_model) && (
                <option value={modelForm.coding_model}>{modelForm.coding_model} (current)</option>
              )}
              {availableModels.map((m) => (
                <option key={m.name} value={m.name}>{m.display_name} ({m.name})</option>
              ))}
            </select>
          </div>
        </div>
        <div style={{ marginTop: 12 }}>
          <button onClick={saveModel}>Save models</button>
        </div>
        <div className="muted" style={{ marginTop: 8 }}>
          {modelsSource === "fallback"
            ? `Using fallback list — API key check failed${modelsError ? `: ${modelsError.slice(0, 120)}…` : ""}`
            : `${availableModels.length} models available for this API key.`}
        </div>
      </div>

      <div className="card">
        <h3>Token usage</h3>
        {!usage || usage.total_tokens === 0 ? (
          <div className="muted">No tokens recorded yet. Usage is tracked once you chat or run agents.</div>
        ) : (
          <>
            <div className="row spread">
              <div><strong>{usage.total_tokens.toLocaleString()}</strong> total tokens</div>
              <div className="muted">
                {usage.total_input_tokens.toLocaleString()} in · {usage.total_output_tokens.toLocaleString()} out
              </div>
            </div>
            <h4 style={{ marginTop: 16, marginBottom: 8, fontSize: 13, color: "var(--muted)", fontWeight: 500 }}>By model</h4>
            <table>
              <thead>
                <tr><th>Model</th><th style={{ textAlign: "right" }}>Input</th><th style={{ textAlign: "right" }}>Output</th><th style={{ textAlign: "right" }}>Total</th><th style={{ textAlign: "right" }}>Calls</th></tr>
              </thead>
              <tbody>
                {Object.entries(usage.by_model).map(([name, b]) => (
                  <tr key={name}>
                    <td>{name}</td>
                    <td style={{ textAlign: "right" }}>{b.input_tokens.toLocaleString()}</td>
                    <td style={{ textAlign: "right" }}>{b.output_tokens.toLocaleString()}</td>
                    <td style={{ textAlign: "right" }}>{(b.input_tokens + b.output_tokens).toLocaleString()}</td>
                    <td style={{ textAlign: "right" }}>{b.calls}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {(usage.chat_totals.calls > 0 || Object.keys(usage.run_totals).length > 0) && (
              <>
                <h4 style={{ marginTop: 16, marginBottom: 8, fontSize: 13, color: "var(--muted)", fontWeight: 500 }}>By activity</h4>
                <table>
                  <thead>
                    <tr><th>Activity</th><th style={{ textAlign: "right" }}>Input</th><th style={{ textAlign: "right" }}>Output</th><th style={{ textAlign: "right" }}>Calls</th></tr>
                  </thead>
                  <tbody>
                    {usage.chat_totals.calls > 0 && (
                      <tr>
                        <td>Brainstorm chat</td>
                        <td style={{ textAlign: "right" }}>{usage.chat_totals.input_tokens.toLocaleString()}</td>
                        <td style={{ textAlign: "right" }}>{usage.chat_totals.output_tokens.toLocaleString()}</td>
                        <td style={{ textAlign: "right" }}>{usage.chat_totals.calls}</td>
                      </tr>
                    )}
                    {Object.entries(usage.run_totals).map(([kind, b]) => (
                      <tr key={kind}>
                        <td>{kind}</td>
                        <td style={{ textAlign: "right" }}>{b.input_tokens.toLocaleString()}</td>
                        <td style={{ textAlign: "right" }}>{b.output_tokens.toLocaleString()}</td>
                        <td style={{ textAlign: "right" }}>{b.calls}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </>
        )}
        <div style={{ marginTop: 12 }}>
          <button className="secondary" onClick={() => api.getProjectTokenUsage(id).then(setUsage)}>Refresh</button>
        </div>
      </div>

      <div className="card">
        <h3>Implementation trigger</h3>
        <select value={triggerMode} onChange={(e) => setTriggerMode(e.target.value)}>
          <option value="">Inherit global default</option>
          <option value="manual">Manual</option>
          <option value="auto_poll">Auto (poll Jira)</option>
        </select>
        <div style={{ marginTop: 12 }}>
          <button onClick={saveTrigger}>Save trigger</button>
        </div>
      </div>

      <div className="card">
        <h3>Brainstorm sessions</h3>
        <div className="row spread">
          <div className="muted">Start a conversation to draft new tickets.</div>
          <button onClick={newSession}>New session</button>
        </div>
        {sessions.length > 0 && (
          <table style={{ marginTop: 12 }}>
            <thead><tr><th>Title</th><th>Status</th><th>Created</th></tr></thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.id}>
                  <td><Link to={`/projects/${id}/chat/${s.id}`}>{s.title || s.id.slice(0, 8)}</Link></td>
                  <td><span className="badge">{s.status}</span></td>
                  <td>{new Date(s.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card" style={{ borderColor: "var(--danger)" }}>
        <h3 style={{ color: "var(--danger)" }}>Danger zone</h3>
        <div className="row spread">
          <div className="muted">
            Permanently delete this project and all its config, chat sessions, ticket drafts, and agent runs.
          </div>
          <button className="danger" onClick={deleteProject}>Delete project</button>
        </div>
      </div>
    </div>
  );
}
