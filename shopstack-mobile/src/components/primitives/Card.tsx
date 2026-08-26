import { View, StyleSheet, type ViewProps } from 'react-native';
import { semantic, radius, shadow, spacing } from '../../theme';

interface CardProps extends ViewProps {
  elevated?: boolean;
  padded?: boolean;
}

export function Card({ children, elevated = false, padded = true, style, ...rest }: CardProps) {
  return (
    <View
      style={[
        styles.card,
        elevated && shadow.md,
        padded && { padding: spacing[4] },
        style,
      ]}
      {...rest}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: semantic.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: semantic.border,
  },
});
