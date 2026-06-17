import { api } from './client';
import type {
  PurgeDataResponse,
  RetentionSummaryResponse,
  UpdateRetentionRequest,
  UndoRequest,
  UndoResponse,
  StoreModeToggleRequest,
  StoreModeToggleResponse,
} from './types';

export async function purgeData(): Promise<PurgeDataResponse> {
  return api.post<PurgeDataResponse>('/api/v1/account/privacy/purge');
}

export async function getRetentionSummary(): Promise<RetentionSummaryResponse> {
  return api.get<RetentionSummaryResponse>('/api/v1/account/privacy/retention-summary');
}

export async function updateRetention(body: UpdateRetentionRequest): Promise<{ success: boolean }> {
  return api.post<{ success: boolean }>('/api/v1/account/privacy/update-retention', body);
}

export async function undo(body: UndoRequest = {}): Promise<UndoResponse> {
  return api.post<UndoResponse>('/api/v1/account/undo', body);
}

export async function toggleStoreMode(body: StoreModeToggleRequest): Promise<StoreModeToggleResponse> {
  return api.post<StoreModeToggleResponse>('/api/v1/account/store-mode/toggle', body);
}
