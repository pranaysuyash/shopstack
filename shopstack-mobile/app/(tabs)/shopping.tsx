import { useState, useCallback } from 'react';
import {
  View, Text, TextInput, StyleSheet, FlatList, TouchableOpacity,
  RefreshControl, ActivityIndicator, Alert,
} from 'react-native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useFocusEffect, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getActiveList, createList, completeList } from '../../src/api/shopping';
import type { ShoppingListItemWire, ShoppingItemInput } from '../../src/api/types';

const PRIORITY_COLORS: Record<string, string> = {
  must_buy: '#ef4444',
  optional: '#f59e0b',
  avoid_buying: '#666',
};

export default function ShoppingScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [goal, setGoal] = useState('');
  const [newItem, setNewItem] = useState('');

  const { data, isLoading, isRefetching, refetch } = useQuery({
    queryKey: ['shopping', 'active'],
    queryFn: getActiveList,
    staleTime: 10_000,
  });

  useFocusEffect(useCallback(() => { refetch(); }, []));

  const createMutation = useMutation({
    mutationFn: () => {
      const items: ShoppingItemInput[] = newItem.trim()
        ? newItem.split(',').map((n) => ({ canonical_name: n.trim() }))
        : [];
      return createList({ goal: goal.trim(), items });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shopping'] });
      setShowCreate(false);
      setGoal('');
      setNewItem('');
    },
    onError: (err: Error) => Alert.alert('Error', err.message),
  });

  const completeMutation = useMutation({
    mutationFn: () => completeList(data!.list_id),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['shopping'] });
      Alert.alert(
        'List Complete',
        `${result.items_added.length} items added to inventory. ${result.items_skipped} skipped.`,
      );
    },
    onError: (err: Error) => Alert.alert('Error', err.message),
  });

  const hasActiveList = data && data.list_id && data.list_id.length > 0;
  const items = data?.items ?? [];

  const renderItem = ({ item }: { item: ShoppingListItemWire }) => (
    <View style={styles.itemCard}>
      <View style={[styles.priorityDot, { backgroundColor: PRIORITY_COLORS[item.priority] || '#666' }]} />
      <View style={styles.itemInfo}>
        <Text style={[styles.itemName, item.status === 'bought' && styles.bought]}>
          {item.canonical_name}
        </Text>
        <Text style={styles.itemDetail}>
          {item.requested_quantity ? `${item.requested_quantity} ${item.unit || ''}` : ''}
          {item.reason ? ` — ${item.reason}` : ''}
        </Text>
      </View>
      <Text style={styles.priority}>{item.priority}</Text>
    </View>
  );

  if (isLoading && !data) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#6366f1" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <Text style={styles.header}>Shopping</Text>
        {!showCreate && (
          <TouchableOpacity style={styles.addBtn} onPress={() => setShowCreate(true)}>
            <Ionicons name="add" size={24} color="#818cf8" />
          </TouchableOpacity>
        )}
      </View>

      {showCreate && (
        <View style={styles.createForm}>
          <TextInput
            style={styles.input}
            placeholder="Shopping goal (optional)"
            placeholderTextColor="#666"
            value={goal}
            onChangeText={setGoal}
          />
          <TextInput
            style={styles.input}
            placeholder="Items: milk, eggs, bread (comma-separated)"
            placeholderTextColor="#666"
            value={newItem}
            onChangeText={setNewItem}
          />
          <TouchableOpacity
            style={[styles.saveBtn, createMutation.isPending && styles.disabled]}
            onPress={() => createMutation.mutate()}
            disabled={createMutation.isPending}
          >
            <Text style={styles.saveText}>
              {createMutation.isPending ? 'Creating...' : 'Create Shopping List'}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setShowCreate(false)}>
            <Text style={styles.cancelText}>Cancel</Text>
          </TouchableOpacity>
        </View>
      )}

      {!hasActiveList && !showCreate && (
        <View style={styles.empty}>
          <Ionicons name="cart-outline" size={48} color="#444" />
          <Text style={styles.emptyText}>No active shopping list</Text>
          <Text style={styles.emptySubtext}>Tap + to create one</Text>
        </View>
      )}

      {hasActiveList && (
        <>
          {data!.goal ? <Text style={styles.goal}>🎯 {data!.goal}</Text> : null}
          <FlatList
            data={items}
            keyExtractor={(item) => item.item_id}
            renderItem={renderItem}
            refreshControl={
              <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#818cf8" />
            }
            contentContainerStyle={styles.list}
          />
          <View style={styles.bottomBar}>
            <TouchableOpacity
              style={styles.completeBtn}
              onPress={() => completeMutation.mutate()}
              disabled={completeMutation.isPending}
            >
              <Text style={styles.completeText}>
                {completeMutation.isPending ? 'Completing...' : 'Complete List → Pantry'}
              </Text>
            </TouchableOpacity>
          </View>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f23' },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#0f0f23' },
  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingTop: 60, paddingBottom: 12 },
  header: { fontSize: 28, fontWeight: '700', color: '#e0e0ff' },
  addBtn: { padding: 8 },
  createForm: { backgroundColor: '#1a1a3e', marginHorizontal: 16, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: '#2a2a5e', gap: 12 },
  input: { backgroundColor: '#0f0f23', borderRadius: 8, padding: 12, fontSize: 14, color: '#e0e0ff', borderWidth: 1, borderColor: '#2a2a5e' },
  saveBtn: { backgroundColor: '#6366f1', borderRadius: 8, padding: 12, alignItems: 'center' },
  disabled: { opacity: 0.5 },
  saveText: { color: '#fff', fontWeight: '600' },
  cancelText: { color: '#8888bb', textAlign: 'center', padding: 8 },
  goal: { fontSize: 14, color: '#22c55e', paddingHorizontal: 16, paddingBottom: 8, fontWeight: '500' },
  list: { padding: 16, paddingTop: 0 },
  itemCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1a1a3e', borderRadius: 10, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: '#2a2a5e' },
  priorityDot: { width: 4, height: 32, borderRadius: 2, marginRight: 12 },
  itemInfo: { flex: 1 },
  itemName: { fontSize: 16, fontWeight: '600', color: '#e0e0ff' },
  bought: { textDecorationLine: 'line-through', color: '#666' },
  itemDetail: { fontSize: 12, color: '#8888bb', marginTop: 2 },
  priority: { fontSize: 11, color: '#666', fontWeight: '500', textTransform: 'uppercase' },
  bottomBar: { padding: 16, borderTopWidth: 1, borderTopColor: '#2a2a5e' },
  completeBtn: { backgroundColor: '#22c55e', borderRadius: 10, padding: 16, alignItems: 'center' },
  completeText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  empty: { alignItems: 'center', paddingTop: 80, gap: 8 },
  emptyText: { fontSize: 18, color: '#666', fontWeight: '600' },
  emptySubtext: { fontSize: 14, color: '#555' },
});
