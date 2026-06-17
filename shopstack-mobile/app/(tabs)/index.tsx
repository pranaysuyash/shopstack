import { useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, RefreshControl, ActivityIndicator } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from 'expo-router';
import { getTodaySnapshot } from '../../src/api/dashboard';

interface StatCardProps {
  title: string;
  count: number;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
}

function StatCard({ title, count, icon, color }: StatCardProps) {
  return (
    <View style={[styles.card, { borderLeftColor: color }]}>
      <Ionicons name={icon} size={24} color={color} />
      <Text style={[styles.count, { color }]}>{count}</Text>
      <Text style={styles.cardTitle}>{title}</Text>
    </View>
  );
}

export default function DashboardScreen() {
  const { data, isLoading, isRefetching, refetch } = useQuery({
    queryKey: ['dashboard', 'today'],
    queryFn: getTodaySnapshot,
    staleTime: 15_000,
  });

  useFocusEffect(
    useCallback(() => {
      refetch();
    }, [])
  );

  if (isLoading && !data) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#6366f1" />
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#818cf8" />
      }
    >
      <Text style={styles.header}>Today</Text>
      <Text style={styles.subheader}>Your household snapshot</Text>

      <View style={styles.grid}>
        <StatCard
          title="In Pantry"
          count={data?.pantry_count ?? 0}
          icon="cube-outline"
          color="#6366f1"
        />
        <StatCard
          title="Use Soon"
          count={data?.use_soon_count ?? 0}
          icon="alert-circle-outline"
          color="#f59e0b"
        />
        <StatCard
          title="Low Items"
          count={data?.low_items_count ?? 0}
          icon="warning-outline"
          color="#ef4444"
        />
        <StatCard
          title="Recent Buys"
          count={data?.recent_purchases_count ?? 0}
          icon="receipt-outline"
          color="#22c55e"
        />
      </View>

      {data?.use_soon_items && data.use_soon_items.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Use Soon</Text>
          {data.use_soon_items.slice(0, 5).map((item: Record<string, unknown>, i: number) => (
            <View key={i} style={styles.itemRow}>
              <Ionicons name="time-outline" size={16} color="#f59e0b" />
              <Text style={styles.itemText}>
                {String(item?.display_name || item?.canonical_name || 'Item')}
              </Text>
            </View>
          ))}
        </View>
      )}

      {data?.low_items && data.low_items.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Running Low</Text>
          {data.low_items.slice(0, 5).map((item: Record<string, unknown>, i: number) => (
            <View key={i} style={styles.itemRow}>
              <Ionicons name="caret-down-outline" size={16} color="#ef4444" />
              <Text style={styles.itemText}>
                {String(item?.display_name || item?.canonical_name || 'Item')}
              </Text>
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f23' },
  content: { padding: 16, paddingTop: 60 },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#0f0f23' },
  header: { fontSize: 28, fontWeight: '700', color: '#e0e0ff' },
  subheader: { fontSize: 14, color: '#8888bb', marginBottom: 24 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 24 },
  card: {
    flex: 1,
    minWidth: '45%',
    backgroundColor: '#1a1a3e',
    borderRadius: 12,
    padding: 16,
    borderLeftWidth: 3,
    borderWidth: 1,
    borderColor: '#2a2a5e',
    gap: 4,
  },
  count: { fontSize: 32, fontWeight: '700', marginTop: 4 },
  cardTitle: { fontSize: 12, color: '#8888bb', fontWeight: '500' },
  section: { backgroundColor: '#1a1a3e', borderRadius: 12, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: '#2a2a5e' },
  sectionTitle: { fontSize: 16, fontWeight: '600', color: '#e0e0ff', marginBottom: 12 },
  itemRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#2a2a5e' },
  itemText: { fontSize: 14, color: '#c0c0dd', flex: 1 },
});
