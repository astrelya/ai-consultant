// SDD Dashboard frontend (Phase 3) — vanilla JS, no build step.

document.addEventListener("DOMContentLoaded", () => {
  renderTabs();
  renderGate();
  initTabs();
  initSse();
});

// Mirrors STATUS_LABELS in app/web.py (French labels).
const STATUS_LABELS = {
  spec_drafting: ["Spécification en cours", "working"],
  pending_spec_approval: ["En attente — validation de la spec", "gate"],
  planning: ["Planification en cours", "working"],
  pending_plan_approval: ["En attente — validation du plan / tâches", "gate"],
  implementing: ["Implémentation en cours", "working"],
  verifying: ["Vérification en cours", "working"],
  completed: ["Terminé", "done"],
  failed: ["Échec", "error"],
};

function renderTabs() {
  if (!window.ARTIFACTS || !window.marked) return;
  for (const key of ["spec.md", "plan.md", "tasks.md"]) {
    const panel = document.getElementById("tab-" + key.replace(".md", ""));
    if (!panel) continue;
    panel.innerHTML = window.ARTIFACTS[key]
      ? marked.parse(window.ARTIFACTS[key])
      : '<p class="muted">Pas encore généré.</p>';
  }
}

function renderGate() {
  const el = document.getElementById("gate-content");
  if (el && window.GATE && window.marked) {
    el.innerHTML = marked.parse(window.GATE.content || "");
  }
}

function initTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const panel = document.getElementById("tab-" + btn.dataset.tab);
      if (panel) panel.classList.add("active");
    });
  });
}

function initSse() {
  if (!window.SSE_URL) return;
  const es = new EventSource(window.SSE_URL);
  const badge = document.getElementById("status-badge");
  const progress = document.getElementById("task-progress");

  es.addEventListener("message", (e) => {
    let ev;
    try { ev = JSON.parse(e.data); } catch { return; }

    if (ev.status && STATUS_LABELS[ev.status] && badge) {
      badge.textContent = STATUS_LABELS[ev.status][0];
      badge.className = "badge badge-" + STATUS_LABELS[ev.status][1];
    }
    if (progress && typeof ev.tasks_total === "number") {
      progress.textContent = `Tâches : ${ev.task_index}/${ev.tasks_total}`;
    }
    // A new gate appeared while the user was watching: reload to show its panel.
    if (ev.pending_gate && !document.getElementById("gate-panel")) location.reload();
    if (!ev.running && !ev.pending_gate && ["completed", "failed"].includes(ev.status)) es.close();
  });
}

async function submitDecision(approved) {
  const feedback = (document.getElementById("gate-feedback")?.value || "").trim();
  const buttons = document.querySelectorAll(".gate-actions .btn");
  buttons.forEach((b) => (b.disabled = true));
  try {
    const res = await fetch(`/api/pipelines/${window.PIPELINE_ID}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved, feedback }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert("Erreur : " + (err.detail || res.status));
      buttons.forEach((b) => (b.disabled = false));
      return;
    }
    const panel = document.getElementById("gate-panel");
    if (panel) {
      panel.innerHTML = approved
        ? "<h2>✓ Approuvé — le pipeline reprend…</h2>"
        : "<h2>✗ Refusé — révision en cours…</h2>";
    }
  } catch (e) {
    alert("Erreur réseau : " + e);
    buttons.forEach((b) => (b.disabled = false));
  }
}
