import { api } from './client';
import type { DashboardSnapshot } from './types';

export async function getTodaySnapshot(): Promise<DashboardSnapshot> {
  return api.get<DashboardSnapshot>('/api/v1/dashboard/today');
}
