// Story 6.2: Cost Indicator — consumes token_update SSE events
import React from 'react';
import type { StreamEvent } from '@/lib/sse/useStream';

export interface CostIndicatorProps {
  events: StreamEvent[];
  initialTotalTokens: number;
  initialTotalCostUsd: number;
}

type TokenUpdatePayload = {
  session_tokens: number;
  session_cost_usd: number;
  total_tokens: number;
  total_cost_usd: number;
};

const nf = new Intl.NumberFormat('en-US');

export default function CostIndicator({
  events,
  initialTotalTokens,
  initialTotalCostUsd,
}: CostIndicatorProps): React.JSX.Element {
  const latest = events.filter((ev) => ev.type === 'token_update').slice(-1)[0];

  let sessionTokens = 0;
  let sessionCostUsd = 0;
  let totalTokens = initialTotalTokens;
  let totalCostUsd = initialTotalCostUsd;

  if (latest) {
    const data = (latest.data ?? {}) as Partial<TokenUpdatePayload>;
    sessionTokens = data.session_tokens ?? 0;
    sessionCostUsd = data.session_cost_usd ?? 0;
    totalTokens = data.total_tokens ?? 0;
    totalCostUsd = data.total_cost_usd ?? 0;
  }

  const sessionTokensFmt = nf.format(sessionTokens);
  const totalTokensFmt = nf.format(totalTokens);
  const sessionCostFmt = sessionCostUsd.toFixed(2);
  const totalCostFmt = totalCostUsd.toFixed(2);

  const ariaLabel =
    `Token usage: ${sessionTokens} this session / ${totalTokens} total, ` +
    `estimated cost $${sessionCostFmt} this session / $${totalCostFmt} total`;

  return (
    <footer
      role="status"
      aria-live="polite"
      aria-label={ariaLabel}
      className="flex-shrink-0 border-t border-border bg-muted/30 px-4 py-1.5 flex justify-between items-center text-xs font-mono text-muted-foreground"
    >
      <div>
        Session:{' '}
        <span className="text-foreground">
          {sessionTokensFmt} tokens · ${sessionCostFmt}
        </span>
      </div>
      <div>
        Total:{' '}
        <span className="text-foreground">
          {totalTokensFmt} tokens · ${totalCostFmt}
        </span>
      </div>
    </footer>
  );
}
