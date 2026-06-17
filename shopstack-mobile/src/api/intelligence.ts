import { api } from './client';
import type {
  DecisionExplanationWire,
  RecurringPlanResponse,
  MealPlanResponse,
} from './types';

export async function getRecurringPlan(windowDays = 3): Promise<RecurringPlanResponse> {
  return api.get<RecurringPlanResponse>('/api/v1/intelligence/recurring', { window: windowDays });
}

export async function getMealPlan(days = 7): Promise<MealPlanResponse> {
  return api.get<MealPlanResponse>('/api/v1/intelligence/mealplan', { days });
}

export async function explainDecision(name: string): Promise<DecisionExplanationWire> {
  return api.get<DecisionExplanationWire>(
    `/api/v1/intelligence/decision/${encodeURIComponent(name)}/explain`,
  );
}
