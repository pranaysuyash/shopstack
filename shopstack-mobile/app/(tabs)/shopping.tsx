import { useCallback, useState } from 'react';
import {
  View, Text, StyleSheet, FlatList, RefreshControl, ActivityIndicator, Alert,
} from 'react-native';
import { useFocusEffect } from 'expo-router';
import { useQueryClient } from '@tanstack/react-query';
import {
  useActiveShoppingList,
  useCreateShoppingList,
  useCompleteShoppingList,
  useMarkPurchased,
} from '../../src/hooks';
import { ShoppingItemRow, EmptyState, Card, Button, Input } from '../../src/components';
import { semantic, spacing, typography } from '../../src/theme';
import type { ShoppingItemInput } from '../../src/api/types';
import { hapticSuccess } from '../../src/utils/haptics';

export default function ShoppingScreen() {
  const qc = useQueryClient();
  const { data, isLoading, isRefetching, refetch } = useActiveShoppingList();
  const create = useCreateShoppingList();
  const complete = useCompleteShoppingList();
  const markPurchased = useMarkPurchased();
  const [showCreate, setShowCreate] = useState(false);
  const [goal, setGoal] = useState('');
  const [newItems, setNewItems] = useState('');
  // Track which item IDs the user has checked during this shopping trip.
  const [boughtItemIds, setBoughtItemIds] = useState<Set<string>>(new Set());

  useFocusEffect(
    useCallback(() => {
      refetch();
      setBoughtItemIds(new Set());
    }, [refetch])
  );

  const hasActiveList = data && data.list_id && data.list_id.length > 0;
  const items = data?.items ?? [];

  function handleCreate() {
    const parsed: ShoppingItemInput[] = newItems
      .split(',')
      .map((n) => n.trim())
      .filter(Boolean)
      .map((canonical_name) => ({ canonical_name }));

    create.mutate(
      { goal: goal.trim(), items: parsed },
      {
        onSuccess: () => {
          hapticSuccess();
          setShowCreate(false);
          setGoal('');
          setNewItems('');
          setBoughtItemIds(new Set());
        },
      }
    );
  }

  function handleComplete() {
    if (!data?.list_id) return;
    complete.mutate(
      { listId: data.list_id, boughtItemIds: Array.from(boughtItemIds) },
      {
        onSuccess: (result) => {
          hapticSuccess();
          setBoughtItemIds(new Set());
          const added = result.items_added.length;
          const skipped = result.items_skipped;
          Alert.alert(
            'List complete ✓',
            `${added} item${added !== 1 ? 's' : ''} added to pantry.${skipped > 0 ? ` ${skipped} skipped.` : ''}`
          );
        },
      }
    );
  }

  function handleToggleBought(itemId: string, isBought: boolean) {
    hapticSuccess();

    // 1. Optimistic UI
    qc.setQueryData(['shopping', 'active'], (old: unknown) => {
      if (!old || typeof old !== 'object') return old;
      const list = old as Record<string, unknown>;
      const oldItems = (list.items ?? []) as Array<Record<string, unknown>>;
      return {
        ...list,
        items: oldItems.map((it: Record<string, unknown>) =>
          it.item_id === itemId ? { ...it, status: isBought ? 'bought' : 'pending' } : it
        ),
      };
    });

    // 2. Track locally
    setBoughtItemIds((prev) => {
      const next = new Set(prev);
      if (isBought) next.add(itemId);
      else next.delete(itemId);
      return next;
    });

    // 3. Persist to backend when checking (not unchecking)
    if (data?.list_id && isBought) {
      markPurchased.mutate({ listId: data.list_id, itemIds: [itemId] });
    }
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Shop</Text>
        {!showCreate && (
          <Button
            title="New list"
            variant="primary"
            size="sm"
            onPress={() => setShowCreate(true)}
          />
        )}
      </View>

      {showCreate && (
        <Card elevated style={styles.createCard}>
          <Input
            placeholder="Shopping goal (optional)"
            value={goal}
            onChangeText={setGoal}
            style={{ marginBottom: spacing[3] }}
          />
          <Input
            placeholder="milk, eggs, bread, rice"
            value={newItems}
            onChangeText={setNewItems}
            style={{ marginBottom: spacing[3] }}
          />
          <View style={styles.createActions}>
            <Button
              title={create.isPending ? 'Creating...' : 'Create List'}
              loading={create.isPending}
              disabled={!newItems.trim() && !goal.trim()}
              onPress={handleCreate}
              style={{ flex: 1 }}
            />
            <Button
              title="Cancel"
              variant="ghost"
              onPress={() => setShowCreate(false)}
            />
          </View>
        </Card>
      )}

      {isLoading && !data ? (
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={semantic.primary} />
        </View>
      ) : !hasActiveList ? (
        <EmptyState
          motif
          title="No list started."
          message={"Tap \"New list\" and tell us what you need - or just paste a note."}
          action={{ label: 'New list', onPress: () => setShowCreate(true) }}
        />
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => item.item_id}
          renderItem={({ item }) => <ShoppingItemRow item={item} onToggleBought={handleToggleBought} />}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={semantic.primary} />
          }
          contentContainerStyle={styles.list}
          ListHeaderComponent={
            data!.goal ? (
              <Text style={styles.goal}>{data!.goal}</Text>
            ) : null
          }
        />
      )}

      {hasActiveList && (
        <View style={styles.bottomBar}>
          <Button
            title={complete.isPending ? 'Completing...' : `Complete list → Pantry${boughtItemIds.size > 0 ? ` (${boughtItemIds.size})` : ''}`}
            loading={complete.isPending}
            onPress={handleComplete}
            variant="primary"
            size="lg"
          />
        </View>
      )}
    </View>
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
  createCard: {
    marginHorizontal: spacing[4],
    marginBottom: spacing[4],
    padding: spacing[4],
  },
  createActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[3],
  },
  goal: {
    fontSize: typography.sizes.sm.size,
    color: semantic.textSecondary,
    marginHorizontal: spacing[4],
    marginBottom: spacing[2],
  },
  list: { paddingBottom: spacing[4] },
  bottomBar: {
    padding: spacing[4],
    borderTopWidth: 1,
    borderTopColor: semantic.divider,
    backgroundColor: semantic.surface,
  },
});
