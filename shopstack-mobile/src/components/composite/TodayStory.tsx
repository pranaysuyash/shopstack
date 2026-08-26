import { View, Text, StyleSheet } from 'react-native';
import { Card, Badge, Button } from '../primitives';
import { semantic, spacing, typography } from '../../theme';
import { useDecisionBadge } from '../../hooks';

interface StoryItem {
  canonical_name: string;
  display_name?: string;
  action: string;
  reason: string;
  confidence?: number;
}

interface TodayStoryProps {
  headline: string;
  kicker: string;
  items: StoryItem[];
  onAction?: (item: StoryItem) => void;
}

export function TodayStory({ headline, kicker, items, onAction }: TodayStoryProps) {
  return (
    <Card elevated style={styles.story}>
      <Text style={styles.kicker}>{kicker}</Text>
      <Text style={styles.headline}>{headline}</Text>

      {items.slice(0, 4).map((item, i) => {
        const badge = useDecisionBadge(item.action, item.confidence);
        return (
          <View key={`${item.canonical_name}-${i}`} style={styles.row}>
            <View style={styles.rowText}>
              <Text style={styles.itemName}>{item.display_name || item.canonical_name}</Text>
              <Text style={styles.itemReason}>{item.reason}</Text>
            </View>
            <View style={styles.rowActions}>
              <Badge kind={badge.kind} label={badge.label} />
              {onAction && (
                <Button
                  title="Act"
                  variant="primary"
                  size="sm"
                  onPress={() => onAction(item)}
                  style={styles.actBtn}
                />
              )}
            </View>
          </View>
        );
      })}
    </Card>
  );
}

const styles = StyleSheet.create({
  story: {
    marginHorizontal: spacing[4],
    marginTop: spacing[4],
    padding: spacing[5],
  },
  kicker: {
    fontSize: typography.sizes.xs.size,
    fontWeight: typography.weight.semibold,
    color: semantic.primary,
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: spacing[1],
  },
  headline: {
    fontSize: typography.sizes['2xl'].size,
    fontWeight: typography.weight.bold,
    color: semantic.textPrimary,
    lineHeight: typography.sizes['2xl'].lineHeight,
    marginBottom: spacing[4],
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing[3],
    borderBottomWidth: 1,
    borderBottomColor: semantic.divider,
  },
  rowText: {
    flex: 1,
    paddingRight: spacing[3],
  },
  itemName: {
    fontSize: typography.sizes.base.size,
    fontWeight: typography.weight.semibold,
    color: semantic.textPrimary,
  },
  itemReason: {
    fontSize: typography.sizes.sm.size,
    color: semantic.textSecondary,
    marginTop: 2,
  },
  rowActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[2],
  },
  actBtn: {
    paddingHorizontal: spacing[3],
    paddingVertical: spacing[2],
  },
});
