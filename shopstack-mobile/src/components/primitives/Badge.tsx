import { View, Text, StyleSheet, type ViewProps } from 'react-native';
import { Icon } from './Icon';
import { decision, radius, spacing, typography } from '../../theme';
import { type IconName } from './Icon';

type DecisionKind = keyof typeof decision;

interface BadgeProps extends ViewProps {
  kind?: DecisionKind;
  label: string;
  icon?: IconName;
  color?: { fg: string; bg: string };
  size?: 'sm' | 'md' | 'lg';
}

export function Badge({ kind, label, icon, color, size = 'sm', style, ...rest }: BadgeProps) {
  const token = kind ? decision[kind] : color;
  if (!token) return null;

  const iconName = (kind ? decision[kind].icon : icon) as IconName | undefined;
  const isLarge = size === 'lg';

  return (
    <View
      style={[
        styles.badge,
        { backgroundColor: token.bg },
        isLarge && styles.badgeLarge,
        style,
      ]}
      {...rest}
    >
      {iconName && <Icon name={iconName} size={isLarge ? 16 : 12} color={token.fg} />}
      <Text style={[styles.text, { color: token.fg }, isLarge && styles.textLarge]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: spacing[1],
    paddingHorizontal: spacing[2] + spacing[1],
    paddingVertical: spacing[1],
    borderRadius: radius.full,
  },
  badgeLarge: {
    paddingHorizontal: spacing[3],
    paddingVertical: spacing[2],
    gap: spacing[2],
  },
  text: {
    fontSize: typography.sizes.xs.size,
    fontWeight: typography.weight.semibold,
    letterSpacing: 0.01,
  },
  textLarge: {
    fontSize: typography.sizes.sm.size,
  },
});
