import { useEffect, useState } from "react";
import { api } from "../api";
import type { AppSettings, GeminiModel, ModelConfig } from "../types";

export default function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [model, setModel] = useState<ModelConfig | null>(null);
  const [availableModels, setAvailableModels] = useState<GeminiModel[]>([]);
  const [modelsSource, setModelsSource] = useState<"api" | "fallback" | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    const [s, m, models] = await Promise.all([
      api.getSettings(),
      api.getDefaultModelConfig(),
      api.listGeminiModels(),
    ]);
    setSettings(s);
    setModel(m);
    setAvailableModels(models.models);
    setModelsSource(models.source);
    setModelsError(models.error ?? null);
  }
  useEffect(() => { load(); }, []);

  async function saveSettings() {
    if (!settings) return;
    try {
      await api.setSettings({
        implementation_trigger_mode: settings.implementation_trigger_mode,
        poll_interval_seconds: settings.poll_interval_seconds,
        auto_trigger_jira_status: settings.auto_trigger_jira_status,
      });
      setMsg("Settings saved.");
    } catch (e) { setErr(String(e)); }
  }
  async function saveApiKey() {
    if (!settings) return;
    if (!apiKeyInput.trim()) return;
    try {
      const s = await api.setSettings({
        implementation_trigger_mode: settings.implementation_trigger_mode,
        poll_interval_seconds: settings.poll_interval_seconds,
        auto_trigger_jira_status: settings.auto_trigger_jira_status,
        gemini_api_key: apiKeyInput.trim(),
      });
      setSettings(s);
      setApiKeyInput("");
      setMsg("Gemini API key saved.");
      const models = await api.listGeminiModels();
      setAvailableModels(models.models);
      setModelsSource(models.source);
      setModelsError(models.error ?? null);
    } catch (e) { setErr(String(e)); }
  }
  async function clearApiKey() {
    if (!settings) return;
    if (!confirm("Clear the stored Gemini API key? The app will fall back to the GEMINI_API_KEY env var, if set.")) return;
    try {
      const s = await api.setSettings({
        implementation_trigger_mode: settings.implementation_trigger_mode,
        poll_interval_seconds: settings.poll_interval_seconds,
        auto_trigger_jira_status: settings.auto_trigger_jira_status,
        gemini_api_key: "",
      });
      setSettings(s);
      setMsg("Gemini API key cleared.");
    } catch (e) { setErr(String(e)); }
  }
  async function saveModel() {
    if (!model) return;
    try {
      await api.setDefaultModelConfig({
        chat_model: model.chat_model,
        coding_model: model.coding_model,
        chat_model_params: model.chat_model_params,
        coding_model_params: model.coding_model_params,
      });
      setMsg("Default model config saved.");
    } catch (e) { setErr(String(e)); }
  }

  if (!settings || !model) return <div>Loading…</div>;

  return (
    <div>
      <h2>Settings</h2>
      {msg && <div className="ok">{msg}</div>}
      {err && <div className="err">{err}</div>}

      <div className="card">
        <h3>Gemini API key</h3>
        <div className="row spread">
          <div className="muted">
            {settings.gemini_api_key_set
              ? "A key is stored (encrypted at rest). Enter a new value below to replace it."
              : "No key stored. The app will fall back to the GEMINI_API_KEY env var if set."}
          </div>
          <span className={`badge ${settings.gemini_api_key_set ? "accepted" : "pending"}`}>
            {settings.gemini_api_key_set ? "configured" : "not set"}
          </span>
        </div>
        <div style={{ marginTop: 12 }}>
          <label>API key</label>
          <input
            type="password"
            value={apiKeyInput}
            onChange={(e) => setApiKeyInput(e.target.value)}
            placeholder={settings.gemini_api_key_set ? "•••• (leave empty to keep current)" : "AIza…"}
            autoComplete="off"
          />
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <button onClick={saveApiKey} disabled={!apiKeyInput.trim()}>Save API key</button>
          {settings.gemini_api_key_set && (
            <button className="secondary" onClick={clearApiKey}>Clear stored key</button>
          )}
        </div>
      </div>

      <div className="card">
        <h3>Implementation trigger</h3>
        <div className="grid grid-2">
          <div>
            <label>Mode</label>
            <select
              value={settings.implementation_trigger_mode}
              onChange={(e) => setSettings({ ...settings, implementation_trigger_mode: e.target.value })}
            >
              <option value="manual">Manual</option>
              <option value="auto_poll">Auto (poll Jira)</option>
            </select>
          </div>
          <div>
            <label>Poll interval (seconds)</label>
            <input
              type="number"
              value={settings.poll_interval_seconds}
              onChange={(e) => setSettings({ ...settings, poll_interval_seconds: Number(e.target.value) })}
            />
          </div>
          <div>
            <label>Auto-trigger Jira status</label>
            <input
              value={settings.auto_trigger_jira_status}
              onChange={(e) => setSettings({ ...settings, auto_trigger_jira_status: e.target.value })}
            />
          </div>
        </div>
        <div style={{ marginTop: 12 }}>
          <button onClick={saveSettings}>Save settings</button>
        </div>
      </div>

      <div className="card">
        <h3>Default models</h3>
        <div className="grid grid-2">
          <div>
            <label>Chat model</label>
            <select value={model.chat_model} onChange={(e) => setModel({ ...model, chat_model: e.target.value })}>
              {availableModels.every((m) => m.name !== model.chat_model) && (
                <option value={model.chat_model}>{model.chat_model} (current)</option>
              )}
              {availableModels.map((m) => (
                <option key={m.name} value={m.name}>{m.display_name} ({m.name})</option>
              ))}
            </select>
          </div>
          <div>
            <label>Coding model</label>
            <select value={model.coding_model} onChange={(e) => setModel({ ...model, coding_model: e.target.value })}>
              {availableModels.every((m) => m.name !== model.coding_model) && (
                <option value={model.coding_model}>{model.coding_model} (current)</option>
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
            ? `Could not list models from the API${modelsError ? ` (${modelsError.slice(0, 120)}…)` : ""}. Using fallback list — check your GEMINI_API_KEY.`
            : `${availableModels.length} models available for this API key. Projects can override these.`}
        </div>
      </div>
    </div>
  );
}
