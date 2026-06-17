import { useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Alert, ActivityIndicator,
} from 'react-native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getRetentionSummary, purgeData, undo } from '../src/api/account';
import { whoami } from '../src/api/auth';

export default function AccountScreen() {
  const queryClient = useQueryClient();

  const whoamiQuery = useQuery({
    queryKey: ['whoami'],
    queryFn: whoami,
    staleTime: 60_000,
  });

  const retentionQuery = useQuery({
    queryKey: ['retention'],
    queryFn: getRetentionSummary,
    staleTime: 30_000,
  });

  useFocusEffect(useCallback(() => {
    whoamiQuery.refetch();
    retentionQuery.refetch();
  }, []));

  const undoMutation = useMutation({
    mutationFn: () => undo(),
    onSuccess: (result) => {
      Alert.alert(result.success ? 'Undone' : 'Nothing to Undo', result.message);
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
    onError: (err: Error) => Alert.alert('Error', err.message),
  });

  const purgeMutation = useMutation({
    mutationFn: () => purgeData(),
    onSuccess: (result) => {
      Alert.alert('Data Purged', `Traces: ${result.traces_purged}, Errors: ${result.errors.length}`);
    },
    onError: (err: Error) => Alert.alert('Error', err.message),
  });

  const info = whoamiQuery.data;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.header}>Account & Privacy</Text>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Server</Text>
        <View style={styles.infoCard}>
          <Text style={styles.infoLabel}>App</Text>
          <Text style={styles.infoValue}>{info?.app_name ?? '...'} v{info?.app_version ?? '?'}</Text>
        </View>
        <View style={styles.infoCard}>
          <Text style={styles.infoLabel}>Household</Text>
          <Text style={styles.infoValue}>{info?.household_name ?? info?.household_id ?? '...'}</Text>
        </View>
        <View style={styles.infoCard}>
          <Text style={styles.infoLabel}>Mode</Text>
          <Text style={styles.infoValue}>{info?.runtime_mode ?? '...'}</Text>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Retention</Text>
        {retentionQuery.data ? (
          <View style={styles.retentionGrid}>
            <View style={styles.retentionItem}>
              <Text style={styles.retentionValue}>{retentionQuery.data.summary.trace_ttl_days}d</Text>
              <Text style={styles.retentionLabel}>Trace TTL</Text>
            </View>
            <View style={styles.retentionItem}>
              <Text style={styles.retentionValue}>{retentionQuery.data.summary.trace_max_rows}</Text>
              <Text style={styles.retentionLabel}>Max Traces</Text>
            </View>
            <View style={styles.retentionItem}>
              <Text style={styles.retentionValue}>{retentionQuery.data.summary.voice_memo_retention_days}d</Text>
              <Text style={styles.retentionLabel}>Voice Memos</Text>
            </View>
            <View style={styles.retentionItem}>
              <Text style={styles.retentionValue}>{retentionQuery.data.summary.backup_retention_days}d</Text>
              <Text style={styles.retentionLabel}>Backups</Text>
            </View>
          </View>
        ) : (
          <ActivityIndicator size="small" color="#6366f1" />
        )}
      </View>

      <View style={styles.actions}>
        <TouchableOpacity
          style={[styles.actionBtn, undoMutation.isPending && styles.disabled]}
          onPress={() => undoMutation.mutate()}
          disabled={undoMutation.isPending}
        >
          <Ionicons name="arrow-undo-outline" size={20} color="#f59e0b" />
          <Text style={styles.actionText}>Undo Last Action</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.dangerBtn, purgeMutation.isPending && styles.disabled]}
          onPress={() => {
            Alert.alert(
              'Purge All Data',
              'This removes traces, community data, and voice memos. Inventory and lists are kept. Continue?',
              [
                { text: 'Cancel', style: 'cancel' },
                { text: 'Purge', style: 'destructive', onPress: () => purgeMutation.mutate() },
              ],
            );
          }}
          disabled={purgeMutation.isPending}
        >
          <Ionicons name="trash-outline" size={20} color="#ef4444" />
          <Text style={styles.dangerText}>Purge User Data</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f23' },
  content: { padding: 16, paddingTop: 60, paddingBottom: 40 },
  header: { fontSize: 28, fontWeight: '700', color: '#e0e0ff', marginBottom: 24 },
  section: { marginBottom: 24 },
  sectionTitle: { fontSize: 13, fontWeight: '600', color: '#666', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 },
  infoCard: { flexDirection: 'row', justifyContent: 'space-between', backgroundColor: '#1a1a3e', padding: 14, borderRadius: 10, marginBottom: 6, borderWidth: 1, borderColor: '#2a2a5e' },
  infoLabel: { fontSize: 14, color: '#8888bb' },
  infoValue: { fontSize: 14, fontWeight: '600', color: '#e0e0ff' },
  retentionGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  retentionItem: { flex: 1, minWidth: '45%', backgroundColor: '#1a1a3e', borderRadius: 10, padding: 16, alignItems: 'center', borderWidth: 1, borderColor: '#2a2a5e' },
  retentionValue: { fontSize: 24, fontWeight: '700', color: '#818cf8' },
  retentionLabel: { fontSize: 12, color: '#8888bb', marginTop: 4 },
  actions: { gap: 12 },
  actionBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#1a1a3e', padding: 16, borderRadius: 12, borderWidth: 1, borderColor: '#2a2a5e' },
  actionText: { color: '#f59e0b', fontSize: 15, fontWeight: '600' },
  dangerBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#1a1a3e', padding: 16, borderRadius: 12, borderWidth: 1, borderColor: '#ef444440' },
  dangerText: { color: '#ef4444', fontSize: 15, fontWeight: '600' },
  disabled: { opacity: 0.5 },
});
