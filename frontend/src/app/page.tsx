"use client";

import React, { useState, useEffect, useRef } from "react";
import { 
  FileText, GitBranch, Settings, Activity, Upload, Link, AlertTriangle, 
  CheckCircle, Play, Database, Server, RefreshCw, Terminal, Layers,
  Send, Bot, MessageSquare, User
} from "lucide-react";

type ChatMessage = {
  id: string;
  role: "user" | "agent";
  type: "log" | "input_required" | "chat_response" | "user_message";
  content: string;
  level?: string;
  jobId?: string;
};

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<"spec" | "dag" | "jobs" | "settings">("spec");
  
  // Settings State
  const [configs, setConfigs] = useState<Record<string, string>>({});
  const [isSavingConfig, setIsSavingConfig] = useState(false);
  
  // Spec Upload State
  const [sourceType, setSourceType] = useState<"text" | "pdf" | "url">("text");
  const [textContent, setTextContent] = useState("");
  const [specFile, setSpecFile] = useState<File | null>(null);
  const [specUrl, setSpecUrl] = useState("");
  const [isUploadingSpec, setIsUploadingSpec] = useState(false);
  const [currentSpecId, setCurrentSpecId] = useState<number | null>(null);
  const [parsedStories, setParsedStories] = useState<any[]>([]);
  const [selectedStories, setSelectedStories] = useState<Record<string, boolean>>({});
  const [isCreatingTickets, setIsCreatingTickets] = useState(false);

  // Tickets & DAG State
  const [tickets, setTickets] = useState<any[]>([]);
  const [isLoadingTickets, setIsLoadingTickets] = useState(false);
  const [selectedTicketsToImplement, setSelectedTicketsToImplement] = useState<Record<string, boolean>>({});
  const [dagData, setDagData] = useState<Record<string, string[]>>({});
  const [isBuildingDag, setIsBuildingDag] = useState(false);

  // Jobs & WebSocket State
  const [jobs, setJobs] = useState<any[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [logs, setLogs] = useState<Array<{ message: string; level: string; job_id?: string }>>([]);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const socketRef = useRef<WebSocket | null>(null);

  // Chat state — unified message stream for the Spec tab
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [pendingInputJobId, setPendingInputJobId] = useState<string | null>(null);
  const [isSendingChat, setIsSendingChat] = useState(false);
  const [isAgentThinking, setIsAgentThinking] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Repo input modal state (triggered when agent needs repo name)
  const [repoInputModal, setRepoInputModal] = useState<{ visible: boolean; jobId: string; prompt: string }>({ visible: false, jobId: "", prompt: "" });
  const [repoInputValue, setRepoInputValue] = useState("");

  // API_BASE is now empty — all /api/* calls go through Next.js rewrites proxy
  const API_BASE = "";
  // WebSocket must connect directly to FastAPI (Next.js can't proxy WS rewrites)
  const WS_BASE = "ws://localhost:8000";

  // Connect to WebSocket
  useEffect(() => {
    const ws = new WebSocket(`${WS_BASE}/ws/logs`);
    socketRef.current = ws;

    ws.onopen = () => {
      console.log("WebSocket connected to log server");
      setLogs((prev) => [...prev, { message: "System: Connected to real-time log agent stream.", level: "INFO" }]);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (data.type === "log") {
          // Feed the Jobs tab terminal
          setLogs((prev) => [...prev, { message: data.message, level: data.level, job_id: data.job_id }]);
          if (data.job_id && !activeJobId) setActiveJobId(data.job_id);
          // A log means the agent is actively doing work — dismiss the idle thinking indicator
          setIsAgentThinking(false);
          // Feed the Spec chat as a compact agent log line
          setChatMessages((prev) => [...prev, {
            id: `log-${Date.now()}-${Math.random()}`,
            role: "agent",
            type: "log",
            content: data.message,
            level: data.level,
            jobId: data.job_id,
          }]);
        } else if (data.type === "thinking") {
          // Heartbeat — agent is alive but no new log yet
          setIsAgentThinking(true);
        } else if (data.type === "input_required") {
          // Agent is asking a question — show inline in chat, not a modal
          setChatMessages((prev) => [...prev, {
            id: `input-${Date.now()}`,
            role: "agent",
            type: "input_required",
            content: data.prompt || "Please provide the requested information:",
            jobId: data.job_id,
          }]);
          setPendingInputJobId(data.job_id || null);
          // Still feed the log terminal as a warning line
          setLogs((prev) => [...prev, { message: `⚠ Agent input required: ${data.prompt}`, level: "WARNING", job_id: data.job_id }]);
        } else if (data.type === "chat_response") {
          // Final supervisor response
          setIsAgentThinking(false);
          setChatMessages((prev) => [...prev, {
            id: `resp-${Date.now()}`,
            role: "agent",
            type: "chat_response",
            content: data.message,
            jobId: data.job_id,
          }]);
        }
      } catch (err) {
        setLogs((prev) => [...prev, { message: event.data, level: "INFO" }]);
      }
    };

    ws.onclose = () => {
      console.log("WebSocket closed");
      setLogs((prev) => [...prev, { message: "System: Log stream disconnected.", level: "WARNING" }]);
    };

    return () => {
      ws.close();
    };
  }, []);

  // Scroll to bottom of logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // Scroll to bottom of chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  // Load Configs
  const fetchConfigs = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/config`);
      const data = await res.json();
      setConfigs(data);
    } catch (err) {
      console.error("Failed to load configs", err);
    }
  };

  // Load Tickets
  const fetchTickets = async () => {
    setIsLoadingTickets(true);
    try {
      const res = await fetch(`${API_BASE}/api/tickets`);
      const data = await res.json();
      if (Array.isArray(data)) {
        setTickets(data);
      }
    } catch (err) {
      console.error("Failed to fetch tickets", err);
    } finally {
      setIsLoadingTickets(false);
    }
  };

  // Load Jobs
  const fetchJobs = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/jobs`);
      const data = await res.json();
      if (Array.isArray(data)) {
        setJobs(data);
      }
    } catch (err) {
      console.error("Failed to fetch jobs", err);
    }
  };

  useEffect(() => {
    fetchConfigs();
    fetchTickets();
    fetchJobs();
  }, []);

  // Send repo name back to the backend when agent asks for it (legacy modal, kept for Jobs tab compat)
  const handleRepoInputSubmit = async () => {
    if (!repoInputValue.trim()) return;
    try {
      await fetch(`${API_BASE}/api/jobs/input_response`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: repoInputModal.jobId, value: repoInputValue.trim() }),
      });
      setLogs((prev) => [...prev, { message: `✅ Repo name provided: ${repoInputValue.trim()}`, level: "SUCCESS", job_id: repoInputModal.jobId }]);
    } catch (err) {
      console.error("Failed to send repo input", err);
    } finally {
      setRepoInputModal({ visible: false, jobId: "", prompt: "" });
      setRepoInputValue("");
    }
  };

  // Chat input submit — handles both free-form messages and agent input responses
  const handleChatSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = chatInput.trim();
    if (!text || isSendingChat) return;

    // Optimistically add user message to chat
    setChatMessages((prev) => [...prev, {
      id: `user-${Date.now()}`,
      role: "user",
      type: "user_message",
      content: text,
    }]);
    setChatInput("");
    setIsSendingChat(true);

    try {
      if (pendingInputJobId) {
        // Resolve agent's pending question (e.g. repo name)
        await fetch(`${API_BASE}/api/jobs/input_response`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ job_id: pendingInputJobId, value: text }),
        });
        setPendingInputJobId(null);
      } else {
        // Free-form message to the supervisor agent
        await fetch(`${API_BASE}/api/chat/message`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text }),
        });
      }
    } catch (err) {
      console.error("Failed to send chat message", err);
    } finally {
      setIsSendingChat(false);
    }
  };

  // Save Config
  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSavingConfig(true);
    try {
      const res = await fetch(`${API_BASE}/api/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(configs),
      });
      if (res.ok) {
        alert("Configuration saved successfully!");
      }
    } catch (err) {
      alert("Failed to save config");
    } finally {
      setIsSavingConfig(false);
    }
  };

  // Submit Spec
  const handleUploadSpec = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsUploadingSpec(true);
    setParsedStories([]);
    
    try {
      const formData = new FormData();
      formData.append("source_type", sourceType);
      
      if (sourceType === "text") {
        formData.append("content", textContent);
      } else if (sourceType === "url") {
        formData.append("content", specUrl);
      } else if (sourceType === "pdf" && specFile) {
        formData.append("file", specFile);
      } else {
        alert("Please provide the correct specification source.");
        setIsUploadingSpec(false);
        return;
      }

      const res = await fetch(`${API_BASE}/api/spec`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      
      if (data.job_id) {
        setActiveJobId(data.job_id);
        setCurrentSpecId(data.spec_id);
        setLogs((prev) => [...prev, { message: `Spec upload received. Processing job: ${data.job_id}`, level: "INFO" }]);
        // Stay on spec tab — chat shows progress in real time
        
        // Start polling for parsed stories
        pollSpecStatus(data.spec_id);
      }
    } catch (err) {
      alert("Failed to process specification");
    } finally {
      setIsUploadingSpec(false);
    }
  };

  // Poll Spec details for stories
  const pollSpecStatus = (specId: number) => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/spec/${specId}`);
        const data = await res.json();
        if (data.analyzed_stories && data.analyzed_stories.length > 0) {
          setParsedStories(data.analyzed_stories);
          
          // Select all stories by default
          const initialSelection: Record<string, boolean> = {};
          data.analyzed_stories.forEach((s: any) => {
            initialSelection[s.id] = true;
          });
          setSelectedStories(initialSelection);
          
          clearInterval(interval);
          // Stay on spec tab — stories appear in the left panel
        }
      } catch (err) {
        console.error("Polling spec details failed", err);
      }
    }, 3000);
  };

  // Create Jira Tickets Batch
  const handleCreateJiraTickets = async () => {
    if (!currentSpecId) return;
    setIsCreatingTickets(true);
    
    // Filter out only selected stories
    const selected = parsedStories.filter(s => selectedStories[s.id]);
    
    try {
      const res = await fetch(`${API_BASE}/api/tickets/create-batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          spec_id: currentSpecId,
          stories: selected
        }),
      });
      const data = await res.json();
      if (data.job_id) {
        setActiveJobId(data.job_id);
        setLogs((prev) => [...prev, { message: `Jira Batch Ticket Creation job started: ${data.job_id}`, level: "INFO" }]);
        // Stay on spec tab — progress visible in chat
        
        // Clear parsed stories since they are pushed
        setParsedStories([]);
        fetchTickets(); // refresh list
      }
    } catch (err) {
      alert("Failed to submit ticket creation");
    } finally {
      setIsCreatingTickets(false);
    }
  };

  // Build DAG Graph Visual
  const handleBuildDag = async () => {
    setIsBuildingDag(true);
    const selectedTids = Object.keys(selectedTicketsToImplement).filter(k => selectedTicketsToImplement[k]);
    
    if (selectedTids.length === 0) {
      alert("Please select at least one ticket to build the graph.");
      setIsBuildingDag(false);
      return;
    }
    
    try {
      const res = await fetch(`${API_BASE}/api/dag/build`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticket_ids: selectedTids }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to build dependency graph.");
      }
      const data = await res.json();
      setDagData(data.dag);
    } catch (err) {
      console.error(err);
      alert(`Error building dependency graph: ${err instanceof Error ? err.message : err}`);
    } finally {
      setIsBuildingDag(false);
    }
  };

  // Trigger implementation pipeline
  const handleTriggerImplementation = async () => {
    const selectedTids = Object.keys(selectedTicketsToImplement).filter(k => selectedTicketsToImplement[k]);
    if (selectedTids.length === 0) {
      alert("Please select at least one ticket to implement.");
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/api/jobs/implement`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticket_ids: selectedTids }),
      });
      const data = await res.json();
      if (data.job_id) {
        setActiveJobId(data.job_id);
        setLogs((prev) => [...prev, { message: `Implementation scheduled for tickets: ${selectedTids.join(", ")}`, level: "INFO" }]);
        setActiveTab("jobs");
      }
    } catch (err) {
      alert("Failed to trigger implementation");
    }
  };

  return (
    <div className="flex h-screen bg-[#0d0e12] text-[#e2e8f0] font-sans overflow-hidden">
      
      {/* Sidebar Navigation */}
      <aside className="w-72 bg-[#14161f] border-r border-[#202433] flex flex-col justify-between">
        <div>
          <div className="p-6 flex items-center space-x-3 border-b border-[#202433]">
            <Server className="w-8 h-8 text-[#5f69f2] animate-pulse" />
            <div>
              <h1 className="font-bold text-lg tracking-wider text-white">ANTIGRAVITY</h1>
              <p className="text-xs text-[#627094] font-mono">SPEC-DRIVEN AGENT</p>
            </div>
          </div>
          
          <nav className="p-4 space-y-2">
            <button
              onClick={() => setActiveTab("spec")}
              className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg text-sm font-medium transition-all duration-200 ${
                activeTab === "spec"
                  ? "bg-[#5f69f2] text-white shadow-lg shadow-[#5f69f2]/20"
                  : "text-[#808eb5] hover:bg-[#1a1d29] hover:text-white"
              }`}
            >
              <FileText className="w-5 h-5" />
              <span>Specification Analyzer</span>
            </button>
            
            <button
              onClick={() => {
                setActiveTab("dag");
                fetchTickets();
              }}
              className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg text-sm font-medium transition-all duration-200 ${
                activeTab === "dag"
                  ? "bg-[#5f69f2] text-white shadow-lg shadow-[#5f69f2]/20"
                  : "text-[#808eb5] hover:bg-[#1a1d29] hover:text-white"
              }`}
            >
              <GitBranch className="w-5 h-5" />
              <span>Dependency Graph</span>
            </button>
            
            <button
              onClick={() => {
                setActiveTab("jobs");
                fetchJobs();
              }}
              className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg text-sm font-medium transition-all duration-200 ${
                activeTab === "jobs"
                  ? "bg-[#5f69f2] text-white shadow-lg shadow-[#5f69f2]/20"
                  : "text-[#808eb5] hover:bg-[#1a1d29] hover:text-white"
              }`}
            >
              <Activity className="w-5 h-5" />
              <span>Job Monitor & Logs</span>
            </button>
            
            <button
              onClick={() => setActiveTab("settings")}
              className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg text-sm font-medium transition-all duration-200 ${
                activeTab === "settings"
                  ? "bg-[#5f69f2] text-white shadow-lg shadow-[#5f69f2]/20"
                  : "text-[#808eb5] hover:bg-[#1a1d29] hover:text-white"
              }`}
            >
              <Settings className="w-5 h-5" />
              <span>Configuration</span>
            </button>
          </nav>
        </div>
        
        <div className="p-4 border-t border-[#202433] bg-[#0f1118]">
          <div className="flex items-center justify-between text-xs font-mono text-[#627094]">
            <span>Agent Mode:</span>
            <span className={`px-2 py-0.5 rounded text-white font-semibold ${
              configs.AGENT_MODE === "remote" ? "bg-[#3b82f6]" : "bg-[#10b981]"
            }`}>
              {configs.AGENT_MODE || "remote"}
            </span>
          </div>
        </div>
      </aside>

      {/* Main Workspace Panels */}
      <main className="flex-1 flex flex-col overflow-hidden">
        
        {/* Header bar */}
        <header className="h-16 border-b border-[#202433] bg-[#14161f]/50 backdrop-blur flex items-center justify-between px-8">
          <div className="flex items-center space-x-2">
            <span className="text-[#627094] font-mono text-sm">Dashboard</span>
            <span className="text-[#323647] font-mono text-sm">/</span>
            <span className="text-[#a5b4fc] font-mono text-sm capitalize">{activeTab}</span>
          </div>
          
          <div className="flex items-center space-x-4">
            <button 
              onClick={async () => {
                await fetchConfigs();
                await fetchTickets();
                await fetchJobs();
              }}
              className="p-2 text-[#808eb5] hover:text-white rounded-lg hover:bg-[#1a1d29] transition-colors"
              title="Refresh all data"
            >
              <RefreshCw className="w-5 h-5" />
            </button>
          </div>
        </header>

        {/* Content Pane */}
        <div className={`flex-1 overflow-hidden ${activeTab === "spec" ? "p-6" : "p-8 overflow-y-auto"}`}>
          
          {/* TAB 1: SPECIFICATION ANALYZER + AGENT CHAT */}
          {activeTab === "spec" && (
            <div className="flex gap-6 h-[calc(100vh-8rem)]">

              {/* LEFT PANEL: Upload form + Parsed stories */}
              <div className="w-[420px] flex-shrink-0 flex flex-col gap-4 overflow-y-auto pr-1">
                <div className="bg-[#14161f] border border-[#202433] rounded-xl p-5 shadow-xl">
                  <h2 className="text-lg font-bold text-white mb-1">Upload Specification</h2>
                  <p className="text-xs text-[#808eb5] mb-4">Paste a spec, upload a PDF, or provide a URL to generate user stories.</p>

                  <form onSubmit={handleUploadSpec} className="space-y-4">
                    <div className="flex space-x-2 border-b border-[#202433] pb-3">
                      {(["text", "pdf", "url"] as const).map((t) => (
                        <button key={t} type="button" onClick={() => setSourceType(t)}
                          className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
                            sourceType === t ? "bg-[#5f69f2] text-white" : "text-[#808eb5] hover:text-white"
                          }`}>
                          {t === "text" ? "Markdown" : t === "pdf" ? "PDF" : "URL"}
                        </button>
                      ))}
                    </div>

                    {sourceType === "text" && (
                      <textarea value={textContent} onChange={(e) => setTextContent(e.target.value)}
                        placeholder="Paste specification content here..."
                        className="w-full h-40 bg-[#090a0f] border border-[#202433] rounded-lg p-3 font-mono text-xs text-white focus:outline-none focus:border-[#5f69f2] resize-none"
                      />
                    )}
                    {sourceType === "pdf" && (
                      <div className="flex flex-col items-center justify-center border-2 border-dashed border-[#202433] rounded-lg p-6 hover:border-[#5f69f2] transition-colors bg-[#090a0f]">
                        <Upload className="w-8 h-8 text-[#627094] mb-2" />
                        <label className="cursor-pointer bg-[#14161f] border border-[#202433] hover:bg-[#1a1d29] px-3 py-1.5 rounded-lg text-xs text-white font-semibold">
                          Select PDF
                          <input type="file" accept=".pdf" onChange={(e) => setSpecFile(e.target.files?.[0] || null)} className="hidden" />
                        </label>
                        {specFile && <p className="mt-2 text-xs text-[#a5b4fc] font-mono">{specFile.name}</p>}
                      </div>
                    )}
                    {sourceType === "url" && (
                      <div className="flex items-center space-x-2">
                        <Link className="w-4 h-4 text-[#627094] flex-shrink-0" />
                        <input type="url" value={specUrl} onChange={(e) => setSpecUrl(e.target.value)}
                          placeholder="https://example.com/spec-doc"
                          className="flex-1 bg-[#090a0f] border border-[#202433] rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-[#5f69f2]"
                        />
                      </div>
                    )}

                    <button type="submit" disabled={isUploadingSpec}
                      className="w-full bg-[#5f69f2] hover:bg-[#4852d9] disabled:bg-[#323647] text-white px-4 py-2.5 rounded-lg text-sm font-semibold transition-all">
                      {isUploadingSpec ? "Analyzing..." : "Run Analysis Pipeline"}
                    </button>
                  </form>
                </div>

                {/* Parsed stories review */}
                {parsedStories.length > 0 && (
                  <div className="bg-[#14161f] border border-[#202433] rounded-xl p-5 shadow-xl space-y-4">
                    <div className="flex items-center justify-between border-b border-[#202433] pb-3">
                      <div>
                        <h2 className="text-md font-bold text-white">Review Stories</h2>
                        <p className="text-xs text-[#808eb5]">Select stories to push to Jira.</p>
                      </div>
                      <button onClick={handleCreateJiraTickets} disabled={isCreatingTickets}
                        className="bg-[#10b981] hover:bg-[#059669] disabled:bg-[#323647] text-white px-4 py-2 rounded-lg text-xs font-semibold transition-all">
                        {isCreatingTickets ? "Pushing..." : "Push to Jira"}
                      </button>
                    </div>
                    <div className="space-y-3 max-h-[400px] overflow-y-auto pr-1">
                      {parsedStories.map((story) => (
                        <div key={story.id} className="border border-[#202433] rounded-lg p-3 bg-[#090a0f]">
                          <div className="flex items-start space-x-2">
                            <input type="checkbox" checked={!!selectedStories[story.id]}
                              onChange={(e) => setSelectedStories({ ...selectedStories, [story.id]: e.target.checked })}
                              className="mt-0.5 w-4 h-4 rounded border-[#202433] text-[#5f69f2] focus:ring-0"
                            />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center space-x-2 flex-wrap gap-1">
                                <span className="px-1.5 py-0.5 bg-[#1e293b] text-[#94a3b8] rounded font-mono text-[10px]">{story.id}</span>
                                <h3 className="font-semibold text-white text-xs">{story.title}</h3>
                              </div>
                              <p className="text-xs text-[#808eb5] mt-1 line-clamp-2">{story.description}</p>
                              {story.acceptance_criteria && (
                                <div className="mt-2 bg-[#14161f] p-2 rounded border border-[#202433]/50">
                                  <ul className="list-disc pl-3 text-[10px] text-[#94a3b8] space-y-0.5">
                                    {story.acceptance_criteria.slice(0, 3).map((ac: string, idx: number) => (
                                      <li key={idx}>{ac}</li>
                                    ))}
                                    {story.acceptance_criteria.length > 3 && (
                                      <li className="text-[#627094]">+{story.acceptance_criteria.length - 3} more...</li>
                                    )}
                                  </ul>
                                </div>
                              )}
                              {story.dependencies && story.dependencies.length > 0 && (
                                <div className="mt-2 flex items-center space-x-1 text-[10px] font-mono text-[#f59e0b]">
                                  <AlertTriangle className="w-3 h-3" />
                                  <span>Depends on: {story.dependencies.join(", ")}</span>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* RIGHT PANEL: Agent Chat */}
              <div className="flex-1 flex flex-col bg-[#14161f] border border-[#202433] rounded-xl overflow-hidden shadow-xl min-h-0">
                {/* Chat header */}
                <div className="flex items-center gap-3 px-5 py-3.5 border-b border-[#202433] flex-shrink-0">
                  <div className="w-8 h-8 rounded-full bg-[#5f69f2]/20 flex items-center justify-center">
                    <Bot className="w-4 h-4 text-[#a5b4fc]" />
                  </div>
                  <div>
                    <h3 className="font-bold text-white text-sm">Agent Chat</h3>
                    <p className="text-[10px] text-[#627094]">Real-time communication · logs · questions · responses</p>
                  </div>
                  {pendingInputJobId && (
                    <div className="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-yellow-500/10 border border-yellow-500/30">
                      <div className="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse" />
                      <span className="text-[10px] font-semibold text-yellow-400">Waiting for input</span>
                    </div>
                  )}
                </div>

                {/* Messages area */}
                <div className="flex-1 overflow-y-auto p-4 space-y-1.5 min-h-0">
                  {chatMessages.length === 0 && (
                    <div className="flex flex-col items-center justify-center h-full text-center py-16">
                      <MessageSquare className="w-12 h-12 text-[#202433] mx-auto mb-3" />
                      <p className="text-sm text-[#3d4566] font-medium">No agent activity yet</p>
                      <p className="text-xs text-[#2a2d3e] mt-1">Upload a spec or send a message to start.</p>
                    </div>
                  )}

                  {chatMessages.map((msg) => {
                    // User message
                    if (msg.role === "user") {
                      return (
                        <div key={msg.id} className="flex justify-end pt-1">
                          <div className="flex items-end gap-2 max-w-[75%]">
                            <div className="bg-[#5f69f2] text-white px-4 py-2.5 rounded-2xl rounded-tr-sm text-sm shadow-md">
                              {msg.content}
                            </div>
                            <div className="w-6 h-6 rounded-full bg-[#202433] flex items-center justify-center flex-shrink-0 mb-0.5">
                              <User className="w-3 h-3 text-[#808eb5]" />
                            </div>
                          </div>
                        </div>
                      );
                    }

                    // Agent input request
                    if (msg.type === "input_required") {
                      return (
                        <div key={msg.id} className="flex items-start gap-2 pt-2">
                          <div className="w-7 h-7 rounded-full bg-yellow-500/15 border border-yellow-500/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                            <AlertTriangle className="w-3.5 h-3.5 text-yellow-400" />
                          </div>
                          <div className="bg-[#1a1d29] border border-yellow-500/25 px-4 py-3 rounded-2xl rounded-tl-sm max-w-[80%] shadow-md">
                            <p className="text-yellow-300 text-sm font-medium leading-relaxed">{msg.content}</p>
                            <p className="text-[10px] text-[#627094] mt-1.5 flex items-center gap-1">
                              <span className="inline-block w-1 h-1 rounded-full bg-yellow-400 animate-pulse" />
                              Type your response in the input below
                            </p>
                          </div>
                        </div>
                      );
                    }

                    // Agent final response (chat_response)
                    if (msg.type === "chat_response") {
                      return (
                        <div key={msg.id} className="flex items-start gap-2 pt-2">
                          <div className="w-7 h-7 rounded-full bg-[#5f69f2]/15 border border-[#5f69f2]/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                            <Bot className="w-3.5 h-3.5 text-[#a5b4fc]" />
                          </div>
                          <div className="bg-[#1a1d29] border border-[#5f69f2]/20 px-4 py-3 rounded-2xl rounded-tl-sm max-w-[80%] text-sm text-[#e2e8f0] whitespace-pre-wrap leading-relaxed shadow-md">
                            {msg.content}
                          </div>
                        </div>
                      );
                    }

                    // Compact log line
                    let logColor = "text-[#4a5568]";
                    if (msg.level === "ERROR") logColor = "text-red-400/80";
                    if (msg.level === "WARNING") logColor = "text-yellow-400/80";
                    if (msg.level === "SUCCESS") logColor = "text-green-400/80";
                    return (
                      <div key={msg.id} className="flex items-start gap-2 pl-1">
                        <div className="w-1.5 h-1.5 rounded-full bg-[#2a2d3e] mt-1.5 flex-shrink-0" />
                        <p className={`font-mono text-[11px] ${logColor} leading-relaxed`}>{msg.content}</p>
                      </div>
                    );
                  })}

                  {/* Thinking indicator — pulsing dots when heartbeat fires */}
                  {isAgentThinking && (
                    <div className="flex items-start gap-2 pt-1">
                      <div className="w-7 h-7 rounded-full bg-[#5f69f2]/10 border border-[#5f69f2]/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                        <Bot className="w-3.5 h-3.5 text-[#5f69f2]/60" />
                      </div>
                      <div className="bg-[#1a1d29] border border-[#202433] px-4 py-3 rounded-2xl rounded-tl-sm shadow-sm flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#5f69f2] animate-bounce [animation-delay:0ms]" />
                        <span className="w-1.5 h-1.5 rounded-full bg-[#5f69f2] animate-bounce [animation-delay:150ms]" />
                        <span className="w-1.5 h-1.5 rounded-full bg-[#5f69f2] animate-bounce [animation-delay:300ms]" />
                      </div>
                    </div>
                  )}

                  <div ref={chatEndRef} />
                </div>

                {/* Chat input bar */}
                <div className={`flex-shrink-0 border-t px-4 py-3 transition-colors duration-300 ${
                  pendingInputJobId
                    ? "border-yellow-500/30 bg-yellow-500/5"
                    : "border-[#202433] bg-[#14161f]"
                }`}>
                  {pendingInputJobId && (
                    <div className="flex items-center gap-1.5 text-[11px] text-yellow-400 mb-2 font-medium">
                      <AlertTriangle className="w-3 h-3" />
                      <span>Agent is waiting — type your response below</span>
                    </div>
                  )}
                  <form onSubmit={handleChatSubmit} className="flex gap-2">
                    <input
                      value={chatInput}
                      onChange={(e) => setChatInput(e.target.value)}
                      placeholder={
                        pendingInputJobId
                          ? "Type your response to the agent..."
                          : "Send a command or question (e.g. 'implement PROJ-1', 'list tickets')..."
                      }
                      disabled={isSendingChat}
                      className="flex-1 bg-[#090a0f] border border-[#202433] focus:border-[#5f69f2] rounded-xl px-4 py-2.5 text-sm text-white placeholder-[#2d3147] focus:outline-none transition-colors disabled:opacity-50"
                    />
                    <button
                      type="submit"
                      disabled={!chatInput.trim() || isSendingChat}
                      className="bg-[#5f69f2] hover:bg-[#4852d9] disabled:bg-[#1e2035] disabled:cursor-not-allowed text-white px-4 py-2.5 rounded-xl transition-colors shadow-md shadow-[#5f69f2]/10 flex-shrink-0"
                    >
                      <Send className="w-4 h-4" />
                    </button>
                  </form>
                </div>
              </div>

            </div>
          )}

          {/* TAB 2: DEPENDENCY GRAPH & TOPOLOGICAL SORT */}
          {activeTab === "dag" && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                
                {/* Available Jira Tickets Selection Card */}
                <div className="bg-[#14161f] border border-[#202433] rounded-xl p-6 shadow-xl lg:col-span-1 flex flex-col max-h-[600px]">
                  <h3 className="text-lg font-bold text-white mb-2">Select Tickets for DAG</h3>
                  <p className="text-xs text-[#808eb5] mb-4">Choose tickets to analyze and implement.</p>

                  <div className="flex-1 overflow-y-auto space-y-2 mb-4 pr-2">
                    {isLoadingTickets ? (
                      <p className="text-sm text-[#627094]">Loading available tickets...</p>
                    ) : tickets.length === 0 ? (
                      <p className="text-sm text-[#627094]">No active tickets found.</p>
                    ) : (
                      tickets.map((t) => (
                        <div key={t.id} className="flex items-center space-x-3 p-2 hover:bg-[#1a1d29] rounded transition-colors border border-[#202433]/50 bg-[#090a0f]">
                          <input
                            type="checkbox"
                            checked={!!selectedTicketsToImplement[t.id]}
                            onChange={(e) => setSelectedTicketsToImplement({
                              ...selectedTicketsToImplement,
                              [t.id]: e.target.checked
                            })}
                            className="w-4 h-4 rounded border-[#202433] text-[#5f69f2] focus:ring-0"
                          />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center space-x-2">
                              <span className="text-xs font-mono text-[#a5b4fc]">{t.id}</span>
                              <span className="px-1.5 py-0.5 bg-[#202433] text-[#a1a1aa] rounded text-[10px] font-bold">{t.status}</span>
                            </div>
                            <p className="text-xs text-white truncate mt-1">{t.title}</p>
                          </div>
                        </div>
                      ))
                    )}
                  </div>

                  <div className="space-y-2">
                    <button
                      onClick={handleBuildDag}
                      disabled={isBuildingDag}
                      className="w-full bg-[#1e293b] hover:bg-[#334155] border border-[#334155] text-white px-4 py-2.5 rounded-lg text-sm font-semibold transition"
                    >
                      Build dependency graph
                    </button>
                    
                    <button
                      onClick={handleTriggerImplementation}
                      className="w-full bg-[#5f69f2] hover:bg-[#4852d9] text-white px-4 py-2.5 rounded-lg text-sm font-semibold flex items-center justify-center space-x-2 transition"
                    >
                      <Play className="w-4 h-4" />
                      <span>Implement Selection</span>
                    </button>
                  </div>
                </div>

                {/* Graph Visualization Viewport */}
                <div className="bg-[#14161f] border border-[#202433] rounded-xl p-6 shadow-xl lg:col-span-2 flex flex-col min-h-[500px]">
                  <h3 className="text-lg font-bold text-white mb-2">Topological Execution Graph</h3>
                  <p className="text-xs text-[#808eb5] mb-6">Visual representation of execution layers (left to right).</p>

                  <div className="flex-1 border border-[#202433] rounded-lg bg-[#090a0f] p-8 flex flex-col justify-center items-center overflow-auto">
                    {Object.keys(dagData).length === 0 ? (
                      <div className="text-center">
                        <GitBranch className="w-16 h-16 text-[#323647] mx-auto mb-4" />
                        <p className="text-sm text-[#627094]">No dependency graph built yet.</p>
                      </div>
                    ) : (
                      <div className="flex items-center space-x-12">
                        {Object.keys(dagData).map((node, index) => {
                          const successors = dagData[node] || [];
                          return (
                            <div key={node} className="flex items-center">
                              <div className="flex flex-col items-center bg-[#14161f] border-2 border-[#5f69f2] rounded-xl p-4 shadow-lg min-w-[120px]">
                                <span className="font-mono text-xs text-[#a5b4fc] mb-1">LAYER {index}</span>
                                <span className="font-bold text-white text-sm">{node}</span>
                                <span className="text-[10px] text-[#627094] mt-2 font-semibold bg-[#090a0f] px-2 py-0.5 rounded">PENDING</span>
                              </div>
                              
                              {successors.length > 0 && (
                                <div className="w-12 h-0.5 bg-[#202433] relative">
                                  <div className="absolute right-0 -top-1 w-2.5 h-2.5 border-t-2 border-r-2 border-[#202433] rotate-45" />
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>

              </div>
            </div>
          )}

          {/* TAB 3: JOBS & WEBSOCKET LOGS */}
          {activeTab === "jobs" && (
            <div className="space-y-6">
              
              {/* Jobs History list */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                
                <div className="bg-[#14161f] border border-[#202433] rounded-xl p-6 shadow-xl lg:col-span-1 max-h-[600px] flex flex-col">
                  <h3 className="text-lg font-bold text-white mb-2">Job List</h3>
                  <p className="text-xs text-[#808eb5] mb-4">Monitor currently running and past jobs.</p>

                  <div className="flex-1 overflow-y-auto space-y-2 pr-2">
                    {jobs.map((job) => (
                      <button
                        key={job.id}
                        onClick={() => {
                          setActiveJobId(job.id);
                          setLogs([]); // Reset log viewport to poll for this job specifically
                          setLogs([{ message: `Viewing job database snapshot logs for ${job.id}`, level: "INFO" }]);
                          if (job.logs) {
                            setLogs((prev) => [...prev, ...job.logs.split("\n").map((line: string) => ({ message: line, level: "INFO" }))]);
                          }
                        }}
                        className={`w-full text-left p-3 rounded-lg border transition-all ${
                          activeJobId === job.id 
                            ? "bg-[#1f2335] border-[#5f69f2]" 
                            : "bg-[#090a0f] border-[#202433]/50 hover:bg-[#12141c]"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-xs text-white truncate max-w-[120px]">{job.id}</span>
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            job.status === "SUCCESS" 
                              ? "bg-[#059669] text-white" 
                              : job.status === "FAILED" 
                              ? "bg-[#dc2626] text-white" 
                              : "bg-[#2563eb] text-white animate-pulse"
                          }`}>
                            {job.status}
                          </span>
                        </div>
                        <p className="text-[10px] text-[#627094] mt-2 font-mono">{new Date(job.created_at).toLocaleString()}</p>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Log Terminal console */}
                <div className="bg-[#14161f] border border-[#202433] rounded-xl p-6 shadow-xl lg:col-span-2 flex flex-col min-h-[500px]">
                  <div className="flex items-center justify-between border-b border-[#202433] pb-4 mb-4">
                    <div className="flex items-center space-x-2">
                      <Terminal className="w-5 h-5 text-[#5f69f2]" />
                      <h3 className="text-lg font-bold text-white">Live Execution Terminal</h3>
                    </div>
                    {activeJobId && (
                      <span className="font-mono text-xs text-[#a5b4fc]">Job ID: {activeJobId.slice(0,8)}...</span>
                    )}
                  </div>

                  <div className="flex-1 bg-[#050608] border border-[#202433] rounded-lg p-6 font-mono text-xs overflow-y-auto max-h-[450px] space-y-1.5 scrollbar-thin">
                    {logs.map((log, index) => {
                      let color = "text-[#94a3b8]";
                      if (log.level === "ERROR") color = "text-red-500 font-semibold";
                      if (log.level === "WARNING") color = "text-yellow-500";
                      if (log.level === "SUCCESS") color = "text-green-400 font-semibold";
                      return (
                        <div key={index} className="flex space-x-2">
                          <span className="text-[#323647] select-none">[{index+1}]</span>
                          <span className={color}>{log.message}</span>
                        </div>
                      );
                    })}
                    <div ref={logsEndRef} />
                  </div>
                </div>

              </div>

            </div>
          )}

          {/* TAB 4: CONFIGURATION SETTINGS */}
          {activeTab === "settings" && (
            <div className="max-w-3xl mx-auto bg-[#14161f] border border-[#202433] rounded-xl p-6 shadow-xl">
              <h2 className="text-xl font-bold text-white mb-2">Configuration Center</h2>
              <p className="text-xs text-[#808eb5] mb-6">Manage global API credentials, agent settings, and local database properties.</p>

              <form onSubmit={handleSaveConfig} className="space-y-6">
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  
                  {/* Left Column: API Keys */}
                  <div className="space-y-4">
                    <h3 className="text-sm font-bold text-[#a5b4fc] tracking-wider uppercase border-b border-[#202433] pb-2">API Keys</h3>
                    
                    <div>
                      <label className="block text-xs font-mono text-[#627094] mb-2">GEMINI API KEY</label>
                      <input
                        type="password"
                        value={configs.GEMINI_API_KEY || ""}
                        onChange={(e) => setConfigs({ ...configs, GEMINI_API_KEY: e.target.value })}
                        className="w-full bg-[#090a0f] border border-[#202433] rounded-lg px-4 py-2 text-xs text-white focus:outline-none focus:border-[#5f69f2]"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-mono text-[#627094] mb-2">GITHUB PERSONAL ACCESS TOKEN</label>
                      <input
                        type="password"
                        value={configs.GITHUB_TOKEN || ""}
                        onChange={(e) => setConfigs({ ...configs, GITHUB_TOKEN: e.target.value })}
                        className="w-full bg-[#090a0f] border border-[#202433] rounded-lg px-4 py-2 text-xs text-white focus:outline-none focus:border-[#5f69f2]"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-mono text-[#627094] mb-2">JIRA API TOKEN</label>
                      <input
                        type="password"
                        value={configs.JIRA_API_TOKEN || ""}
                        onChange={(e) => setConfigs({ ...configs, JIRA_API_TOKEN: e.target.value })}
                        className="w-full bg-[#090a0f] border border-[#202433] rounded-lg px-4 py-2 text-xs text-white focus:outline-none focus:border-[#5f69f2]"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-mono text-[#627094] mb-2">CONTEXT7 API KEY</label>
                      <input
                        type="password"
                        value={configs.CONTEXT7_API_KEY || ""}
                        onChange={(e) => setConfigs({ ...configs, CONTEXT7_API_KEY: e.target.value })}
                        className="w-full bg-[#090a0f] border border-[#202433] rounded-lg px-4 py-2 text-xs text-white focus:outline-none focus:border-[#5f69f2]"
                      />
                    </div>
                  </div>

                  {/* Right Column: Server & Strategy Config */}
                  <div className="space-y-4">
                    <h3 className="text-sm font-bold text-[#a5b4fc] tracking-wider uppercase border-b border-[#202433] pb-2">Target Settings</h3>

                    <div>
                      <label className="block text-xs font-mono text-[#627094] mb-2">JIRA CLOUD URL</label>
                      <input
                        type="url"
                        value={configs.JIRA_URL || ""}
                        onChange={(e) => setConfigs({ ...configs, JIRA_URL: e.target.value })}
                        className="w-full bg-[#090a0f] border border-[#202433] rounded-lg px-4 py-2 text-xs text-white focus:outline-none focus:border-[#5f69f2]"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-mono text-[#627094] mb-2">JIRA USER (EMAIL)</label>
                      <input
                        type="email"
                        value={configs.JIRA_USER || ""}
                        onChange={(e) => setConfigs({ ...configs, JIRA_USER: e.target.value })}
                        className="w-full bg-[#090a0f] border border-[#202433] rounded-lg px-4 py-2 text-xs text-white focus:outline-none focus:border-[#5f69f2]"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-mono text-[#627094] mb-2">GITHUB OWNER (ORG/USER)</label>
                      <input
                        type="text"
                        value={configs.GITHUB_OWNER || ""}
                        onChange={(e) => setConfigs({ ...configs, GITHUB_OWNER: e.target.value })}
                        className="w-full bg-[#090a0f] border border-[#202433] rounded-lg px-4 py-2 text-xs text-white focus:outline-none focus:border-[#5f69f2]"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-mono text-[#627094] mb-2">POSTGRESQL DATABASE URL</label>
                      <input
                        type="text"
                        value={configs.DATABASE_URL || ""}
                        onChange={(e) => setConfigs({ ...configs, DATABASE_URL: e.target.value })}
                        className="w-full bg-[#090a0f] border border-[#202433] rounded-lg px-4 py-2 text-xs text-white focus:outline-none focus:border-[#5f69f2]"
                      />
                    </div>
                  </div>

                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-4 border-t border-[#202433]">
                  <div>
                    <label className="block text-xs font-mono text-[#627094] mb-2">DEVELOPMENT MODE</label>
                    <select
                      value={configs.AGENT_MODE || "remote"}
                      onChange={(e) => setConfigs({ ...configs, AGENT_MODE: e.target.value })}
                      className="w-full bg-[#090a0f] border border-[#202433] rounded-lg px-4 py-2 text-xs text-white focus:outline-none focus:border-[#5f69f2]"
                    >
                      <option value="remote">Remote (Github MCP API)</option>
                      <option value="local">Local (Workspace Folders)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-mono text-[#627094] mb-2">TICKET GENERATION MODEL</label>
                    <input
                      type="text"
                      value={configs.TICKET_MODEL || "gemini-2.5-flash"}
                      onChange={(e) => setConfigs({ ...configs, TICKET_MODEL: e.target.value })}
                      className="w-full bg-[#090a0f] border border-[#202433] rounded-lg px-4 py-2 text-xs text-white focus:outline-none focus:border-[#5f69f2]"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-mono text-[#627094] mb-2">CODING EXPERT MODEL</label>
                    <input
                      type="text"
                      value={configs.CODING_MODEL || "gemini-3.1-pro-preview"}
                      onChange={(e) => setConfigs({ ...configs, CODING_MODEL: e.target.value })}
                      className="w-full bg-[#090a0f] border border-[#202433] rounded-lg px-4 py-2 text-xs text-white focus:outline-none focus:border-[#5f69f2]"
                    />
                  </div>
                </div>

                <div className="flex justify-end pt-4">
                  <button
                    type="submit"
                    disabled={isSavingConfig}
                    className="bg-[#5f69f2] hover:bg-[#4852d9] disabled:bg-[#323647] text-white px-6 py-2.5 rounded-lg text-sm font-semibold transition-all duration-200 shadow-lg shadow-[#5f69f2]/10"
                  >
                    {isSavingConfig ? "Saving Config..." : "Save Settings"}
                  </button>
                </div>
                
              </form>
            </div>
          )}

        </div>
      </main>

    </div>
  );
}
