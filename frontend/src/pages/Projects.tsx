import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { Project } from "../types";

export default function Projects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const load = () => api.listProjects().then(setProjects).catch((e) => setErr(String(e)));
  useEffect(() => { load(); }, []);

  async function create() {
    if (!name.trim()) return;
    try {
      await api.createProject(name.trim(), description.trim() || undefined);
      setName(""); setDescription(""); setErr(null);
      load();
    } catch (e) { setErr(String(e)); }
  }

  async function remove(p: Project) {
    if (!confirm(`Delete project "${p.name}"?\n\nThis permanently removes its config, chat sessions, ticket drafts, and agent runs. This cannot be undone.`)) return;
    try {
      await api.deleteProject(p.id);
      load();
    } catch (e) { setErr(String(e)); }
  }

  return (
    <div>
      <h2>Projects</h2>

      <div className="card">
        <h3>Create project</h3>
        <div className="grid grid-2">
          <div>
            <label>Name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="My Project" />
          </div>
          <div>
            <label>Description</label>
            <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Optional" />
          </div>
        </div>
        <div style={{ marginTop: 12 }}>
          <button onClick={create}>Create</button>
        </div>
        {err && <div className="err">{err}</div>}
      </div>

      <div className="card">
        <h3>Your projects</h3>
        {projects.length === 0 ? (
          <div className="muted">No projects yet.</div>
        ) : (
          <table>
            <thead>
              <tr><th>Name</th><th>Description</th><th>Trigger</th><th></th></tr>
            </thead>
            <tbody>
              {projects.map((p) => (
                <tr key={p.id}>
                  <td><Link to={`/projects/${p.id}`}>{p.name}</Link></td>
                  <td>{p.description || <span className="muted">—</span>}</td>
                  <td><span className="badge">{p.implementation_trigger_mode || "inherit"}</span></td>
                  <td style={{ textAlign: "right" }}>
                    <div className="row" style={{ justifyContent: "flex-end" }}>
                      <Link to={`/projects/${p.id}/chat`}>
                        <button className="secondary">Brainstorm</button>
                      </Link>
                      <button className="danger" onClick={() => remove(p)}>Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
