import { useRef } from 'react';
import { View, TouchableOpacity, Text, StyleSheet, Animated, type TouchableOpacityProps } from 'react-native';
import { Icon, type IconName } from '../primitives';
import { semantic, radius, spacing, typography } from '../../theme';

interface ActionTileProps extends TouchableOpacityProps {
  icon: IconName;
  title: string;
  subtitle: string;
  color: string;
  dominant?: boolean;
}

export function ActionTile({ icon, title, subtitle, color, dominant, style, ...rest }: ActionTileProps) {
  const scale = useRef(new Animated.Value(1)).current;

  function handlePressIn() {
    Animated.spring(scale, { toValue: 0.95, useNativeDriver: true }).start();
  }

  function handlePressOut() {
    Animated.spring(scale, { toValue: 1, useNativeDriver: true, friction: 5 }).start();
  }

  return (
    <Animated.View style={[{ transform: [{ scale }] }, dominant ? styles.dominantWrapper : styles.wrapper]}>
      <TouchableOpacity
        activeOpacity={0.85}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        style={[styles.tile, { borderColor: color + '40', backgroundColor: semantic.surface }, dominant && styles.dominantTile, style]}
        {...rest}
      >
        <View style={[styles.iconCircle, { backgroundColor: color + '15' }]}>
          <Icon name={icon} size={dominant ? 28 : 22} color={color} />
        </View>
        <Text style={[styles.title, dominant && styles.dominantTitle]}>{title}</Text>
        <Text style={styles.subtitle}>{subtitle}</Text>
      </TouchableOpacity>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    flex: 1,
    minWidth: '45%',
  },
  dominantWrapper: {
    width: '100%',
    marginBottom: spacing[2],
  },
  tile: {
    borderRadius: radius.lg,
    borderWidth: 1,
    padding: spacing[4],
    gap: spacing[2],
  },
  dominantTile: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing[5],
    paddingHorizontal: spacing[5],
    gap: spacing[4],
  },
  iconCircle: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: spacing[1],
  },
  title: {
    fontSize: typography.sizes.lg.size,
    fontWeight: typography.weight.bold,
    color: semantic.textPrimary,
  },
  dominantTitle: {
    fontSize: typography.sizes.xl.size,
  },
  subtitle: {
    fontSize: typography.sizes.sm.size,
    color: semantic.textSecondary,
  },
});
