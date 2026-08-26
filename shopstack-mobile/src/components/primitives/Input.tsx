import { TextInput, StyleSheet, type TextInputProps, View } from 'react-native';
import { semantic, radius, spacing, typography } from '../../theme';
import { Icon, type IconName } from './Icon';
import { forwardRef } from 'react';

interface InputProps extends TextInputProps {
  icon?: IconName;
  error?: string;
}

export const Input = forwardRef<TextInput, InputProps>(function Input({ icon, error, style, ...rest }, ref) {
  return (
    <View style={[styles.wrapper, error && styles.wrapperError, style]}>
      {icon && <Icon name={icon} size={18} color={semantic.textTertiary} />}
      <TextInput
        ref={ref}
        placeholderTextColor={semantic.textTertiary}
        style={styles.input}
        {...rest}
      />
    </View>
  );
});

const styles = StyleSheet.create({
  wrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[2],
    backgroundColor: semantic.surface,
    borderWidth: 1,
    borderColor: semantic.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing[3],
    paddingVertical: spacing[3],
    minHeight: 48,
  },
  wrapperError: {
    borderColor: semantic.danger,
  },
  input: {
    flex: 1,
    color: semantic.textPrimary,
    fontSize: typography.sizes.base.size,
    lineHeight: typography.sizes.base.lineHeight,
  },
});
