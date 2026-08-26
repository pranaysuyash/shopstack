import { useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, RefreshControl, ActivityIndicator,
} from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import { useToday } from '../../src/hooks';
import { TodayStory, ActionTile, EmptyState, Card, Skeleton, DecisionBanner } from '../../src/components/composite';
import { semantic, spacing, typography } from '../../src/theme';

export default function HomeScreen() {
  const router = useRouter();
  const { data, isLoading, isRefetching, refetch } = useToday();

  useFocusEffect(
    useCallback(() => {
      refetch();
    }, [refetch])
  );

  const storyItems =
    (data?.use_soon_items ?? []).map((it: Record<string, unknown>) => ({
      canonical_name: String(it.canonical_name || it.display_name || ''),
      display_name: String(it.display_name || it.canonical_name || ''),
      action: 'use_soon',
      reason: 'Use soon to avoid waste',
    })) || [];

  const lowItems = (data?.low_items ?? []) as Record<string, unknown>[];
  const topDecision =
    storyItems.length > 0
      ? { action: 'use_soon', title: `Use ${storyItems[0].display_name} first`, reason: 'It will spoil soon' }
      : lowItems.length > 0
        ? { action: 'buy', title: `Restock ${String(lowItems[0].display_name || lowItems[0].canonical_name || 'low item')}`, reason: 'Running low' }
        : null;

  if (isLoading && !data) {
    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        <Skeleton width={140} height={24} style={{ marginBottom: spacing[2] }} />
        <Skeleton width={260} height={36} style={{ marginBottom: spacing[6] }} />
        <Skeleton height={120} style={{ marginHorizontal: spacing[4], marginBottom: spacing[5] }} />
        <View style={styles.grid}>
          <Skeleton height={120} style={{ flex: 1, minWidth: '30%' }} />
          <Skeleton height={120} style={{ flex: 1, minWidth: '30%' }} />
          <Skeleton height={120} style={{ flex: 1, minWidth: '30%' }} />
        </View>
      </ScrollView>
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
      <Text style={styles.greeting}>Good day,</Text>
      <Text style={styles.title}>What should we do today?</Text>

      {topDecision ? (
        <DecisionBanner
          action={topDecision.action}
          title={topDecision.title}
          reason={topDecision.reason}
          onPress={() =>
            router.push(topDecision.action === 'buy' ? '/shopping' : '/inventory')
          }
        />
      ) : null}

      <View style={styles.grid}>
        <ActionTile
          icon="cart-outline"
          title="Buy"
          subtitle="Restock"
          color={semantic.primary}
          onPress={() => router.push('/shopping')}
        />
        <ActionTile
          icon="time-outline"
          title="Use"
          subtitle="Avoid waste"
          color={semantic.warning}
          onPress={() => router.push('/inventory')}
        />
        <ActionTile
          icon="restaurant-outline"
          title="Cook"
          subtitle="Tonight"
          color={semantic.terracotta[500]}
          onPress={() => router.push('/recipes')}
        />
      </View>

      {storyItems.length > 0 ? (
        <TodayStory
          kicker="Top actions"
          headline="Use these first"
          items={storyItems}
        />
) : (
          <Card elevated style={styles.emptyCard}>
            <EmptyState
              motif
              title="Pantry's empty. That's a fresh start."
              message={ `Tap "Add first item" and we'll learn what you cook, when you shop, and what to remind you about.` }
              action={{ label: 'Add first item', onPress: () => router.push('/inventory') }}
            />
          </Card>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: semantic.background },
  content: { paddingTop: 64, paddingBottom: 32 },
  greeting: {
    fontSize: typography.sizes.base.size,
    color: semantic.textSecondary,
    paddingHorizontal: spacing[4],
  },
  title: {
    fontSize: typography.sizes['3xl'].size,
    fontWeight: typography.weight.bold,
    color: semantic.textPrimary,
    lineHeight: typography.sizes['3xl'].lineHeight,
    paddingHorizontal: spacing[4],
    marginBottom: spacing[5],
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing[3],
    paddingHorizontal: spacing[4],
    marginBottom: spacing[5],
  },
  emptyCard: {
    marginHorizontal: spacing[4],
  },
});
