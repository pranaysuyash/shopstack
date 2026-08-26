import { useCallback, useState } from 'react';
import {
  View, Text, StyleSheet, FlatList, RefreshControl, ActivityIndicator,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import { useInventory, useToday, useOnlineStatus } from '../../src/hooks';
import { PantryItemRow, QuickAddBar, EmptyState, Card, Button, Input, StapleChips, Celebration, OfflineBanner, BarcodeScanner } from '../../src/components';
import { semantic, spacing, typography } from '../../src/theme';
import { addLot } from '../../src/api/inventory';
import { lookupBarcode } from '../../src/api/barcode';
import { useCommand } from '../../src/hooks';
import { useQueryClient, useMutation } from '@tanstack/react-query';
import { hapticSuccess, hapticLight } from '../../src/utils/haptics';
import type { BarcodeProduct } from '../../src/api/barcode';

export default function InventoryScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const isOnline = useOnlineStatus();
  const command = useCommand();
  const { data, isLoading, isFetching, isRefetching, refetch } = useInventory(200);
  const [showAdd, setShowAdd] = useState(false);
  const [showScanner, setShowScanner] = useState(false);
  const [celebrate, setCelebrate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newQty, setNewQty] = useState('1');
  const [newUnit, setNewUnit] = useState('unit');

  const addMutation = useMutation({
    mutationFn: () =>
      addLot({
        canonical_name: newName.trim(),
        quantity: parseFloat(newQty) || 1,
        unit: newUnit.trim() || 'unit',
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['inventory'] });
      qc.invalidateQueries({ queryKey: ['today'] });
      setShowAdd(false);
      setNewName('');
      setNewQty('1');
      setNewUnit('unit');
      hapticSuccess();
      if (lots.length === 0) {
        setCelebrate(true);
      }
    },
  });

  useFocusEffect(
    useCallback(() => {
      refetch();
    }, [refetch])
  );

  const lots = data?.items ?? [];

  function handleQuickAdd(text: string) {
    if (!isOnline) {
      // Fallback to local parsing when offline
      const parts = text.trim().split(/\s+/);
      const qty = parseFloat(parts[0]);
      if (!isNaN(qty) && parts.length >= 3) {
        addLot({ canonical_name: parts.slice(2).join(' '), quantity: qty, unit: parts[1] });
      } else {
        addLot({ canonical_name: text, quantity: 1, unit: 'unit' });
      }
      return;
    }
    // Let the backend parse and classify the command
    command.mutate(text, {
      onSuccess: () => {
        hapticSuccess();
        qc.invalidateQueries({ queryKey: ['inventory'] });
        qc.invalidateQueries({ queryKey: ['today'] });
        if (lots.length === 0) {
          setCelebrate(true);
        }
      },
    });
  }

  function handleScan(product: BarcodeProduct) {
    hapticSuccess();
    const qty = product.quantity ? parseFloat(product.quantity) || 1 : 1;
    addLot({
      canonical_name: product.name,
      quantity: qty,
      unit: 'unit',
      nutrition_per_100g: product.nutritionPer100g ?? undefined,
    });
    qc.invalidateQueries({ queryKey: ['inventory'] });
    qc.invalidateQueries({ queryKey: ['today'] });
    if (lots.length === 0) {
      setCelebrate(true);
    }
  }

  function handleStaple(name: string) {
    hapticLight();
    addLot({ canonical_name: name, quantity: 1, unit: 'unit' });
    if (lots.length === 0) {
      setCelebrate(true);
    }
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      style={styles.container}
    >
      <OfflineBanner isOnline={isOnline} isFetching={isFetching} />

      <View style={styles.header}>
        <Text style={styles.title}>Pantry</Text>
        <View style={styles.headerActions}>
          <Button
            title="Scan"
            variant="secondary"
            size="sm"
            onPress={() => setShowScanner(true)}
            style={{ marginRight: spacing[2] }}
          />
          <Button
            title={showAdd ? 'Close' : 'Add'}
            variant={showAdd ? 'secondary' : 'primary'}
            size="sm"
            onPress={() => setShowAdd(!showAdd)}
          />
        </View>
      </View>

      {showAdd && (
        <Card elevated style={styles.addCard}>
          <Input
            placeholder="Item name"
            value={newName}
            onChangeText={setNewName}
            style={{ marginBottom: spacing[3] }}
          />
          <View style={styles.addRow}>
            <Input
              placeholder="Qty"
              value={newQty}
              onChangeText={setNewQty}
              keyboardType="decimal-pad"
              style={[styles.qtyInput, { marginBottom: 0 }]}
            />
            <Input
              placeholder="Unit"
              value={newUnit}
              onChangeText={setNewUnit}
              style={[styles.unitInput, { marginBottom: 0 }]}
            />
          </View>
          <Button
            title={addMutation.isPending ? 'Adding...' : 'Add to Pantry'}
            loading={addMutation.isPending}
            disabled={!newName.trim()}
            onPress={() => addMutation.mutate()}
            style={{ marginTop: spacing[3] }}
          />
        </Card>
      )}

      {isLoading && !data ? (
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={semantic.primary} />
        </View>
      ) : (
        <FlatList
          data={lots}
          keyExtractor={(item) => item.lot_id}
          renderItem={({ item }) => (
            <PantryItemRow
              item={item}
              action={item.label_expiry_date || item.estimated_use_by_date ? 'use_soon' : 'watch'}
            />
          )}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={semantic.primary} />
          }
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <EmptyState
              motif
              title="Nothing in the pantry yet."
              message={ `Tap a staple chip below, or "Add" for something specific. We'll start predicting refill dates after a few entries.` }
              action={{ label: 'Add item', onPress: () => setShowAdd(true) }}
            >
              <StapleChips onSelect={handleStaple} />
            </EmptyState>
          }
        />
      )}

      <BarcodeScanner
        visible={showScanner}
        onScan={handleScan}
        onClose={() => setShowScanner(false)}
      />

      <Celebration
        visible={celebrate}
        message="First item in. The pantry lives."
        submessage="Keep adding — we'll learn your rhythms."
        onDone={() => setCelebrate(false)}
      />

      <QuickAddBar
        placeholder={isOnline ? 'Try: bought 2 kg rice for 120' : 'Quick add: 2 kg rice'}
        onSubmit={handleQuickAdd}
        loading={addMutation.isPending || command.isPending}
      />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: semantic.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing[4],
    paddingTop: 64,
    paddingBottom: spacing[3],
  },
  title: {
    fontSize: typography.sizes['2xl'].size,
    fontWeight: typography.weight.bold,
    color: semantic.textPrimary,
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  addCard: {
    marginHorizontal: spacing[4],
    marginBottom: spacing[4],
    padding: spacing[4],
  },
  addRow: {
    flexDirection: 'row',
    gap: spacing[3],
  },
  qtyInput: { flex: 1 },
  unitInput: { flex: 2 },
  list: { paddingBottom: spacing[4] },
});
