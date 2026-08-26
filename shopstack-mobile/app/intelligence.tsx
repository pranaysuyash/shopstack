import { useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator,
} from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { getRecurringPlan, getMealPlan } from '../src/api/intelligence';
import type { RecurringPlanItemWire, MealPlanDayWire } from '../src/api/types';
import { semantic, spacing, typography } from '../src/theme';

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
        <ActivityIndicator size="large" color={semantic.primary} style={{ marginTop: 40 }} />
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
        <Ionicons name="trending-up-outline" size={48} color={semantic.textTertiary} />
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
        <Ionicons name="restaurant-outline" size={48} color={semantic.textTertiary} />
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
                <Text style={styles.ingredients}>✅ Have: {day.ingredients_used.join(', ')}</Text>
              )}
              {day.ingredients_missing.length > 0 && (
                <Text style={styles.missing}>❌ Need: {day.ingredients_missing.join(', ')}</Text>
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
  container: { flex: 1, backgroundColor: semantic.background },
  content: { padding: spacing[4], paddingTop: 60, paddingBottom: 40 },
  header: { fontSize: 28, fontWeight: '700', color: semantic.textPrimary, marginBottom: 16 },
  tabs: { flexDirection: 'row', gap: 8, marginBottom: 20 },
  tab: { flex: 1, padding: 12, borderRadius: 10, alignItems: 'center', backgroundColor: semantic.surface, borderWidth: 1, borderColor: semantic.divider },
  tabActive: { borderColor: semantic.primary, backgroundColor: semantic.primary + '15' },
  tabText: { color: semantic.textSecondary, fontWeight: '600' },
  tabTextActive: { color: semantic.primary },
  summary: { fontSize: 14, color: semantic.textSecondary, marginBottom: 16, fontStyle: 'italic' },
  card: { backgroundColor: semantic.surface, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: semantic.divider },
  cardRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  cardTitle: { fontSize: 16, fontWeight: '600', color: semantic.textPrimary },
  cardScore: { fontSize: 14, fontWeight: '700', color: semantic.success },
  cardMeta: { fontSize: 13, color: semantic.warning, marginTop: 4 },
  reason: { fontSize: 12, color: semantic.textSecondary, marginTop: 2 },
  date: { fontSize: 14, fontWeight: '700', color: semantic.primary, marginBottom: 4 },
  recipeName: { fontSize: 18, fontWeight: '600', color: semantic.textPrimary },
  cuisine: { fontSize: 13, color: semantic.textSecondary, marginTop: 2 },
  ingredients: { fontSize: 13, color: semantic.success, marginTop: 8 },
  missing: { fontSize: 13, color: semantic.danger, marginTop: 2 },
  noRecipe: { fontSize: 14, color: semantic.textTertiary, fontStyle: 'italic', marginTop: 4 },
  empty: { alignItems: 'center', paddingTop: 60, gap: 8 },
  emptyText: { fontSize: 16, color: semantic.textSecondary },
});
