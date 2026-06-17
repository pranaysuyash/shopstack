import { useQuery } from '@tanstack/react-query';
import {
  View, Text, StyleSheet, FlatList, RefreshControl, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { listTraces } from '../src/api/traces';
import type { TraceSummaryWire } from '../src/api/types';

export default function TracesScreen() {
  const { data, isLoading, isRefetching, refetch } = useQuery({
    queryKey: ['traces'],
    queryFn: () => listTraces({ limit: 50 }),
    staleTime: 15_000,
  });

  const renderItem = ({ item }: { item: TraceSummaryWire }) => (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <Text style={styles.action}>{item.action || 'command'}</Text>
        <Text style={styles.time}>
          {item.timestamp ? new Date(item.timestamp).toLocaleDateString() : ''}
        </Text>
      </View>
      <Text style={styles.userGoal} numberOfLines={2}>
        {item.user_goal || item.final_response || '(no text)'}
      </Text>
      <View style={styles.cardFooter}>
        <Text style={styles.inputType}>{item.input_type}</Text>
        <Text style={styles.toolCount}>{item.tool_call_count} tool calls</Text>
      </View>
    </View>
  );

  if (isLoading && !data) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#6366f1" />
      </View>
    );
  }

  const traces = data?.items ?? [];

  return (
    <View style={styles.container}>
      <Text style={styles.header}>Command History</Text>
      <FlatList
        data={traces}
        keyExtractor={(item) => item.trace_id}
        renderItem={renderItem}
        refreshControl={
          <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#818cf8" />
        }
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Ionicons name="code-slash-outline" size={48} color="#444" />
            <Text style={styles.emptyText}>No commands yet</Text>
          </View>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f23' },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#0f0f23' },
  header: { fontSize: 28, fontWeight: '700', color: '#e0e0ff', paddingHorizontal: 16, paddingTop: 60, paddingBottom: 12 },
  list: { padding: 16, paddingTop: 0 },
  card: { backgroundColor: '#1a1a3e', borderRadius: 10, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: '#2a2a5e' },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
  action: { fontSize: 13, fontWeight: '700', color: '#818cf8', textTransform: 'uppercase' },
  time: { fontSize: 12, color: '#666' },
  userGoal: { fontSize: 14, color: '#c0c0dd', marginBottom: 8, lineHeight: 20 },
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between' },
  inputType: { fontSize: 11, color: '#8888bb', backgroundColor: '#0f0f23', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4 },
  toolCount: { fontSize: 11, color: '#666' },
  empty: { alignItems: 'center', paddingTop: 60, gap: 8 },
  emptyText: { fontSize: 16, color: '#666' },
});
