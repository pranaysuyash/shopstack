import { useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, RefreshControl,
} from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { getRecurringPlan, getMealPlan } from '../src/api/intelligence';
import type { RecurringPlanItemWire, MealPlanDayWire } from '../src/api/types';

type Tab = 'recurring' | 'mealplan';

export default function IntelligenceScreen() {
  const [tab, setTab] = useState<Tab>('recurring');

  const recurringQuery = useQuery({
    queryKey: ['intelligence', 'recurring'],
    queryFn: () => getRecurringPlan(7),
    staleTime: 30_000,
  });

  const mealPlanQuery = useQuery({
    queryKey: ['intelligence', 'mealplan'],
    queryFn: () => getMealPlan(7),
    staleTime: 60_000,
  });

  const data = tab === 'recurring' ? recurringQuery : mealPlanQuery;
  const isLoading = data.isLoading && !data.data;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.header}>Intelligence</Text>

      <View style={styles.tabs}>
        <TouchableOpacity
          style={[styles.tab, tab === 'recurring' && styles.tabActive]}
          onPress={() => setTab('recurring')}
        >
          <Text style={[styles.tabText, tab === 'recurring' && styles.tabTextActive]}>Recurring</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, tab === 'mealplan' && styles.tabActive]}
          onPress={() => setTab('mealplan')}
        >
          <Text style={[styles.tabText, tab === 'mealplan' && styles.tabTextActive]}>Meal Plan</Text>
        </TouchableOpacity>
      </View>

      {isLoading ? (
        <ActivityIndicator size="large" color="#6366f1" style={{ marginTop: 40 }} />
      ) : tab === 'recurring' ? (
        <RecurringPlanView data={recurringQuery.data} />
      ) : (
        <MealPlanView data={mealPlanQuery.data} />
      )}
    </ScrollView>
  );
}

function RecurringPlanView({ data }: { data?: { items: RecurringPlanItemWire[]; summary: string } }) {
  if (!data || data.items.length === 0) {
    return (
      <View style={styles.empty}>
        <Ionicons name="trending-up-outline" size={48} color="#444" />
        <Text style={styles.emptyText}>No recurring items due</Text>
      </View>
    );
  }
  return (
    <>
      <Text style={styles.summary}>{data.summary}</Text>
      {data.items.map((item, i) => (
        <View key={i} style={styles.card}>
          <View style={styles.cardRow}>
            <Text style={styles.cardTitle}>{item.display_name || item.canonical_name}</Text>
            <Text style={styles.cardScore}>{(item.confidence * 100).toFixed(0)}%</Text>
          </View>
          {item.days_until_next !== null && item.days_until_next !== undefined && (
            <Text style={styles.cardMeta}>
              {item.days_until_next <= 0 ? 'Due today' : `Due in ${item.days_until_next} days`}
            </Text>
          )}
          {item.reasons?.map((r, j) => (
            <Text key={j} style={styles.reason}>• {r}</Text>
          ))}
        </View>
      ))}
    </>
  );
}

function MealPlanView({ data }: { data?: { items: MealPlanDayWire[]; summary: string } }) {
  if (!data || data.items.length === 0) {
    return (
      <View style={styles.empty}>
        <Ionicons name="restaurant-outline" size={48} color="#444" />
        <Text style={styles.emptyText}>No meal plan available</Text>
      </View>
    );
  }
  return (
    <>
      <Text style={styles.summary}>{data.summary}</Text>
      {data.items.map((day, i) => (
        <View key={i} style={styles.card}>
          <Text style={styles.date}>{day.date}</Text>
          {day.recipe_name ? (
            <>
              <Text style={styles.recipeName}>{day.recipe_name}</Text>
              {day.cuisine && <Text style={styles.cuisine}>{day.cuisine}</Text>}
              {day.ingredients_used.length > 0 && (
                <Text style={styles.ingredients}>
                  ✅ Have: {day.ingredients_used.join(', ')}
                </Text>
              )}
              {day.ingredients_missing.length > 0 && (
                <Text style={styles.missing}>
                  ❌ Need: {day.ingredients_missing.join(', ')}
                </Text>
              )}
            </>
          ) : (
            <Text style={styles.noRecipe}>No recipe planned</Text>
          )}
        </View>
      ))}
    </>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f23' },
  content: { padding: 16, paddingTop: 60, paddingBottom: 40 },
  header: { fontSize: 28, fontWeight: '700', color: '#e0e0ff', marginBottom: 16 },
  tabs: { flexDirection: 'row', gap: 8, marginBottom: 20 },
  tab: { flex: 1, padding: 12, borderRadius: 10, alignItems: 'center', backgroundColor: '#1a1a3e', borderWidth: 1, borderColor: '#2a2a5e' },
  tabActive: { borderColor: '#818cf8', backgroundColor: '#818cf820' },
  tabText: { color: '#666', fontWeight: '600' },
  tabTextActive: { color: '#818cf8' },
  summary: { fontSize: 14, color: '#8888bb', marginBottom: 16, fontStyle: 'italic' },
  card: { backgroundColor: '#1a1a3e', borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: '#2a2a5e' },
  cardRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  cardTitle: { fontSize: 16, fontWeight: '600', color: '#e0e0ff' },
  cardScore: { fontSize: 14, fontWeight: '700', color: '#22c55e' },
  cardMeta: { fontSize: 13, color: '#f59e0b', marginTop: 4 },
  reason: { fontSize: 12, color: '#8888bb', marginTop: 2 },
  date: { fontSize: 14, fontWeight: '700', color: '#818cf8', marginBottom: 4 },
  recipeName: { fontSize: 18, fontWeight: '600', color: '#e0e0ff' },
  cuisine: { fontSize: 13, color: '#8888bb', marginTop: 2 },
  ingredients: { fontSize: 13, color: '#22c55e', marginTop: 8 },
  missing: { fontSize: 13, color: '#ef4444', marginTop: 2 },
  noRecipe: { fontSize: 14, color: '#666', fontStyle: 'italic', marginTop: 4 },
  empty: { alignItems: 'center', paddingTop: 60, gap: 8 },
  emptyText: { fontSize: 16, color: '#666' },
});
