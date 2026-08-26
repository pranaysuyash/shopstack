import { decision } from '../theme';

type Action = 'buy' | 'skip' | 'use_soon' | 'compare' | 'confirm' | 'watch';

interface DecisionBadgeResult {
  label: string;
  kind: keyof typeof decision;
}

export function useDecisionBadge(action: Action | string, confidence?: number): DecisionBadgeResult {
  const key = (action || '').toLowerCase();
  if (key === 'buy') return { label: 'Buy', kind: 'buy' };
  if (key === 'skip') return { label: 'Skip', kind: 'skip' };
  if (key === 'use_soon' || key === 'use-soon') return { label: 'Use soon', kind: 'useSoon' };
  if (key === 'compare') return { label: 'Compare', kind: 'compare' };
  if (key === 'confirm') return { label: 'Confirm', kind: 'confirm' };
  if (key === 'watch') return { label: 'Watch', kind: 'watch' };

  // Fallback based on confidence heuristic
  if (typeof confidence === 'number') {
    if (confidence >= 0.9) return { label: 'Buy', kind: 'buy' };
    if (confidence >= 0.7) return { label: 'Use soon', kind: 'useSoon' };
    if (confidence >= 0.4) return { label: 'Watch', kind: 'watch' };
  }

  return { label: 'Watch', kind: 'watch' };
}
