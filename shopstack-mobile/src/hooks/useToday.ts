import { useQuery } from '@tanstack/react-query';
import { getTodaySnapshot } from '../api/dashboard';
import type { DashboardSnapshot } from '../api/types';

export const todayQueryKey = ['today', 'snapshot'] as const;

export function useToday() {
  return useQuery<DashboardSnapshot, Error>({
    queryKey: todayQueryKey,
    queryFn: getTodaySnapshot,
    staleTime: 15_000,
  });
}
