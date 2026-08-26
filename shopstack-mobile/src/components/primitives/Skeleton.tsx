import { View, StyleSheet, type ViewProps } from 'react-native';
import { semantic, radius } from '../../theme';

interface SkeletonProps extends ViewProps {
  width?: number;
  height?: number;
  circle?: boolean;
}

export function Skeleton({ width, height = 16, circle = false, style, ...rest }: SkeletonProps) {
  return (
    <View
      style={[
        styles.skeleton,
        {
          width,
          height,
          borderRadius: circle ? height / 2 : radius.sm,
        },
        style,
      ]}
      {...rest}
    />
  );
}

const styles = StyleSheet.create({
  skeleton: {
    backgroundColor: semantic.surfaceElevated,
    overflow: 'hidden',
  },
});
