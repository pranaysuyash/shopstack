import { useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity, RefreshControl,
  ActivityIndicator, Alert,
} from 'react-native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getActiveList } from '../src/api/shopping';
import { toggleStoreMode } from '../src/api/account';
import type { ShoppingListItemWire } from '../src/api/types';

export default function StoreModeScreen() {
  const queryClient = useQueryClient();
  const [toggling, setToggling] = useState<string | null>(null);

  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['shopping', 'active', 'store-mode'],
    queryFn: getActiveList,
    staleTime: 5_000,
  });

  useFocusEffect(useCallback(() => { refetch(); }, []));

  const toggleMutation = useMutation({
    mutationFn: async (itemId: string) => {
      setToggling(itemId);
      try {
        return await toggleStoreMode({ item_id: itemId });
      } finally {
        setToggling(null);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shopping'] });
    },
    onError: (err: Error) => Alert.alert('Error', err.message),
  });

  const hasActiveList = data && data.list_id && data.list_id.length > 0;
  const items = data?.items ?? [];
  const pending = items.filter((i: ShoppingListItemWire) => i.status !== 'bought');
  const bought = items.filter((i: ShoppingListItemWire) => i.status === 'bought');
  const progress = items.length > 0 ? Math.round((bought.length / items.length) * 100) : 0;

  if (isLoading && !data) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#6366f1" />
      </View>
    );
  }

  if (!hasActiveList) {
    return (
      <View style={styles.centered}>
        <Ionicons name="cart-outline" size={48} color="#444" />
        <Text style={styles.emptyText}>No active shopping list</Text>
        <Text style={styles.emptySubtext}>Create one in the Shopping tab</Text>
      </View>
    );
  }

  const renderItem = ({ item }: { item: ShoppingListItemWire }) => {
    const isBought = item.status === 'bought';
    return (
      <TouchableOpacity
        style={[styles.item, isBought && styles.itemBought]}
        onPress={() => toggleMutation.mutate(item.item_id)}
        disabled={toggling === item.item_id}
      >
        <View style={[styles.checkbox, isBought && styles.checkboxChecked]}>
          {isBought && <Ionicons name="checkmark" size={16} color="#fff" />}
          {toggling === item.item_id && !isBought && (
            <ActivityIndicator size="small" color="#818cf8" />
          )}
        </View>
        <View style={styles.itemInfo}>
          <Text style={[styles.itemName, isBought && styles.itemNameBought]}>
            {item.canonical_name}
          </Text>
          {item.requested_quantity && (
            <Text style={styles.itemQty}>
              {item.requested_quantity} {item.unit || ''}
            </Text>
          )}
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <View style={styles.container}>
      <View style={styles.headerSection}>
        <Text style={styles.header}>Store Mode</Text>
        <View style={styles.progressBar}>
          <View style={[styles.progressFill, { width: `${progress}%` }]} />
        </View>
        <Text style={styles.progressText}>
          {bought.length} / {items.length} items ({progress}%)
        </Text>
      </View>

      <FlatList
        data={[...pending, ...bought]}
        keyExtractor={(item) => item.item_id}
        renderItem={renderItem}
        refreshControl={
          <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#818cf8" />
        }
        contentContainerStyle={styles.list}
        ListHeaderComponent={
          pending.length > 0 ? (
            <Text style={styles.sectionLabel}>To Get</Text>
          ) : null
        }
        ListFooterComponent={
          bought.length > 0 && pending.length === 0 ? (
            <View style={styles.allDone}>
              <Ionicons name="checkmark-circle" size={48} color="#22c55e" />
              <Text style={styles.allDoneText}>All done!</Text>
            </View>
          ) : null
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f23' },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#0f0f23', gap: 8, padding: 24 },
  headerSection: { padding: 16, paddingTop: 60, paddingBottom: 8 },
  header: { fontSize: 28, fontWeight: '700', color: '#e0e0ff', marginBottom: 16 },
  progressBar: { height: 6, backgroundColor: '#1a1a3e', borderRadius: 3, marginBottom: 6 },
  progressFill: { height: '100%', backgroundColor: '#22c55e', borderRadius: 3 },
  progressText: { fontSize: 13, color: '#8888bb', textAlign: 'right' },
  list: { padding: 16, paddingTop: 0 },
  sectionLabel: { fontSize: 13, fontWeight: '600', color: '#666', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8, marginTop: 8 },
  item: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1a1a3e', borderRadius: 10, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: '#2a2a5e' },
  itemBought: { opacity: 0.5, borderColor: '#22c55e40' },
  checkbox: { width: 28, height: 28, borderRadius: 8, borderWidth: 2, borderColor: '#444', justifyContent: 'center', alignItems: 'center', marginRight: 12 },
  checkboxChecked: { backgroundColor: '#22c55e', borderColor: '#22c55e' },
  itemInfo: { flex: 1 },
  itemName: { fontSize: 16, fontWeight: '600', color: '#e0e0ff' },
  itemNameBought: { textDecorationLine: 'line-through', color: '#666' },
  itemQty: { fontSize: 13, color: '#8888bb', marginTop: 2 },
  emptyText: { fontSize: 18, color: '#666', fontWeight: '600' },
  emptySubtext: { fontSize: 14, color: '#555' },
  allDone: { alignItems: 'center', paddingTop: 40, gap: 8 },
  allDoneText: { fontSize: 20, fontWeight: '700', color: '#22c55e' },
});
