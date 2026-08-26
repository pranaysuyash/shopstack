import { useState } from 'react';
import {
  View, Text, TextInput, StyleSheet, FlatList, TouchableOpacity,
  RefreshControl, ActivityIndicator, Alert,
} from 'react-native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { listCorrections, createCorrection } from '../src/api/corrections';
import type { CorrectionItemWire } from '../src/api/types';
import { semantic, spacing } from '../src/theme';

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
      setName(''); setWas(''); setShould(''); setReason('');
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
      <Text style={styles.correctionDetail}>{item.was_action} → {item.should_be_action}</Text>
      <Text style={styles.source}>{item.source} · {item.timestamp ? new Date(item.timestamp).toLocaleDateString() : ''}</Text>
    </View>
  );

  if (isLoading && !data) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={semantic.primary} />
      </View>
    );
  }

  const corrections = data?.items ?? [];

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <Text style={styles.header}>Corrections</Text>
        <TouchableOpacity onPress={() => setShowCreate(!showCreate)}>
          <Ionicons name={showCreate ? 'close' : 'add'} size={24} color={semantic.primary} />
        </TouchableOpacity>
      </View>

      {showCreate && (
        <View style={styles.form}>
          <TextInput style={styles.input} placeholder="Item name" placeholderTextColor={semantic.textTertiary} value={name} onChangeText={setName} />
          <TextInput style={styles.input} placeholder="What the system did (was_action)" placeholderTextColor={semantic.textTertiary} value={was} onChangeText={setWas} />
          <TextInput style={styles.input} placeholder="What it should have done" placeholderTextColor={semantic.textTertiary} value={should} onChangeText={setShould} />
          <TextInput style={styles.input} placeholder="Reason (optional)" placeholderTextColor={semantic.textTertiary} value={reason} onChangeText={setReason} />
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
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={semantic.primary} />}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Ionicons name="git-network-outline" size={48} color={semantic.textTertiary} />
            <Text style={styles.emptyText}>No corrections yet</Text>
          </View>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: semantic.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: semantic.background },
  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: spacing[4], paddingTop: 60, paddingBottom: 12 },
  header: { fontSize: 28, fontWeight: '700', color: semantic.textPrimary },
  form: { backgroundColor: semantic.surface, marginHorizontal: spacing[4], borderRadius: 12, padding: spacing[4], marginBottom: 12, borderWidth: 1, borderColor: semantic.divider, gap: 10 },
  input: { backgroundColor: semantic.background, borderRadius: 8, padding: 12, fontSize: 14, color: semantic.textPrimary, borderWidth: 1, borderColor: semantic.divider },
  saveBtn: { backgroundColor: semantic.primary, borderRadius: 8, padding: 12, alignItems: 'center' },
  disabled: { opacity: 0.5 },
  saveText: { color: '#fff', fontWeight: '600' },
  list: { padding: spacing[4], paddingTop: 0 },
  card: { backgroundColor: semantic.surface, borderRadius: 10, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: semantic.divider },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  itemName: { fontSize: 16, fontWeight: '600', color: semantic.textPrimary },
  badge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 },
  acceptedBadge: { backgroundColor: semantic.success + '20' },
  pendingBadge: { backgroundColor: semantic.warning + '20' },
  badgeText: { fontSize: 11, fontWeight: '600' },
  acceptedText: { color: semantic.success },
  pendingText: { color: semantic.warning },
  correctionDetail: { fontSize: 14, color: semantic.textSecondary, marginBottom: 4 },
  source: { fontSize: 12, color: semantic.textTertiary },
  empty: { alignItems: 'center', paddingTop: 60, gap: 8 },
  emptyText: { fontSize: 16, color: semantic.textSecondary },
});
