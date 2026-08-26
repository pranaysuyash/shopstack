import { useCallback, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, RefreshControl, ActivityIndicator, Pressable,
} from 'react-native';
import { useFocusEffect } from 'expo-router';
import { useMealPlan, useCreateShoppingList } from '../../src/hooks';
import { Card, EmptyState, Badge, Button, Celebration, RecipeSheet } from '../../src/components';
import { semantic, spacing, typography } from '../../src/theme';
import type { MealPlanDayWire } from '../../src/api/types';
import { hapticSuccess } from '../../src/utils/haptics';

export default function RecipesScreen() {
  const { data, isLoading, isRefetching, refetch } = useMealPlan(7);
  const createList = useCreateShoppingList();
  const [celebrate, setCelebrate] = useState(false);
  const [selectedDay, setSelectedDay] = useState<MealPlanDayWire | undefined>();

  useFocusEffect(
    useCallback(() => {
      refetch();
    }, [refetch])
  );

  const days = data?.items ?? [];
  const tonight = days[0];

  function addMissingToList(day: MealPlanDayWire) {
    const items = day.ingredients_missing.map((name) => ({
      canonical_name: name,
      reason: `For ${day.recipe_name || 'tonight'}`,
    }));
    createList.mutate(
      {
        goal: `Cook ${day.recipe_name || 'tonight'}`,
        items,
      },
      {
        onSuccess: () => {
          hapticSuccess();
          setCelebrate(true);
          setSelectedDay(undefined);
        },
      }
    );
  }

  function openRecipe(day: MealPlanDayWire) {
    setSelectedDay(day);
  }

  if (isLoading && !data) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={semantic.primary} />
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={semantic.primary} />
      }
    >
      <Text style={styles.title}>Cook this week</Text>
      <Text style={styles.subtitle}>{data?.summary || 'Meal suggestions from your pantry'}</Text>

      {tonight && (
        <Card elevated style={styles.tonightCard}>
          <Pressable onPress={() => openRecipe(tonight)}>
            <View style={styles.tonightHeader}>
              <Badge kind="confirm" label="Cook tonight" size="lg" />
              {tonight.cuisine && <Badge kind="watch" label={tonight.cuisine} />}
            </View>
            <Text style={styles.tonightRecipe}>{tonight.recipe_name || 'Use pantry staples'}</Text>
            {tonight.cook_minutes ? <Text style={styles.meta}>{tonight.cook_minutes} min</Text> : null}
            {tonight.ingredients_used.length > 0 && (
              <Text style={styles.ingredients}>
                Uses: {tonight.ingredients_used.slice(0, 5).join(', ')}
              </Text>
            )}
            {tonight.ingredients_missing.length > 0 && (
              <Text style={styles.missing}>
                Missing: {tonight.ingredients_missing.slice(0, 5).join(', ')}
              </Text>
            )}
          </Pressable>
          {tonight.ingredients_missing.length > 0 && (
            <Button
              title={createList.isPending ? 'Adding to list...' : 'Add missing to shopping list'}
              loading={createList.isPending}
              onPress={() => addMissingToList(tonight)}
              style={{ marginTop: spacing[3] }}
            />
          )}
        </Card>
      )}

      {days.length === 0 ? (
        <EmptyState
          motif
          title="No meals planned yet."
          message="Stock a few staples — rice, dal, veggies — and we'll suggest dinners that use what you have."
        />
      ) : (
        days.slice(1).map((day: MealPlanDayWire, i: number) => (
          <Pressable key={`${day.date}-${i}`} onPress={() => openRecipe(day)}>
            <Card style={styles.dayCard}>
              <View style={styles.dayHeader}>
                <Text style={styles.dayName}>{day.date}</Text>
                {day.cuisine && <Badge kind="confirm" label={day.cuisine} />}
              </View>
              <Text style={styles.recipe}>{day.recipe_name || 'Use pantry staples'}</Text>
              {day.cook_minutes ? <Text style={styles.meta}>{day.cook_minutes} min</Text> : null}
              {day.ingredients_used.length > 0 && (
                <Text style={styles.ingredients}>
                  Uses: {day.ingredients_used.slice(0, 5).join(', ')}
                </Text>
              )}
            </Card>
          </Pressable>
        ))
      )}

      <RecipeSheet
        day={selectedDay}
        onClose={() => setSelectedDay(undefined)}
        onAddMissing={addMissingToList}
      />

      <Celebration
        visible={celebrate}
        message="Shopping list ready"
        submessage="Everything you need for tonight's dinner is on the list."
        onDone={() => setCelebrate(false)}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: semantic.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: semantic.background },
  content: { paddingTop: 64, paddingHorizontal: spacing[4], paddingBottom: 32 },
  title: {
    fontSize: typography.sizes['2xl'].size,
    fontWeight: typography.weight.bold,
    color: semantic.textPrimary,
    marginBottom: spacing[1],
  },
  subtitle: {
    fontSize: typography.sizes.base.size,
    color: semantic.textSecondary,
    marginBottom: spacing[5],
  },
  tonightCard: {
    marginBottom: spacing[4],
    padding: spacing[5],
    borderWidth: 2,
    borderColor: semantic.accent,
  },
  tonightHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing[2],
  },
  tonightRecipe: {
    fontSize: typography.sizes['2xl'].size,
    fontWeight: typography.weight.bold,
    color: semantic.textPrimary,
    marginBottom: spacing[1],
  },
  dayCard: {
    marginBottom: spacing[4],
    padding: spacing[4],
  },
  dayHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing[2],
  },
  dayName: {
    fontSize: typography.sizes.xs.size,
    fontWeight: typography.weight.semibold,
    color: semantic.textTertiary,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  recipe: {
    fontSize: typography.sizes.lg.size,
    fontWeight: typography.weight.bold,
    color: semantic.textPrimary,
    marginBottom: spacing[1],
  },
  meta: {
    fontSize: typography.sizes.sm.size,
    color: semantic.textSecondary,
  },
  ingredients: {
    fontSize: typography.sizes.sm.size,
    color: semantic.textSecondary,
    marginTop: spacing[2],
  },
  missing: {
    fontSize: typography.sizes.sm.size,
    color: semantic.danger,
    marginTop: spacing[1],
  },
});
