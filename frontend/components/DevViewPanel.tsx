// Story 6.3: Dev View Panel — live file tree + read-only viewer, local mode only
"use client";

import React, { useEffect, useRef, useState } from 'react';
import { apiClient, WorkspaceEntry } from '@/lib/api/client';
import type { StreamEvent } from '@/lib/sse/useStream';

interface DevViewPanelProps {
  projectId: string;
  events: StreamEvent[];
}

type FileOp = 'created' | 'modified' | 'deleted';

interface FileTreeUpdatePayload {
  path: string;
  operation: FileOp;
}

export default function DevViewPanel({ projectId, events }: DevViewPanelProps) {
  const [entries, setEntries] = useState<WorkspaceEntry[]>([]);
  const [root, setRoot] = useState<string | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [selectedContent, setSelectedContent] = useState<string | null>(null);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());
  const [fileOps, setFileOps] = useState<Record<string, FileOp>>({});
  const eventCursor = useRef<number>(0);

  useEffect(() => {
    let cancelled = false;
    async function loadTree() {
      try {
        const tree = await apiClient.getWorkspaceTree(projectId);
        if (cancelled) return;
        setEntries(tree.entries);
        setRoot(tree.root);
      } catch (err) {
        console.error('DevViewPanel: failed to load tree', err);
        if (!cancelled) {
          setEntries([]);
          setRoot(null);
        }
      }
    }
    loadTree();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => {
    if (events.length <= eventCursor.current) return;
    const newEvents = events.slice(eventCursor.current);
    eventCursor.current = events.length;

    let deletedSelected = false;
    let refetchSelected = false;

    setEntries((prevEntries) => {
      const next = [...prevEntries];
      const known = new Set(next.map((e) => `${e.type}:${e.path}`));
      for (const ev of newEvents) {
        if (ev.type !== 'file_tree_update') continue;
        const payload = ev.data as FileTreeUpdatePayload | null;
        if (!payload || !payload.path || !payload.operation) continue;
        if (payload.operation === 'created' && !known.has(`file:${payload.path}`)) {
          next.push({ path: payload.path, type: 'file' });
          known.add(`file:${payload.path}`);
        }
        if (payload.path === selectedPath) {
          if (payload.operation === 'deleted') deletedSelected = true;
          else refetchSelected = true;
        }
      }
      return next;
    });

    setFileOps((prevOps) => {
      const next = { ...prevOps };
      for (const ev of newEvents) {
        if (ev.type !== 'file_tree_update') continue;
        const payload = ev.data as FileTreeUpdatePayload | null;
        if (!payload || !payload.path || !payload.operation) continue;
        next[payload.path] = payload.operation;
      }
      return next;
    });

    if (deletedSelected) {
      setSelectedContent('<empty — file deleted>');
    } else if (refetchSelected && selectedPath) {
      apiClient
        .getWorkspaceFile(projectId, selectedPath)
        .then((res) => setSelectedContent(res.content))
        .catch((err) => console.error('DevViewPanel: refetch failed', err));
    }
  }, [events, projectId, selectedPath]);

  const handleFileClick = async (path: string) => {
    setSelectedPath(path);
    setSelectedContent(null);
    try {
      const res = await apiClient.getWorkspaceFile(projectId, path);
      setSelectedContent(res.content);
    } catch (err) {
      console.error('DevViewPanel: file fetch failed', err);
      setSelectedContent('<failed to load>');
    }
  };

  const toggleDir = (path: string) => {
    setExpandedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const isVisible = (entryPath: string): boolean => {
    const parts = entryPath.split('/');
    if (parts.length === 1) return true;
    for (let i = 1; i < parts.length; i++) {
      const parentPath = parts.slice(0, i).join('/');
      if (!expandedDirs.has(parentPath)) return false;
    }
    return true;
  };

  const renderDot = (op: FileOp | undefined) => {
    if (op === 'created')
      return <span className="w-1.5 h-1.5 rounded-full bg-success shrink-0" />;
    if (op === 'modified')
      return <span className="w-1.5 h-1.5 rounded-full bg-agent-active shrink-0" />;
    return <span className="w-1.5 h-1.5 shrink-0" />;
  };

  const renderEntry = (entry: WorkspaceEntry) => {
    if (!isVisible(entry.path)) return null;
    const depth = entry.path.split('/').length - 1;
    const indent = { paddingLeft: `${depth * 16}px` };
    const name = entry.path.split('/').pop() ?? entry.path;

    if (entry.type === 'dir') {
      const expanded = expandedDirs.has(entry.path);
      return (
        <button
          key={`dir:${entry.path}`}
          type="button"
          onClick={() => toggleDir(entry.path)}
          className="w-full flex items-center gap-2 text-left hover:bg-muted/40 rounded-sm px-2 py-0.5 font-mono text-[13px] text-muted-foreground"
          style={indent}
        >
          <span className="w-3 shrink-0">{expanded ? '▼' : '▶'}</span>
          <span>{name}/</span>
        </button>
      );
    }

    const op = fileOps[entry.path];
    const isDeleted = op === 'deleted';
    const isSelected = selectedPath === entry.path;
    return (
      <button
        key={`file:${entry.path}`}
        type="button"
        onClick={() => handleFileClick(entry.path)}
        className={`w-full flex items-center gap-2 text-left hover:bg-muted/40 rounded-sm px-2 py-0.5 font-mono text-[13px] ${
          isSelected ? 'bg-muted/60 text-foreground' : 'text-muted-foreground'
        } ${isDeleted ? 'line-through text-destructive' : ''}`}
        style={indent}
      >
        <span className="w-3 shrink-0" />
        {renderDot(op)}
        <span>{name}</span>
      </button>
    );
  };

  const showEmptyState = root === null && entries.length === 0;

  return (
    <div className="w-[40%] flex flex-col bg-sidebar/50 h-full overflow-hidden">
      <div className="p-3 border-b border-border bg-log-surface text-muted-foreground text-xs uppercase tracking-wider font-mono">
        Dev View (File Tree)
      </div>

      <div className="flex-1 basis-0 min-h-0 overflow-y-auto p-2">
        {showEmptyState ? (
          <div className="h-full flex items-center justify-center p-8 text-center">
            <p className="italic text-muted-foreground text-sm">
              Workspace not initialized. Run a ticket in local mode to populate.
            </p>
          </div>
        ) : (
          <div className="space-y-0.5">{entries.map(renderEntry)}</div>
        )}
      </div>

      {selectedPath && (
        <div className="h-[45%] border-t border-border flex flex-col overflow-hidden">
          <div className="p-2 border-b border-border bg-log-surface text-muted-foreground text-xs font-mono truncate">
            {selectedPath}
          </div>
          <div className="flex-1 overflow-y-auto">
            <pre className="whitespace-pre font-mono text-[12px] text-foreground p-3">
              {selectedContent ?? 'Loading…'}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
