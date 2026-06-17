import { api } from './client';
import type {
  ListResponse,
  InventoryLot,
  AddInventoryLotRequest,
} from './types';

export async function listLots(
  params?: { limit?: number; offset?: number; status_filter?: string },
): Promise<ListResponse<InventoryLot>> {
  return api.get<ListResponse<InventoryLot>>('/api/v1/inventory/lots', params as Record<string, string | number | boolean | undefined>);
}

export async function getLot(lotId: string): Promise<InventoryLot> {
  return api.get<InventoryLot>(`/api/v1/inventory/lots/${encodeURIComponent(lotId)}`);
}

export async function addLot(body: AddInventoryLotRequest): Promise<InventoryLot> {
  return api.post<InventoryLot>('/api/v1/inventory/lots', body);
}

export async function consumeLot(lotId: string, quantity: number, unit?: string): Promise<InventoryLot> {
  return api.post<InventoryLot>(
    `/api/v1/inventory/lots/${encodeURIComponent(lotId)}/consume`,
    { quantity, unit: unit || 'unit' },
  );
}
