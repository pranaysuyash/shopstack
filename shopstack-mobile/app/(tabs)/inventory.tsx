import { useState, useCallback } from 'react';
import {
  View, Text, TextInput, StyleSheet, FlatList, TouchableOpacity,
  RefreshControl, ActivityIndicator, Alert,
} from 'react-native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useFocusEffect, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { listLots, addLot, consumeLot } from '../../src/api/inventory';
import type { InventoryLot } from '../../src/api/types';

export default function InventoryScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState('');
  const [newQty, setNewQty] = useState('1');
  const [newUnit, setNewUnit] = useState('unit');
  const [consumeQty, setConsumeQty] = useState<Record<string, string>>({});

  const { data, isLoading, isRefetching, refetch } = useQuery({
    queryKey: ['inventory', 'lots'],
    queryFn: () => listLots({ limit: 200 }),
    staleTime: 10_000,
  });

  useFocusEffect(useCallback(() => { refetch(); }, []));

  const addMutation = useMutation({
    mutationFn: () => addLot({
      canonical_name: newName.trim(),
      quantity: parseFloat(newQty) || 1,
      unit: newUnit.trim() || 'unit',
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['inventory'] });
      setShowAdd(false);
      setNewName('');
      setNewQty('1');
      setNewUnit('unit');
    },
    onError: (err: Error) => Alert.alert('Error', err.message),
  });

  const consumeMutation = useMutation({
    mutationFn: ({ lotId, qty }: { lotId: string; qty: number }) =>
      consumeLot(lotId, qty),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['inventory'] }),
    onError: (err: Error) => Alert.alert('Error', err.message),
  });

  const lots = data?.items ?? [];

  const renderItem = ({ item }: { item: InventoryLot }) => (
    <View style={styles.lotCard}>
      <View style={styles.lotHeader}>
        <View style={styles.lotInfo}>
          <Text style={styles.lotName}>{item.display_name || item.canonical_name}</Text>
          <Text style={styles.lotDetail}>
            {item.quantity} {item.unit}
            {item.storage_location_name ? ` · ${item.storage_location_name}` : ''}
          </Text>
        </View>
        <View style={styles.lotActions}>
          <TextInput
            style={styles.consumeInput}
            value={consumeQty[item.lot_id] || ''}
            onChangeText={(v) => setConsumeQty((p) => ({ ...p, [item.lot_id]: v }))}
            placeholder="qty"
            placeholderTextColor="#555"
            keyboardType="decimal-pad"
          />
          <TouchableOpacity
            style={styles.consumeBtn}
            onPress={() => {
              const qty = parseFloat(consumeQty[item.lot_id] || '0');
              if (qty > 0) {
                consumeMutation.mutate({ lotId: item.lot_id, qty });
                setConsumeQty((p) => ({ ...p, [item.lot_id]: '' }));
              }
            }}
          >
            <Ionicons name="remove-circle-outline" size={20} color="#ef4444" />
          </TouchableOpacity>
        </View>
      </View>
      {item.label_expiry_date && (
        <Text style={styles.expiry}>Expires: {item.label_expiry_date}</Text>
      )}
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
        <Text style={styles.header}>Pantry</Text>
        <TouchableOpacity style={styles.addBtn} onPress={() => setShowAdd(!showAdd)}>
          <Ionicons name={showAdd ? 'close' : 'add'} size={24} color="#818cf8" />
        </TouchableOpacity>
      </View>

      {showAdd && (
        <View style={styles.addForm}>
          <TextInput
            style={styles.input}
            placeholder="Item name"
            placeholderTextColor="#666"
            value={newName}
            onChangeText={setNewName}
          />
          <View style={styles.addRow}>
            <TextInput
              style={[styles.input, styles.qtyInput]}
              placeholder="Qty"
              placeholderTextColor="#666"
              value={newQty}
              onChangeText={setNewQty}
              keyboardType="decimal-pad"
            />
            <TextInput
              style={[styles.input, styles.unitInput]}
              placeholder="Unit"
              placeholderTextColor="#666"
              value={newUnit}
              onChangeText={setNewUnit}
            />
          </View>
          <TouchableOpacity
            style={[styles.saveBtn, !newName.trim() && styles.disabled]}
            onPress={() => addMutation.mutate()}
            disabled={!newName.trim() || addMutation.isPending}
          >
            <Text style={styles.saveText}>
              {addMutation.isPending ? 'Adding...' : 'Add to Pantry'}
            </Text>
          </TouchableOpacity>
        </View>
      )}

      <FlatList
        data={lots}
        keyExtractor={(item) => item.lot_id}
        renderItem={renderItem}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#818cf8" />}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Ionicons name="cube-outline" size={48} color="#444" />
            <Text style={styles.emptyText}>Your pantry is empty</Text>
            <Text style={styles.emptySubtext}>Add your first item above</Text>
          </View>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f23' },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#0f0f23' },
  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingTop: 60, paddingBottom: 12 },
  header: { fontSize: 28, fontWeight: '700', color: '#e0e0ff' },
  addBtn: { padding: 8 },
  addForm: { backgroundColor: '#1a1a3e', marginHorizontal: 16, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: '#2a2a5e', gap: 12 },
  input: { backgroundColor: '#0f0f23', borderRadius: 8, padding: 12, fontSize: 14, color: '#e0e0ff', borderWidth: 1, borderColor: '#2a2a5e', flex: 1 },
  addRow: { flexDirection: 'row', gap: 8 },
  qtyInput: { flex: 1 },
  unitInput: { flex: 1 },
  saveBtn: { backgroundColor: '#6366f1', borderRadius: 8, padding: 12, alignItems: 'center' },
  disabled: { opacity: 0.5 },
  saveText: { color: '#fff', fontWeight: '600' },
  list: { padding: 16, paddingTop: 0 },
  lotCard: { backgroundColor: '#1a1a3e', borderRadius: 10, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: '#2a2a5e' },
  lotHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  lotInfo: { flex: 1 },
  lotName: { fontSize: 16, fontWeight: '600', color: '#e0e0ff' },
  lotDetail: { fontSize: 13, color: '#8888bb', marginTop: 2 },
  lotActions: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  consumeInput: { backgroundColor: '#0f0f23', borderRadius: 6, padding: 6, width: 50, color: '#e0e0ff', textAlign: 'center', fontSize: 13, borderWidth: 1, borderColor: '#333' },
  consumeBtn: { padding: 4 },
  expiry: { fontSize: 12, color: '#f59e0b', marginTop: 6 },
  empty: { alignItems: 'center', paddingTop: 60, gap: 8 },
  emptyText: { fontSize: 18, color: '#666', fontWeight: '600' },
  emptySubtext: { fontSize: 14, color: '#555' },
});
