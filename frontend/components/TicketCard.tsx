"use client";

import React, { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';

export interface Ticket {
  id: string;
  title: string;
  description: string;
  acceptance_criteria: string;
  status: 'Pending' | 'Accepted' | 'In Progress' | 'Done' | 'Error';
  blocking: string[];
  blocked_by: string[];
}

interface TicketCardProps {
  ticket: Ticket;
  isSelected?: boolean;
  hasWarning?: boolean;
  onToggleSelection?: (id: string, selected: boolean) => void;
  onAccept: (id: string, updates?: Partial<Ticket>) => void;
  onRevise: (id: string, instruction: string) => void;
}

export default function TicketCard({ ticket, isSelected = false, hasWarning = false, onToggleSelection, onAccept, onRevise }: TicketCardProps) {
  const [revisionText, setRevisionText] = useState('');
  const [isAccepted, setIsAccepted] = useState(ticket.status === 'Accepted');
  
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(ticket.title);
  const [editDescription, setEditDescription] = useState(ticket.description);
  const [editAC, setEditAC] = useState(ticket.acceptance_criteria);

  const handleAccept = () => {
    setIsAccepted(true);
    if (isEditing) {
      onAccept(ticket.id, {
        title: editTitle,
        description: editDescription,
        acceptance_criteria: editAC
      });
      setIsEditing(false);
    } else {
      onAccept(ticket.id);
    }
  };

  const handleRevise = () => {
    if (!revisionText.trim()) return;
    onRevise(ticket.id, revisionText.trim());
    setRevisionText('');
  };

  const statusVariant = isAccepted ? 'default' : 'secondary';
  const statusLabel = isAccepted ? 'Accepted' : ticket.status;

  return (
    <Card
      id={`ticket-card-${ticket.id}`}
      className={`bg-muted border-border ${hasWarning ? 'border-yellow-500/50 shadow-[0_0_10px_rgba(234,179,8,0.2)]' : ''}`}
    >
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            {onToggleSelection && isAccepted && (
              <input
                type="checkbox"
                checked={isSelected}
                onChange={(e) => onToggleSelection(ticket.id, e.target.checked)}
                className="w-4 h-4 cursor-pointer accent-primary"
                title="Include in execution"
              />
            )}
            {isEditing ? (
              <Input 
                value={editTitle} 
                onChange={(e) => setEditTitle(e.target.value)}
                className="font-semibold text-sm"
              />
            ) : (
              <CardTitle className="text-foreground text-sm flex items-center gap-2">
                {ticket.title}
              </CardTitle>
            )}
          </div>
          <Badge
            id={`ticket-status-${ticket.id}`}
            variant={statusVariant}
            className={isAccepted ? 'bg-success/20 text-success border-success/30' : ''}
          >
            {statusLabel}
          </Badge>
        </div>
        {hasWarning && (
          <div className="text-xs text-yellow-500 mt-2 font-medium flex items-center gap-1 bg-yellow-500/10 p-1.5 rounded border border-yellow-500/20">
            ⚠️ Warning: A required blocking ticket is excluded from execution.
          </div>
        )}
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Description */}
        <div>
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1">
            Description
          </p>
          {isEditing ? (
            <Textarea 
              value={editDescription} 
              onChange={(e) => setEditDescription(e.target.value)}
              className="text-sm"
              rows={4}
            />
          ) : (
            <p className="text-sm text-foreground whitespace-pre-wrap">
              {ticket.description}
            </p>
          )}
        </div>

        {/* Acceptance Criteria */}
        <div>
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1">
            Acceptance Criteria
          </p>
          <div className="rounded-md bg-log-surface p-3">
            {isEditing ? (
              <Textarea 
                value={editAC} 
                onChange={(e) => setEditAC(e.target.value)}
                className="text-xs font-mono"
                rows={5}
              />
            ) : (
              <p className="text-xs text-foreground font-mono whitespace-pre-wrap">
                {ticket.acceptance_criteria}
              </p>
            )}
          </div>
        </div>

        {/* Dependencies */}
        {(ticket.blocking.length > 0 || ticket.blocked_by.length > 0) && (
          <div className="flex flex-wrap gap-3">
            {ticket.blocked_by.length > 0 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1">
                  Blocked By
                </p>
                <div className="flex flex-wrap gap-1">
                  {ticket.blocked_by.map((depId) => (
                    <Badge key={depId} variant="outline" className="text-xs font-mono">
                      {depId.slice(0, 8)}…
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            {ticket.blocking.length > 0 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1">
                  Blocks
                </p>
                <div className="flex flex-wrap gap-1">
                  {ticket.blocking.map((depId) => (
                    <Badge key={depId} variant="outline" className="text-xs font-mono">
                      {depId.slice(0, 8)}…
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>

      <CardFooter className="flex-col items-stretch gap-2">
        {/* Action row */}
        <div className="flex items-center gap-2">
          <Button
            id={`ticket-accept-${ticket.id}`}
            size="sm"
            disabled={isAccepted}
            onClick={handleAccept}
            className={isAccepted ? 'bg-success/20 text-success cursor-default' : 'bg-primary text-primary-foreground'}
          >
            {isAccepted ? '✓ Accepted' : (isEditing ? 'Save & Accept' : 'Accept')}
          </Button>
          {!isAccepted && !isEditing && (
            <Button
              id={`ticket-edit-${ticket.id}`}
              size="sm"
              variant="outline"
              onClick={() => setIsEditing(true)}
            >
              Edit
            </Button>
          )}
          {!isAccepted && isEditing && (
            <Button
              id={`ticket-cancel-${ticket.id}`}
              size="sm"
              variant="outline"
              onClick={() => {
                setIsEditing(false);
                setEditTitle(ticket.title);
                setEditDescription(ticket.description);
                setEditAC(ticket.acceptance_criteria);
              }}
            >
              Cancel
            </Button>
          )}
        </div>

        {/* Revision text field */}
        {!isAccepted && (
          <div className="flex gap-2">
            <Textarea
              id={`ticket-revision-${ticket.id}`}
              value={revisionText}
              onChange={(e) => setRevisionText(e.target.value)}
              placeholder="Suggest a revision…"
              className="resize-none min-h-[36px] text-xs bg-background border-border"
              rows={1}
            />
            <Button
              id={`ticket-revise-${ticket.id}`}
              size="sm"
              variant="outline"
              onClick={handleRevise}
              disabled={!revisionText.trim()}
            >
              Revise
            </Button>
          </div>
        )}
      </CardFooter>
    </Card>
  );
}
