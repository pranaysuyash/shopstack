import { View, Text, StyleSheet } from 'react-native';
import { semantic, spacing, typography } from '../../theme';
import { Icon, type IconName } from './Icon';
import { Button } from './Button';
import { PantryMotif } from '../composite/PantryMotif';

interface EmptyStateProps {
  icon?: IconName;
  motif?: boolean;
  title: string;
  message: string;
  action?: { label: string; onPress: () => void };
  color?: string;
  children?: React.ReactNode;
}

export function EmptyState({ icon, motif, title, message, action, color = semantic.textTertiary, children }: EmptyStateProps) {
  return (
    <View style={styles.container}>
      {motif ? (
        <PantryMotif size={144} />
      ) : (
        <View style={styles.iconCircle}>
          <Icon name={icon ?? 'basket-outline'} size={32} color={color} />
        </View>
      )}
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.message}>{message}</Text>
      {children}
      {action && <Button title={action.label} variant="primary" onPress={action.onPress} style={styles.action} />}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    paddingHorizontal: spacing[6],
    paddingVertical: spacing[12],
    gap: spacing[3],
  },
  iconCircle: {
    width: 72,
    height: 72,
    borderRadius: 999,
    backgroundColor: semantic.surfaceElevated,
    borderWidth: 1,
    borderColor: semantic.border,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: spacing[2],
  },
  title: {
    fontSize: typography.sizes.xl.size,
    fontWeight: typography.weight.bold,
    color: semantic.textPrimary,
    textAlign: 'center',
  },
  message: {
    fontSize: typography.sizes.base.size,
    color: semantic.textSecondary,
    textAlign: 'center',
    lineHeight: typography.sizes.base.lineHeight,
  },
  action: {
    marginTop: spacing[3],
    minWidth: 200,
  },
});
