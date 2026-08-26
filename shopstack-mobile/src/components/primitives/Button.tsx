import {
  TouchableOpacity,
  Text,
  StyleSheet,
  ActivityIndicator,
  type TouchableOpacityProps,
} from 'react-native';
import { semantic, radius, spacing, typography } from '../../theme';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

interface ButtonProps extends TouchableOpacityProps {
  title: string;
  variant?: ButtonVariant;
  loading?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

const variantStyles: Record<ButtonVariant, { bg: string; fg: string; border: string }> = {
  primary: { bg: semantic.primary, fg: semantic.onPrimary, border: semantic.primary },
  secondary: { bg: semantic.surfaceElevated, fg: semantic.textPrimary, border: semantic.border },
  ghost: { bg: 'transparent', fg: semantic.primary, border: 'transparent' },
  danger: { bg: semantic.danger, fg: semantic.textInverse, border: semantic.danger },
};

const sizeStyles = {
  sm: { padding: spacing[2] + spacing[1], fontSize: typography.sizes.sm.size },
  md: { padding: spacing[3], fontSize: typography.sizes.base.size },
  lg: { padding: spacing[4], fontSize: typography.sizes.lg.size },
};

export function Button({
  title,
  variant = 'primary',
  loading = false,
  size = 'md',
  disabled,
  style,
  ...rest
}: ButtonProps) {
  const v = variantStyles[variant];
  const s = sizeStyles[size];

  return (
    <TouchableOpacity
      activeOpacity={0.85}
      disabled={disabled || loading}
      style={[
        styles.button,
        { backgroundColor: v.bg, borderColor: v.border, padding: s.padding },
        (disabled || loading) && styles.disabled,
        style,
      ]}
      {...rest}
    >
      {loading ? (
        <ActivityIndicator size="small" color={v.fg} />
      ) : (
        <Text style={[styles.text, { color: v.fg, fontSize: s.fontSize }]}>{title}</Text>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  button: {
    borderRadius: radius.md,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 44,
  },
  disabled: {
    opacity: 0.5,
  },
  text: {
    fontWeight: typography.weight.semibold,
  },
});
