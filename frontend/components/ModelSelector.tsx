"use client";

import { useEffect, useState } from 'react';
import { apiClient } from '@/lib/api/client';

type Role = 'ticket' | 'coding';

const ROLE_LABELS: Record<Role, string> = {
  ticket: 'Master',
  coding: 'Sub-agents',
};

export default function ModelSelector() {
  const [available, setAvailable] = useState<string[]>([]);
  const [current, setCurrent] = useState<Record<Role, string>>({ ticket: '', coding: '' });
  const [saving, setSaving] = useState<Role | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .getConfig()
      .then((cfg) => {
        if (cancelled) return;
        setAvailable(cfg.available_models);
        setCurrent({ ticket: cfg.models.ticket, coding: cfg.models.coding });
      })
      .catch((err: Error) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, []);

  const handleChange = async (role: Role, value: string) => {
    setSaving(role);
    setError(null);
    try {
      const res = await apiClient.updateModels({ [role]: value });
      setCurrent({ ticket: res.models.ticket, coding: res.models.coding });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update model');
    } finally {
      setSaving(null);
    }
  };

  if (!available.length) return null;

  return (
    <div className="flex items-center gap-3 text-xs">
      {(['ticket', 'coding'] as Role[]).map((role) => (
        <label key={role} className="flex items-center gap-1.5 text-muted-foreground">
          <span className="uppercase tracking-wider">{ROLE_LABELS[role]}</span>
          <select
            className="bg-muted/50 border border-border rounded px-2 py-1 text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            value={current[role]}
            disabled={saving === role}
            onChange={(e) => handleChange(role, e.target.value)}
          >
            {available.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
      ))}
      {error && <span className="text-destructive" title={error}>⚠</span>}
    </div>
  );
}
