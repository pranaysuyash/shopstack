import { useQuery } from '@tanstack/react-query';
import { getMealPlan } from '../api/intelligence';
import type { MealPlanResponse } from '../api/types';

export const mealPlanQueryKey = ['intelligence', 'mealplan'] as const;

export function useMealPlan(days = 7) {
  return useQuery<MealPlanResponse, Error>({
    queryKey: [...mealPlanQueryKey, { days }],
    queryFn: () => getMealPlan(days),
    staleTime: 60 * 60 * 1000, // meal plans don't change minute-to-minute
  });
}
