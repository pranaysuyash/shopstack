import { api } from './client';
import type {
  CorrectionListResponse,
  CorrectionCreateRequest,
  CorrectionCreateResponse,
} from './types';

export async function listCorrections(
  params?: { limit?: number; accepted_only?: boolean },
): Promise<CorrectionListResponse> {
  return api.get<CorrectionListResponse>(
    '/api/v1/corrections',
    params as Record<string, string | number | boolean | undefined>,
  );
}

export async function createCorrection(body: CorrectionCreateRequest): Promise<CorrectionCreateResponse> {
  return api.post<CorrectionCreateResponse>('/api/v1/corrections', body);
}
