import { useQuery } from '@tanstack/react-query';
import { listLots } from '../api/inventory';
import type { ListResponse, InventoryLot } from '../api/types';

export const inventoryQueryKey = ['inventory', 'lots'] as const;

export function useInventory(limit = 200) {
  return useQuery<ListResponse<InventoryLot>, Error>({
    queryKey: [...inventoryQueryKey, { limit }],
    queryFn: () => listLots({ limit }),
    staleTime: 10_000,
  });
}
