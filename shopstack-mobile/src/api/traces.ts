import { api } from './client';
import type { TraceListResponse, TraceDetailResponse, CommandHistoryResponse } from './types';

export async function listTraces(
  params?: { limit?: number; search?: string; input_type_filter?: string },
): Promise<TraceListResponse> {
  return api.get<TraceListResponse>('/api/v1/traces', params as Record<string, string | number | boolean | undefined>);
}

export async function getTrace(traceId: string): Promise<TraceDetailResponse> {
  return api.get<TraceDetailResponse>(`/api/v1/traces/${encodeURIComponent(traceId)}`);
}

export async function exportTrace(traceId: string, redact = true): Promise<{ trace_id: string; jsonl: string }> {
  return api.get<{ trace_id: string; jsonl: string }>(
    `/api/v1/traces/${encodeURIComponent(traceId)}/export`,
    { redact: redact ? 'true' : 'false' },
  );
}

export async function getCommandHistory(params?: { limit?: number }): Promise<CommandHistoryResponse> {
  return api.get<CommandHistoryResponse>('/api/v1/command/history', params);
}
