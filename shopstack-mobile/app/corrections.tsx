import { useState } from 'react';
import {
  View, Text, TextInput, StyleSheet, FlatList, TouchableOpacity,
  RefreshControl, ActivityIndicator, Alert,
} from 'react-native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { listCorrections, createCorrection } from '../src/api/corrections';
import type { CorrectionItemWire } from '../src/api/types';

export default function CorrectionsScreen() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState('');
  const [was, setWas] = useState('');
  const [should, setShould] = useState('');
  const [reason, setReason] = useState('');

  const { data, isLoading, isRefetching, refetch } = useQuery({
    queryKey: ['corrections'],
    queryFn: () => listCorrections({ limit: 50 }),
    staleTime: 15_000,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createCorrection({
        canonical_name: name.trim(),
        was_action: was.trim(),
        should_be_action: should.trim(),
        reason: reason.trim() || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['corrections'] });
      setShowCreate(false);
      setName('');
      setWas('');
      setShould('');
      setReason('');
    },
    onError: (err: Error) => Alert.alert('Error', err.message),
  });

  const renderItem = ({ item }: { item: CorrectionItemWire }) => (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <Text style={styles.itemName}>{item.canonical_name}</Text>
        <View style={[styles.badge, item.accepted ? styles.acceptedBadge : styles.pendingBadge]}>
          <Text style={[styles.badgeText, item.accepted ? styles.acceptedText : styles.pendingText]}>
            {item.accepted ? 'Accepted' : 'Pending'}
          </Text>
        </View>
      </View>
      <Text style={styles.correctionDetail}>
        {item.was_action} → {item.should_be_action}
      </Text>
      <Text style={styles.source}>{item.source} · {item.timestamp ? new Date(item.timestamp).toLocaleDateString() : ''}</Text>
    </View>
  );

  if (isLoading && !data) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#6366f1" />
      </View>
    );
  }

  const corrections = data?.items ?? [];

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <Text style={styles.header}>Corrections</Text>
        <TouchableOpacity onPress={() => setShowCreate(!showCreate)}>
          <Ionicons name={showCreate ? 'close' : 'add'} size={24} color="#818cf8" />
        </TouchableOpacity>
      </View>

      {showCreate && (
        <View style={styles.form}>
          <TextInput style={styles.input} placeholder="Item name" placeholderTextColor="#666" value={name} onChangeText={setName} />
          <TextInput style={styles.input} placeholder="What the system did (was_action)" placeholderTextColor="#666" value={was} onChangeText={setWas} />
          <TextInput style={styles.input} placeholder="What it should have done" placeholderTextColor="#666" value={should} onChangeText={setShould} />
          <TextInput style={styles.input} placeholder="Reason (optional)" placeholderTextColor="#666" value={reason} onChangeText={setReason} />
          <TouchableOpacity
            style={[styles.saveBtn, (!name || !was || !should || createMutation.isPending) && styles.disabled]}
            onPress={() => createMutation.mutate()}
            disabled={!name || !was || !should || createMutation.isPending}
          >
            <Text style={styles.saveText}>{createMutation.isPending ? 'Saving...' : 'Record Correction'}</Text>
          </TouchableOpacity>
        </View>
      )}

      <FlatList
        data={corrections}
        keyExtractor={(item) => item.event_id}
        renderItem={renderItem}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#818cf8" />}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Ionicons name="git-network-outline" size={48} color="#444" />
            <Text style={styles.emptyText}>No corrections yet</Text>
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
  form: { backgroundColor: '#1a1a3e', marginHorizontal: 16, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: '#2a2a5e', gap: 10 },
  input: { backgroundColor: '#0f0f23', borderRadius: 8, padding: 12, fontSize: 14, color: '#e0e0ff', borderWidth: 1, borderColor: '#2a2a5e' },
  saveBtn: { backgroundColor: '#6366f1', borderRadius: 8, padding: 12, alignItems: 'center' },
  disabled: { opacity: 0.5 },
  saveText: { color: '#fff', fontWeight: '600' },
  list: { padding: 16, paddingTop: 0 },
  card: { backgroundColor: '#1a1a3e', borderRadius: 10, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: '#2a2a5e' },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  itemName: { fontSize: 16, fontWeight: '600', color: '#e0e0ff' },
  badge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 },
  acceptedBadge: { backgroundColor: '#22c55e20' },
  pendingBadge: { backgroundColor: '#f59e0b20' },
  badgeText: { fontSize: 11, fontWeight: '600' },
  acceptedText: { color: '#22c55e' },
  pendingText: { color: '#f59e0b' },
  correctionDetail: { fontSize: 14, color: '#c0c0dd', marginBottom: 4 },
  source: { fontSize: 12, color: '#666' },
  empty: { alignItems: 'center', paddingTop: 60, gap: 8 },
  emptyText: { fontSize: 16, color: '#666' },
});
