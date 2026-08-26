import { useQuery } from '@tanstack/react-query';
import { getTodaySnapshot } from '../api/dashboard';
import { getCommandHistory } from '../api/traces';
import type { DashboardSnapshot, CommandHistoryResponse } from '../api/types';

/**
 * Trips is intentionally thin: it surfaces trip-recommendation signals from the
 * dashboard plus recent command/traces. No dedicated trip router exists yet.
 */
export function useTripSignals() {
  return useQuery<DashboardSnapshot, Error>({
    queryKey: ['trips', 'signals'],
    queryFn: getTodaySnapshot,
    staleTime: 30_000,
  });
}

export function useTripHistory(limit = 20) {
  return useQuery<CommandHistoryResponse, Error>({
    queryKey: ['trips', 'history', { limit }],
    queryFn: () => getCommandHistory({ limit }),
    staleTime: 60_000,
  });
}
