import { useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, RefreshControl, ActivityIndicator,
} from 'react-native';
import { useFocusEffect } from 'expo-router';
import { useTripSignals } from '../../src/hooks';
import { Card, EmptyState, Badge } from '../../src/components';
import { semantic, spacing, typography } from '../../src/theme';

export default function TripsScreen() {
  const { data, isLoading, isRefetching, refetch } = useTripSignals();

  useFocusEffect(
    useCallback(() => {
      refetch();
    }, [refetch])
  );

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
      <Text style={styles.title}>Trips</Text>
      <Text style={styles.subtitle}>Shopping trip signals from your household</Text>

      <Card elevated style={styles.summaryCard}>
        <View style={styles.statRow}>
          <View style={styles.stat}>
            <Text style={styles.statValue}>{data?.pantry_count ?? 0}</Text>
            <Text style={styles.statLabel}>In pantry</Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statValue}>{data?.use_soon_count ?? 0}</Text>
            <Text style={styles.statLabel}>Use soon</Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statValue}>{data?.low_items_count ?? 0}</Text>
            <Text style={styles.statLabel}>Running low</Text>
          </View>
        </View>
      </Card>

      {data?.has_trip_recommendation ? (
        <Card elevated style={styles.signalCard}>
          <Badge kind="buy" label="Trip recommended" />
          <Text style={styles.signalText}>
            You have items running low and things expiring soon. This is a good time to plan a trip.
          </Text>
        </Card>
      ) : (
        <Card style={styles.signalCard}>
          <Badge kind="watch" label="No trip needed" />
          <Text style={styles.signalText}>
            Pantry looks balanced. We'll let you know when enough items run low to justify a trip.
          </Text>
        </Card>
      )}

      {data?.use_soon_items && data.use_soon_items.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Use before you shop</Text>
          {(data.use_soon_items as Record<string, unknown>[]).slice(0, 5).map((item, i) => (
            <View key={i} style={styles.itemRow}>
              <Text style={styles.itemText}>
                {String(item.display_name || item.canonical_name || 'Item')}
              </Text>
              <Badge kind="useSoon" label="Use soon" />
            </View>
          ))}
        </View>
      )}

      {data?.low_items && data.low_items.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Running low</Text>
          {(data.low_items as Record<string, unknown>[]).slice(0, 5).map((item, i) => (
            <View key={i} style={styles.itemRow}>
              <Text style={styles.itemText}>
                {String(item.display_name || item.canonical_name || 'Item')}
              </Text>
              <Badge kind="buy" label="Buy" />
            </View>
          ))}
        </View>
      )}
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
  summaryCard: {
    marginBottom: spacing[4],
    padding: spacing[4],
  },
  statRow: {
    flexDirection: 'row',
    justifyContent: 'space-around',
  },
  stat: {
    alignItems: 'center',
  },
  statValue: {
    fontSize: typography.sizes['2xl'].size,
    fontWeight: typography.weight.bold,
    color: semantic.primary,
  },
  statLabel: {
    fontSize: typography.sizes.xs.size,
    color: semantic.textSecondary,
    marginTop: spacing[1],
  },
  signalCard: {
    marginBottom: spacing[4],
    padding: spacing[4],
    gap: spacing[3],
  },
  signalText: {
    fontSize: typography.sizes.base.size,
    color: semantic.textSecondary,
    lineHeight: typography.sizes.base.lineHeight,
  },
  section: {
    marginBottom: spacing[5],
  },
  sectionTitle: {
    fontSize: typography.sizes.xs.size,
    fontWeight: typography.weight.semibold,
    color: semantic.textTertiary,
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: spacing[3],
  },
  itemRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing[3],
    borderBottomWidth: 1,
    borderBottomColor: semantic.divider,
  },
  itemText: {
    fontSize: typography.sizes.base.size,
    color: semantic.textPrimary,
  },
});
