import { View, Text, StyleSheet } from 'react-native';
import { Card, Badge } from '../primitives';
import { semantic, spacing, typography } from '../../theme';
import { useDecisionBadge } from '../../hooks';
import type { InventoryLot } from '../../api/types';

interface PantryItemRowProps {
  item: InventoryLot;
  action?: string;
}

export function PantryItemRow({ item, action }: PantryItemRowProps) {
  const badge = useDecisionBadge(action || 'watch');
  const isExpiringSoon = !!item.label_expiry_date || !!item.estimated_use_by_date;

  return (
    <Card style={styles.row} padded={false}>
      <View style={styles.inner}>
        <View style={styles.main}>
          <Text style={styles.name}>{item.display_name || item.canonical_name}</Text>
          <Text style={styles.meta}>
            {item.quantity} {item.unit}
            {item.storage_location_name ? ` · ${item.storage_location_name}` : ''}
          </Text>
        </View>
        <View style={styles.badges}>
          {isExpiringSoon && <Badge kind="useSoon" label="Use soon" />}
          <Badge kind={badge.kind} label={badge.label} />
        </View>
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  row: {
    marginHorizontal: spacing[4],
    marginBottom: spacing[3],
    overflow: 'hidden',
  },
  inner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: spacing[4],
  },
  main: {
    flex: 1,
    paddingRight: spacing[3],
  },
  name: {
    fontSize: typography.sizes.base.size,
    fontWeight: typography.weight.semibold,
    color: semantic.textPrimary,
  },
  meta: {
    fontSize: typography.sizes.sm.size,
    color: semantic.textSecondary,
    marginTop: 2,
  },
  badges: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[2],
  },
});
