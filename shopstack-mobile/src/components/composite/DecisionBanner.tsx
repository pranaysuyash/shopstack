import { View, Text, StyleSheet } from 'react-native';
import { Card, Badge } from '../primitives';
import { semantic, spacing, typography } from '../../theme';
import { useDecisionBadge } from '../../hooks';

interface DecisionBannerProps {
  action: string;
  title: string;
  reason: string;
  onPress?: () => void;
}

export function DecisionBanner({ action, title, reason, onPress }: DecisionBannerProps) {
  const badge = useDecisionBadge(action);

  return (
    <Card onTouchEnd={onPress} style={styles.banner} elevated={!!onPress} padded={false}>
      <View style={styles.inner}>
        <View style={styles.lead}>
          <Badge kind={badge.kind} label={badge.label} size="lg" />
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.reason}>{reason}</Text>
        </View>
        {onPress && <Badge kind="confirm" label="Tap to act" icon="arrow-forward-outline" />}
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  banner: {
    marginHorizontal: spacing[4],
    marginBottom: spacing[4],
    overflow: 'hidden',
  },
  inner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: spacing[5],
  },
  lead: {
    flex: 1,
    gap: spacing[2],
  },
  title: {
    fontSize: typography.sizes.xl.size,
    fontWeight: typography.weight.bold,
    color: semantic.textPrimary,
  },
  reason: {
    fontSize: typography.sizes.sm.size,
    color: semantic.textSecondary,
    lineHeight: typography.sizes.sm.lineHeight,
  },
});
