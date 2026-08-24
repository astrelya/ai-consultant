"use client";

import React, { useState, useRef, useEffect } from 'react';
import { useStream } from '@/lib/sse/useStream';
import ExecutionStatusBlock from './ExecutionStatusBlock';
import TicketCardList from '@/components/TicketCardList';
import type { Ticket } from '@/components/TicketCard';
import { apiClient } from '@/lib/api/client';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';

interface ChatInterfaceProps {
  projectId: string;
}

export default function ChatInterface({ projectId }: ChatInterfaceProps) {
  const { events, isConnected, error } = useStream(projectId);
  const [inputValue, setInputValue] = useState('');
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [showDevView, setShowDevView] = useState(false);
  const [activeMode, setActiveMode] = useState<'brainstorm' | 'spec_review' | 'direct_implementation' | null>(null);
  const [specPreview, setSpecPreview] = useState<string | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [jiraConfigured, setJiraConfigured] = useState(false);

  const [messages, setMessages] = useState<{ id: string; role: 'user' | 'agent'; content: string }[]>([]);

  useEffect(() => {
    async function loadProject() {
      try {
        const project = await apiClient.getProject(projectId);
        setJiraConfigured(!!project.jira_configured);
      } catch (err) {
        console.error('Failed to load project details:', err);
      }
    }
    loadProject();
  }, [projectId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events, messages]);

  // Detect spec_stored events from SSE stream to show spec preview card
  useEffect(() => {
    const latestSpecStored = events
      .filter(ev => ev.type === 'spec_stored')
      .slice(-1)[0];
    if (latestSpecStored) {
      const data = latestSpecStored.data as { preview?: string };
      if (data?.preview) {
        setSpecPreview(data.preview);
      }
    }
  }, [events]);

  // Detect tickets_generated SSE event to show inline ticket cards
  useEffect(() => {
    const latestTicketsEvent = events
      .filter(ev => ev.type === 'tickets_generated')
      .slice(-1)[0];
    if (latestTicketsEvent) {
      const data = latestTicketsEvent.data as { tickets?: Ticket[] };
      if (data?.tickets) {
        setTickets(data.tickets);
      }
    }
  }, [events]);

  // Client-side intent detection for button highlight only (no LLM call)
  const detectModeFromInput = (text: string): 'brainstorm' | 'spec_review' | 'direct_implementation' | null => {
    const lower = text.toLowerCase();
    if (/implement (this|my|the) spec|build (this|my|the) spec|use this spec and build it|execute this spec/.test(lower)) {
      return 'direct_implementation';
    }
    if (/review (this|my|the) spec|analyze (this|my|the) spec|validate (this|my|the) spec|check (this|my|the) spec/.test(lower)) {
      return 'spec_review';
    }
    if (/brainstorm|ideate|idea for|think through|sketch/.test(lower)) {
      return 'brainstorm';
    }
    return null;
  };

  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputValue.trim()) return;

    const userMessage = inputValue.trim();
    setInputValue('');
    setIsSending(true);
    setActiveMode(detectModeFromInput(userMessage));
    setSpecPreview(null);

    setMessages(prev => [...prev, { id: Date.now().toString(), role: 'user', content: userMessage }]);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${apiUrl}/projects/${projectId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage }),
      });

      if (!response.ok) {
        let errorDetail = 'Failed to send message';
        try {
          const errorBody = await response.json();
          if (errorBody && errorBody.detail) {
            errorDetail = typeof errorBody.detail === 'string' ? errorBody.detail : JSON.stringify(errorBody.detail);
          }
        } catch { /* ignore */ }
        throw new Error(errorDetail);
      }
    } catch (err) {
      console.error(err);
      setMessages(prev => [...prev, { id: Date.now().toString(), role: 'agent', content: `❌ Error: ${err instanceof Error ? err.message : 'Failed to send'}` }]);
    } finally {
      setIsSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    // Update mode highlight as user types (client-side only)
    setActiveMode(detectModeFromInput(e.target.value));
  };

  const hasMessages = messages.length > 0 || events.length > 0;

  return (
    <div className="flex flex-col h-full relative">
      {/* Header */}
      <header className="flex-shrink-0 px-4 py-3 border-b border-border flex items-center justify-between bg-background">
        <div className="flex items-center gap-3">
          <h2 className="text-[18px] font-medium tracking-tight">Project Workspace</h2>
          {/* Mode indicator buttons */}
          <div className="flex items-center gap-2">
            <button
              id="brainstorm-mode-btn"
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-all duration-200 ${
                activeMode === 'brainstorm'
                  ? 'bg-primary text-primary-foreground border-primary shadow-sm ring-2 ring-primary/30'
                  : 'bg-muted text-muted-foreground border-transparent'
              }`}
              title="Brainstorm Mode"
              aria-pressed={activeMode === 'brainstorm'}
            >
              💡 Brainstorm
            </button>
            <button
              id="spec-review-mode-btn"
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-all duration-200 ${
                activeMode === 'spec_review'
                  ? 'bg-accent text-accent-foreground border-accent shadow-sm ring-2 ring-accent/30'
                  : 'bg-muted text-muted-foreground border-transparent'
              }`}
              title="Spec Review Mode"
              aria-pressed={activeMode === 'spec_review'}
            >
              🔍 Spec Review
            </button>
            <button
              id="direct-implementation-mode-btn"
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-all duration-200 ${
                activeMode === 'direct_implementation'
                  ? 'bg-success text-success-foreground border-success shadow-sm ring-2 ring-success/30'
                  : 'bg-muted text-muted-foreground border-transparent'
              }`}
              title="Implement Mode"
              aria-pressed={activeMode === 'direct_implementation'}
            >
              ⚡ Implement
            </button>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <Button variant="outline" size="sm" onClick={() => setShowDevView(!showDevView)}>
            {showDevView ? 'Hide Dev View' : 'Show Dev View'}
          </Button>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-success' : 'bg-destructive'}`} />
            <span className="text-sm text-muted-foreground">{isConnected ? 'Connected' : 'Disconnected'}</span>
          </div>
        </div>
      </header>

      {/* Main Content Area (Split if Dev View active) */}
      <div className="flex-1 min-h-0 flex overflow-hidden">
        
        {/* Chat Area */}
        <div className={`flex flex-col h-full transition-all duration-300 ${showDevView ? 'w-[60%] border-r border-border' : 'w-full'}`}>
          <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
            <ExecutionStatusBlock events={events} />

            {/* Spec Preview Card (shown after spec_stored SSE event) */}
            {specPreview && (
              <div id="spec-preview-card" className="rounded-lg border border-accent/40 bg-accent/10 p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <span className="text-base">✅</span>
                  <span className="font-semibold text-sm">
                    {activeMode === 'direct_implementation' ? 'Spec saved and ready for implementation' : 'Spec validated and ready'}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground font-mono whitespace-pre-wrap">{specPreview}</p>
                <div className="flex gap-2 pt-1">
                  <Button
                    id="review-spec-btn"
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setMessages(prev => [...prev, { id: Date.now().toString(), role: 'agent', content: `📄 Full spec:\n\n${specPreview}` }]);
                    }}
                  >
                    Review Spec
                  </Button>
                  <Button
                    id="generate-tickets-btn"
                    size="sm"
                    onClick={() => {
                      setMessages(prev => [...prev, { id: Date.now().toString(), role: 'agent', content: '🎫 Ticket generation will be available in the next update (Story 4.1).' }]);
                    }}
                  >
                    Generate Tickets
                  </Button>
                  <Button
                    id="execute-directly-btn"
                    size="sm"
                    onClick={() => {
                      setMessages(prev => [...prev, { id: Date.now().toString(), role: 'agent', content: '⚡ Direct execution will begin shortly.' }]);
                    }}
                  >
                    Execute Directly
                  </Button>
                </div>
              </div>
            )}

            {/* Ticket Cards (shown after tickets_generated SSE event) */}
            {tickets.length > 0 && (
              <TicketCardList tickets={tickets} projectId={projectId} jiraConfigured={jiraConfigured} />
            )}

            {!hasMessages ? (
              <div className="h-full flex flex-col items-center justify-center text-center text-muted-foreground">
                <p className="text-[18px] font-medium mb-1 text-foreground">Ready to build.</p>
                <p className="text-sm max-w-md">Describe what you want to build, or type 'brainstorm' to get started.</p>
              </div>
            ) : (
              <div className="space-y-6 pb-4">
                {messages.map((msg) => (
                  <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[80%] rounded-lg p-4 ${msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground'}`}>
                      <div className="whitespace-pre-wrap">{msg.content}</div>
                    </div>
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          <div className="flex-shrink-0 p-4 border-t border-border bg-background">
            <div className="max-w-4xl mx-auto flex gap-3">
              <Textarea
                value={inputValue}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder="Message the agent... (Press Enter to send)"
                disabled={!isConnected || isSending}
                className="resize-none min-h-[44px] max-h-[144px] bg-muted/50 border-border focus-visible:ring-1 focus-visible:ring-primary shadow-sm"
                rows={1}
              />
              <Button 
                onClick={(e) => handleSend(e)} 
                disabled={!inputValue.trim() || !isConnected || isSending}
                className="self-end"
              >
                Send
              </Button>
            </div>
          </div>
        </div>

        {/* Dev View Panel */}
        {showDevView && (
          <div className="w-[40%] flex flex-col bg-sidebar/50 h-full overflow-hidden">
            <div className="p-3 border-b border-border bg-log-surface text-muted-foreground text-xs uppercase tracking-wider font-mono">
              Dev View (File Tree)
            </div>
            <div className="flex-1 p-4 font-mono text-[13px] text-muted-foreground overflow-y-auto">
              {/* Placeholder for Dev View file tree */}
              <div className="flex items-center gap-2 mb-2">
                <div className="w-1.5 h-1.5 rounded-full bg-success"></div>
                <span>frontend/app/page.tsx</span>
              </div>
              <div className="flex items-center gap-2 mb-2">
                <div className="w-1.5 h-1.5 rounded-full bg-agent-active"></div>
                <span>frontend/components/Sidebar.tsx</span>
              </div>
              <p className="mt-8 italic opacity-50">Local workspace synchronization not active.</p>
            </div>
          </div>
        )}
      </div>

      {/* Cost Indicator Footer */}
      <footer className="flex-shrink-0 border-t border-border bg-muted/30 px-4 py-1.5 flex justify-between items-center text-xs font-mono text-muted-foreground">
        <div>Session: 0 tokens / $0.00</div>
        <div>Project: 0 tokens / $0.00</div>
      </footer>
    </div>
  );
}
