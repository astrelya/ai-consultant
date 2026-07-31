"use client";

import { useState, useEffect, useMemo, useRef } from 'react';
import { StreamEvent } from '@/lib/sse/useStream';

// ── TypeScript interfaces ────────────────────────────────────────────────────

export interface QueueTicket {
  id: string;
  name: string;
  status: 'done' | 'active' | 'pending';
}

export interface ExecutionStatus {
  active: boolean;
  activeTicketId: string | null;
  tickets: QueueTicket[];
}

// ── State derivation ─────────────────────────────────────────────────────────

function deriveExecutionState(events: StreamEvent[]): ExecutionStatus {
  let active = false;
  let activeTicketId: string | null = null;
  let tickets: QueueTicket[] = [];

  for (const event of events) {
    switch (event.type) {
      case 'execution_start': {
        const payload = event.data as { tickets?: Array<{ id: string; name: string; status?: string }> };
        active = true;
        activeTicketId = null;
        tickets = (payload.tickets ?? []).map((t) => ({
          id: t.id,
          name: t.name,
          status: (t.status as QueueTicket['status']) ?? 'pending',
        }));
        break;
      }

      case 'bmad_output': {
        if (!active) {
          active = true;
          activeTicketId = null;
          tickets = [];
        }
        break;
      }

      case 'execution_tick': {
        const payload = event.data as { active_ticket_id?: string; elapsed_seconds?: number };
        if (payload.active_ticket_id && tickets.some(t => t.id === payload.active_ticket_id)) {
          activeTicketId = payload.active_ticket_id;
          tickets = tickets.map((t) => ({
            ...t,
            status:
              t.id === payload.active_ticket_id
                ? 'active'
                : t.status === 'active'
                  ? 'pending'
                  : t.status,
          }));
        }
        break;
      }

      case 'ticket_done': {
        const payload = event.data as { ticket_id?: string };
        if (payload.ticket_id) {
          tickets = tickets.map((t) =>
            t.id === payload.ticket_id ? { ...t, status: 'done' } : t,
          );
          if (activeTicketId === payload.ticket_id) {
            activeTicketId = null;
          }
        }
        break;
      }

      case 'execution_end':
      case 'bmad_complete':
      case 'bmad_error':
      case 'spec_stored':
      case 'spec_store_error': {
        active = false;
        activeTicketId = null;
        break;
      }
    }
  }

  return { active, activeTicketId, tickets };
}

// ── Helper: format elapsed seconds ──────────────────────────────────────────

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60); // Math.floor ensures padStart works nicely on floats
  return m > 0
    ? `${m}m ${String(s).padStart(2, '0')}s`
    : `${s}s`;
}

// ── Component ────────────────────────────────────────────────────────────────

interface ExecutionStatusBlockProps {
  events: StreamEvent[];
}

export default function ExecutionStatusBlock({ events }: ExecutionStatusBlockProps) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const logEndRef = useRef<HTMLDivElement>(null);

  const executionState = useMemo(() => deriveExecutionState(events), [events]);

  // Elapsed-time counter reset on activeTicketId change or active state
  useEffect(() => {
    if (!executionState.active) return;
    setElapsedSeconds(0);
    const id = setInterval(() => setElapsedSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [executionState.active, executionState.activeTicketId]);

  // Derive agent output (log stream)
  const agentContent = useMemo(() => {
    return events
      .filter(e => e.type === 'message' || !e.type || e.type === 'bmad_output' || e.type === 'bmad_error')
      .map(e => {
        if (typeof e.data === 'string') return e.data;
        if (e.data !== null && typeof e.data === 'object') {
          const d = e.data as Record<string, unknown>;
          if (e.type === 'bmad_output' && typeof d.line === 'string') return d.line + '\n';
          if (e.type === 'bmad_error' && typeof d.error === 'string') return 'ERROR: ' + d.error + '\n';
          if (typeof d.content === 'string') return d.content;
        }
        return '';
      })
      .join('');
  }, [events]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [agentContent]);

  if (!executionState.active) return null;

  const activeTicket = executionState.tickets.find(
    (t) => t.id === executionState.activeTicketId,
  );

  return (
    <div className="bg-log-surface border border-log-surface-border rounded-xl font-mono text-[13px] p-4 text-foreground/90 my-4 shadow-sm" role="status" aria-live="polite">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 border-b border-log-surface-border pb-3">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-agent-active animate-pulse" aria-hidden="true" />
          <span className="font-semibold text-agent-active uppercase tracking-wider text-[11px]">Running</span>
        </div>
        <span className="text-muted-foreground">{formatElapsed(elapsedSeconds)}</span>
      </div>

      <div className="flex flex-col md:flex-row gap-6">
        {/* Execution Queue Sidebar */}
        <div className="w-full md:w-1/3 flex-shrink-0">
          {activeTicket && (
            <div className="mb-4">
              <p className="text-xs text-muted-foreground mb-1 uppercase tracking-wider">Active Task</p>
              <div className="flex items-start gap-2">
                <span className="animate-spin text-agent-active mt-0.5">●</span>
                <span className="font-medium">{activeTicket.name}</span>
              </div>
            </div>
          )}

          {executionState.tickets.length > 0 && (
            <>
              <p className="text-xs text-muted-foreground mb-2 uppercase tracking-wider">Queue</p>
              <ul className="space-y-1">
                {executionState.tickets.map((ticket) => (
                  <li key={ticket.id} className="flex items-start gap-2">
                    <span className="mt-0.5 text-[10px]">
                      {ticket.status === 'done' && <span className="text-success">✓</span>}
                      {ticket.status === 'active' && <span className="text-agent-active">▶</span>}
                      {ticket.status === 'pending' && <span className="text-pending">○</span>}
                    </span>
                    <span className={`truncate ${ticket.status === 'done' ? 'text-muted-foreground line-through opacity-70' : ticket.status === 'active' ? 'text-agent-active font-medium' : 'text-pending'}`}>
                      {ticket.name}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>

        {/* Log Stream Area */}
        <div className="flex-1 min-w-0 flex flex-col border border-log-surface-border rounded-md bg-[#090b10] overflow-hidden max-h-[40vh]">
          <div className="px-3 py-1.5 border-b border-log-surface-border bg-log-surface text-[11px] text-muted-foreground uppercase tracking-wider">
            Agent Output Log
          </div>
          <div className="flex-1 overflow-y-auto p-3 whitespace-pre-wrap leading-[1.6]">
            {agentContent || <span className="text-muted-foreground italic">Waiting for output...</span>}
            <div ref={logEndRef} />
          </div>
        </div>
      </div>
    </div>
  );
}
