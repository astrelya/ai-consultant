"use client";

import React, { useState } from 'react';
import TicketCard from '@/components/TicketCard';
import type { Ticket } from '@/components/TicketCard';
import { apiClient } from '@/lib/api/client';

interface TicketCardListProps {
  tickets: Ticket[];
  projectId: string;
  jiraConfigured?: boolean;
}

/**
 * Topological sort: returns tickets in dependency-resolved order
 * (blockers before dependents). Pure frontend logic, zero LLM calls.
 */
function topoSort(tickets: Ticket[]): Ticket[] {
  const map = new Map(tickets.map((t) => [t.id, t]));
  const visited = new Set<string>();
  const result: Ticket[] = [];

  function visit(id: string) {
    if (visited.has(id)) return;
    visited.add(id);
    const ticket = map.get(id);
    if (!ticket) return;
    for (const depId of ticket.blocked_by) {
      visit(depId);
    }
    result.push(ticket);
  }

  tickets.forEach((t) => visit(t.id));
  return result;
}

export default function TicketCardList({ tickets, projectId, jiraConfigured }: TicketCardListProps) {
  const sorted = topoSort(tickets);

  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => {
    const initial = new Set<string>();
    tickets.forEach(t => {
      if (t.status === 'Accepted') initial.add(t.id);
    });
    return initial;
  });

  const missingBlockers = new Set<string>();
  const warningTickets = new Set<string>();

  sorted.forEach(t => {
    if (!selectedIds.has(t.id)) {
      missingBlockers.add(t.id);
    } else {
      const hasMissingBlocker = t.blocked_by.some(blockerId => missingBlockers.has(blockerId));
      if (hasMissingBlocker) {
        missingBlockers.add(t.id);
        warningTickets.add(t.id);
      }
    }
  });

  const toggleSelection = (id: string, selected: boolean) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (selected) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const handleAccept = async (ticketId: string, updates?: Record<string, any>) => {
    try {
      await apiClient.acceptTicket(projectId, ticketId, updates);
      setSelectedIds(prev => {
        const next = new Set(prev);
        next.add(ticketId);
        return next;
      });
    } catch (err) {
      console.error('Failed to accept ticket:', err);
    }
  };

  const handleRevise = async (ticketId: string, instruction: string) => {
    try {
      await apiClient.reviseTicket(projectId, ticketId, instruction);
    } catch {
      console.warn('Ticket revision endpoint not yet available (Story 4.3 scope)');
    }
  };

  const handleExecute = async () => {
    const executeIds = sorted.filter(t => selectedIds.has(t.id)).map(t => t.id);
    if (executeIds.length === 0) return;
    try {
      await apiClient.executeTickets(projectId, executeIds);
    } catch (err) {
      console.error('Failed to execute tickets:', err);
    }
  };

  return (
    <div id="ticket-card-list" className="space-y-3">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className="text-base">🎫</span>
          <span className="font-semibold text-sm text-foreground">
            Generated Tickets ({sorted.length})
          </span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={async () => {
              const pendingTickets = tickets.filter(t => t.status === 'Pending' || t.status === 'Error');
              await Promise.all(pendingTickets.map(t => handleAccept(t.id)));
            }}
            className="text-xs bg-primary text-primary-foreground px-2 py-1 rounded"
          >
            Accept All
          </button>
          <button
            onClick={handleExecute}
            disabled={selectedIds.size === 0}
            className="text-xs bg-success text-success-foreground px-2 py-1 rounded disabled:opacity-50"
          >
            {jiraConfigured ? `Approve & Begin (${selectedIds.size})` : `Execute (${selectedIds.size})`}
          </button>
        </div>
      </div>
      {sorted.map((ticket) => (
        <TicketCard
          key={ticket.id}
          ticket={ticket}
          isSelected={selectedIds.has(ticket.id)}
          hasWarning={warningTickets.has(ticket.id)}
          onToggleSelection={toggleSelection}
          onAccept={handleAccept}
          onRevise={handleRevise}
        />
      ))}
    </div>
  );
}
