import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { Project, TicketDraft } from "../types";

export default function TicketReview() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [drafts, setDrafts] = useState<TicketDraft[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState<Partial<TicketDraft>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { api.listProjects().then(setProjects); }, []);

  async function load() {
    setDrafts(await api.listDrafts({ project_id: selected || undefined }));
  }
  useEffect(() => { load(); }, [selected]);

  function startEdit(d: TicketDraft) {
    setEditing(d.id);
    setForm({
      title: d.title, description: d.description, acceptance_criteria: d.acceptance_criteria,
      issue_type: d.issue_type, priority: d.priority, labels: d.labels,
    });
  }
  async function saveEdit(id: string) {
    try { await api.updateDraft(id, form); setEditing(null); setMsg("Saved"); load(); }
    catch (e) { setErr(String(e)); }
  }
  async function accept(id: string) { await api.acceptDraft(id); load(); }
  async function reject(id: string) { await api.rejectDraft(id); load(); }
  async function retry(id: string) { await api.retryPush(id); load(); }

  const grouped = useMemo(() => {
    const byProject = new Map<string, TicketDraft[]>();
    for (const d of drafts) {
      const arr = byProject.get(d.project_id) || [];
      arr.push(d);
      byProject.set(d.project_id, arr);
    }
    return byProject;
  }, [drafts]);

  const accepted = drafts.filter((d) => d.status === "accepted");
  async function pushAccepted() {
    if (accepted.length === 0) return;
    try {
      const res = await api.pushDrafts(accepted.map((d) => d.id));
      const ok = res.filter((r) => r.status === "pushed").length;
      const failed = res.filter((r) => r.status === "push_failed").length;
      setMsg(`Pushed ${ok} to Jira${failed ? `, ${failed} failed` : ""}.`);
      load();
    } catch (e) { setErr(String(e)); }
  }
  async function acceptAllPending() {
    const pending = drafts.filter((d) => d.status === "pending" || d.status === "edited");
    if (pending.length === 0) return;
    await Promise.all(pending.map((d) => api.acceptDraft(d.id)));
    load();
  }

  const projectName = (pid: string) => projects.find((p) => p.id === pid)?.name || pid.slice(0, 8);

  return (
    <div>
      <h2>Ticket Review</h2>
      <div className="row spread">
        <div className="row">
          <label style={{ marginBottom: 0 }}>Filter project:</label>
          <select value={selected} onChange={(e) => setSelected(e.target.value)} style={{ width: "auto" }}>
            <option value="">All projects</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div className="row">
          <button className="secondary" onClick={acceptAllPending}>Accept all pending</button>
          <button onClick={pushAccepted} disabled={accepted.length === 0}>
            Push {accepted.length} accepted → Jira
          </button>
        </div>
      </div>
      {msg && <div className="ok">{msg}</div>}
      {err && <div className="err">{err}</div>}

      {drafts.length === 0 && <div className="card muted">No ticket drafts.</div>}

      {[...grouped.entries()].map(([pid, list]) => (
        <div key={pid} style={{ marginTop: 20 }}>
          <h3>{projectName(pid)}</h3>
          {list.map((d) => (
            <div key={d.id} className="card">
              <div className="row spread">
                <div style={{ flex: 1 }}>
                  {editing === d.id ? (
                    <>
                      <label>Title</label>
                      <input value={form.title ?? ""} onChange={(e) => setForm({ ...form, title: e.target.value })} />
                      <label style={{ marginTop: 8 }}>Description</label>
                      <textarea value={form.description ?? ""} onChange={(e) => setForm({ ...form, description: e.target.value })} />
                      <label style={{ marginTop: 8 }}>Acceptance criteria (one per line)</label>
                      <textarea
                        value={(form.acceptance_criteria ?? []).join("\n")}
                        onChange={(e) => setForm({ ...form, acceptance_criteria: e.target.value.split("\n").filter(Boolean) })}
                      />
                      <div className="grid grid-2" style={{ marginTop: 8 }}>
                        <div>
                          <label>Issue type</label>
                          <select value={form.issue_type ?? "Story"} onChange={(e) => setForm({ ...form, issue_type: e.target.value })}>
                            <option>Story</option><option>Task</option><option>Bug</option><option>Epic</option>
                          </select>
                        </div>
                        <div>
                          <label>Priority</label>
                          <select value={form.priority ?? "Medium"} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                            <option>Highest</option><option>High</option><option>Medium</option><option>Low</option><option>Lowest</option>
                          </select>
                        </div>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="row spread">
                        <strong>{d.title}</strong>
                        <div className="row">
                          <span className="badge">{d.issue_type}</span>
                          <span className="badge">{d.priority}</span>
                          <span className={`badge ${d.status}`}>{d.status}</span>
                          {d.jira_issue_key && <span className="badge">{d.jira_issue_key}</span>}
                        </div>
                      </div>
                      <div style={{ marginTop: 8 }}>{d.description}</div>
                      {d.acceptance_criteria.length > 0 && (
                        <ul style={{ marginTop: 8 }}>
                          {d.acceptance_criteria.map((ac, i) => <li key={i}>{ac}</li>)}
                        </ul>
                      )}
                      {d.push_error && <div className="err">Push error: {d.push_error}</div>}
                    </>
                  )}
                </div>
              </div>
              <div className="row" style={{ marginTop: 12 }}>
                {editing === d.id ? (
                  <>
                    <button onClick={() => saveEdit(d.id)}>Save</button>
                    <button className="secondary" onClick={() => setEditing(null)}>Cancel</button>
                  </>
                ) : (
                  <>
                    {d.status !== "pushed" && <button className="secondary" onClick={() => startEdit(d)}>Edit</button>}
                    {d.status !== "accepted" && d.status !== "pushed" && <button onClick={() => accept(d.id)}>Accept</button>}
                    {d.status !== "rejected" && d.status !== "pushed" && <button className="danger" onClick={() => reject(d.id)}>Reject</button>}
                    {d.status === "push_failed" && <button onClick={() => retry(d.id)}>Retry push</button>}
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
