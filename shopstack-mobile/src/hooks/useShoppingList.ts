import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getActiveList, createList, completeList, markPurchased } from '../api/shopping';
import type {
  ShoppingListWire,
  CreateShoppingListRequest,
  CompleteShoppingListRequest,
  CompleteShoppingListResponse,
  MarkPurchasedRequest,
  MarkPurchasedResponse,
} from '../api/types';

export const shoppingQueryKey = ['shopping', 'active'] as const;

export function useActiveShoppingList() {
  return useQuery<ShoppingListWire, Error>({
    queryKey: shoppingQueryKey,
    queryFn: getActiveList,
    staleTime: 10_000,
  });
}

export function useCreateShoppingList() {
  const qc = useQueryClient();
  return useMutation<ShoppingListWire, Error, CreateShoppingListRequest>({
    mutationFn: createList,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['shopping'] }),
  });
}

export interface CompleteListArgs {
  listId: string;
  boughtItemIds: string[];
}

export function useCompleteShoppingList() {
  const qc = useQueryClient();
  return useMutation<CompleteShoppingListResponse, Error, CompleteListArgs>({
    mutationFn: ({ listId, boughtItemIds }) =>
      completeList(listId, { purchased_item_ids: boughtItemIds.length > 0 ? boughtItemIds : undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['shopping'] });
      qc.invalidateQueries({ queryKey: ['inventory'] });
      qc.invalidateQueries({ queryKey: ['today'] });
    },
  });
}

export interface MarkPurchasedArgs {
  listId: string;
  itemIds: string[];
}

export function useMarkPurchased() {
  const qc = useQueryClient();
  return useMutation<MarkPurchasedResponse, Error, MarkPurchasedArgs>({
    mutationFn: ({ listId, itemIds }) =>
      markPurchased(listId, { item_ids: itemIds }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['shopping'] });
      qc.invalidateQueries({ queryKey: ['inventory'] });
    },
  });
}
