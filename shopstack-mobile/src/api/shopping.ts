import { api } from './client';
import type {
  ShoppingListWire,
  CreateShoppingListRequest,
  CompleteShoppingListRequest,
  CompleteShoppingListResponse,
  MarkPurchasedRequest,
  MarkPurchasedResponse,
} from './types';

export async function getActiveList(): Promise<ShoppingListWire> {
  return api.get<ShoppingListWire>('/api/v1/shopping/active');
}

export async function createList(body: CreateShoppingListRequest): Promise<ShoppingListWire> {
  return api.post<ShoppingListWire>('/api/v1/shopping/lists', body);
}

export async function completeList(
  listId: string,
  body: CompleteShoppingListRequest = {},
): Promise<CompleteShoppingListResponse> {
  return api.post<CompleteShoppingListResponse>(
    `/api/v1/shopping/lists/${encodeURIComponent(listId)}/complete`,
    body,
  );
}

export async function markPurchased(
  listId: string,
  body: MarkPurchasedRequest,
): Promise<MarkPurchasedResponse> {
  return api.post<MarkPurchasedResponse>(
    `/api/v1/shopping/lists/${encodeURIComponent(listId)}/mark-purchased`,
    body,
  );
}
