"use client";

import { useState, useEffect } from 'react';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface StreamEvent {
  type: string;
  data: unknown;
  timestamp: string;
}

const NAMED_EVENT_TYPES = [
  'execution_start',
  'execution_tick',
  'ticket_done',
  'execution_end',
  // Spec pipeline and brainstorm events (Stories 3.3, 3.4)
  'bmad_output',
  'bmad_complete',
  'bmad_error',
  'spec_stored',
  'spec_store_error',
  'connected',
] as const;

export type NamedEventType = typeof NAMED_EVENT_TYPES[number];

export function useStream(projectId: string) {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!projectId) {
      setIsConnected(false);
      setEvents([]);
      return;
    }

    const baseUrl = API_BASE_URL.replace(/\/$/, '');
    const url = `${baseUrl}/stream/${projectId}`;
    const eventSource = new EventSource(url);

    eventSource.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    // Existing handler — catches unnamed (default) SSE events; keep as-is
    eventSource.onmessage = (event) => {
      try {
        const parsedData = JSON.parse(event.data);
        const newEvent: StreamEvent = {
          type: 'message',
          data: parsedData,
          timestamp: new Date().toISOString(),
        };
        setEvents((prev) => [...prev, newEvent]);
      } catch (err) {
        console.error('Failed to parse SSE data', err);
      }
    };

    // Named event listeners for execution status events
    const namedHandlers: Array<{ type: string; handler: EventListener }> = [];
    NAMED_EVENT_TYPES.forEach((type) => {
      const handler = (event: Event) => {
        const msgEvent = event as MessageEvent;
        try {
          const parsedData = JSON.parse(msgEvent.data);
          setEvents((prev) => [
            ...prev,
            { type, data: parsedData, timestamp: new Date().toISOString() },
          ]);
        } catch (err) {
          console.error(`Failed to parse SSE data for event type "${type}"`, err);
        }
      };
      eventSource.addEventListener(type, handler);
      namedHandlers.push({ type, handler });
    });

    eventSource.onerror = (err) => {
      console.error('EventSource failed:', err);
      if (eventSource.readyState === EventSource.CLOSED) {
        setIsConnected(false);
        setError(new Error('EventSource failed'));
      }
      // If readyState is CONNECTING (0), EventSource will auto-reconnect.
    };

    return () => {
      // Remove named event listeners to prevent memory leaks
      namedHandlers.forEach(({ type, handler }) => {
        eventSource.removeEventListener(type, handler);
      });
      eventSource.close();
      setIsConnected(false);
    };
  }, [projectId]);

  return { events, isConnected, error };
}
