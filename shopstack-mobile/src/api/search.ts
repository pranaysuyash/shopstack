import { api } from './client';
import type { SearchResponse } from './types';

export async function searchGlobal(q: string): Promise<SearchResponse> {
  return api.get<SearchResponse>('/api/v1/search/global', { q });
}

export async function searchInventory(q: string): Promise<SearchResponse> {
  return api.get<SearchResponse>('/api/v1/search/inventory', { q });
}
