import { useEffect, useRef } from 'react';
import { View, Animated, StyleSheet, Text } from 'react-native';
import { semantic, spacing, typography } from '../../theme';
import { PantryMotif } from './PantryMotif';

interface CelebrationProps {
  visible: boolean;
  message: string;
  submessage?: string;
  onDone?: () => void;
}

export function Celebration({ visible, message, submessage, onDone }: CelebrationProps) {
  const scale = useRef(new Animated.Value(0)).current;
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!visible) return;
    scale.setValue(0);
    opacity.setValue(0);

    Animated.sequence([
      Animated.parallel([
        Animated.spring(scale, { toValue: 1, useNativeDriver: true, friction: 6 }),
        Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: true }),
      ]),
      Animated.delay(1600),
      Animated.timing(opacity, { toValue: 0, duration: 400, useNativeDriver: true }),
    ]).start(() => onDone?.());
  }, [visible]);

  if (!visible) return null;

  return (
    <View style={styles.overlay} pointerEvents="none">
      <Animated.View style={[styles.bubble, { transform: [{ scale }], opacity }]}>
        <View style={styles.motif}>
          <PantryMotif size={80} />
        </View>
        <Text style={styles.message}>{message}</Text>
        {submessage && <Text style={styles.submessage}>{submessage}</Text>}
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 50,
  },
  bubble: {
    backgroundColor: semantic.primary,
    borderRadius: 24,
    padding: spacing[6],
    alignItems: 'center',
    shadowColor: semantic.shadow,
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.25,
    shadowRadius: 16,
    elevation: 10,
  },
  iconCircle: {
    width: 72,
    height: 72,
    borderRadius: 999,
    backgroundColor: 'rgba(255,255,255,0.2)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: spacing[3],
  },
  motif: {
    marginBottom: spacing[3],
  },
  message: {
    fontSize: typography.sizes.xl.size,
    fontWeight: typography.weight.bold,
    color: semantic.onPrimary,
  },
  submessage: {
    fontSize: typography.sizes.sm.size,
    color: semantic.onPrimary,
    opacity: 0.9,
    marginTop: spacing[1],
  },
});
