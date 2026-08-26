import { api } from './client';

export interface ExportResponse {
  schema_version: string;
  exported_at: string;
  export_type: string;
  inventory: Array<Record<string, unknown>>;
  price_observations: Array<Record<string, unknown>>;
  field_notes: string;
}

export interface ImportResult {
  items_added: number;
  items_updated: number;
  price_observations_added: number;
  errors: string[];
  messages: string[];
}

export async function exportData(): Promise<ExportResponse> {
  return api.get<ExportResponse>('/api/v1/portability/export');
}

export async function importData(
  data: Record<string, unknown>,
  importMode = 'merge',
): Promise<ImportResult> {
  return api.post<ImportResult>('/api/v1/portability/import', {
    data,
    import_mode: importMode,
  });
}

export async function validateImport(
  data: Record<string, unknown>,
): Promise<ImportResult> {
  return api.post<ImportResult>('/api/v1/portability/validate', { data });
}
