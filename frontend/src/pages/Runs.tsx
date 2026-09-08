import { useEffect, useState } from "react";
import { api } from "../api";
import type { AgentRun, Project, PullRequest } from "../types";

export default function Runs() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [prs, setPRs] = useState<PullRequest[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [issueKey, setIssueKey] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { api.listProjects().then(setProjects); }, []);

  async function load() {
    setRuns(await api.listRuns({ project_id: selected || undefined }));
    setPRs(await api.listPRs(selected || undefined));
  }
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
    // eslint-disable-next-line
  }, [selected]);

  async function trigger() {
    if (!selected || !issueKey.trim()) return;
    try {
      const run = await api.implement(selected, issueKey.trim());
      setMsg(`Enqueued run ${run.id.slice(0, 8)} for ${issueKey}`);
      setIssueKey("");
      load();
    } catch (e) { setErr(String(e)); }
  }

  return (
    <div>
      <h2>Runs</h2>

      <div className="card">
        <h3>Trigger implementation</h3>
        <div className="grid grid-2">
          <div>
            <label>Project</label>
            <select value={selected} onChange={(e) => setSelected(e.target.value)}>
              <option value="">— select —</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <label>Jira issue key</label>
            <input value={issueKey} onChange={(e) => setIssueKey(e.target.value)} placeholder="ENG-123" />
          </div>
        </div>
        <div style={{ marginTop: 12 }}>
          <button onClick={trigger} disabled={!selected || !issueKey.trim()}>Run implementation agent</button>
        </div>
        {msg && <div className="ok">{msg}</div>}
        {err && <div className="err">{err}</div>}
      </div>

      <div className="card">
        <h3>Agent runs</h3>
        {runs.length === 0 ? <div className="muted">No runs.</div> : (
          <table>
            <thead>
              <tr><th>Type</th><th>Related</th><th>Model</th><th>Status</th><th>Created</th><th>Summary</th></tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>{r.run_type}</td>
                  <td>{r.related_id || "—"}</td>
                  <td>{r.model_used || "—"}</td>
                  <td><span className={`badge ${r.status}`}>{r.status}</span></td>
                  <td>{new Date(r.created_at).toLocaleString()}</td>
                  <td className="muted" style={{ maxWidth: 400, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {r.error_message || r.output_summary || ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3>Pull requests</h3>
        {prs.length === 0 ? <div className="muted">No PRs recorded.</div> : (
          <table>
            <thead><tr><th>Ticket</th><th>Status</th><th>URL</th><th>Opened</th></tr></thead>
            <tbody>
              {prs.map((p) => (
                <tr key={p.id}>
                  <td>{p.jira_issue_key}</td>
                  <td><span className={`badge ${p.status}`}>{p.status}</span></td>
                  <td>{p.pr_url ? <a href={p.pr_url} target="_blank" rel="noreferrer">{p.pr_url}</a> : "—"}</td>
                  <td>{new Date(p.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
