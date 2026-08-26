import { useQuery } from '@tanstack/react-query';
import { getRecipeDetail } from '../api/intelligence';
import type { RecipeDetailResponse } from '../api/types';

export const recipeDetailQueryKey = (recipeId: string) =>
  ['intelligence', 'recipe', recipeId] as const;

export function useRecipeDetail(recipeId: string | undefined) {
  return useQuery<RecipeDetailResponse, Error>({
    queryKey: recipeId ? [...recipeDetailQueryKey(recipeId)] : ['intelligence', 'recipe', 'none'],
    queryFn: () => {
      if (!recipeId) throw new Error('No recipe selected');
      return getRecipeDetail(recipeId);
    },
    enabled: Boolean(recipeId),
    staleTime: 60 * 60 * 1000,
  });
}
