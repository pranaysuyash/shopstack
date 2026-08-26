import { View, Text, StyleSheet, Animated } from 'react-native';
import { Card, Badge } from '../primitives';
import { semantic, spacing, typography } from '../../theme';
import { useDecisionBadge } from '../../hooks';
import type { ShoppingListItemWire } from '../../api/types';
import { PanGestureHandler, State } from 'react-native-gesture-handler';

const priorityToAction: Record<string, string> = {
  must_buy: 'buy',
  optional: 'watch',
  avoid_buying: 'skip',
};

interface ShoppingItemRowProps {
  item: ShoppingListItemWire;
  onToggleBought?: (itemId: string, isBought: boolean) => void;
}

export function ShoppingItemRow({ item, onToggleBought }: ShoppingItemRowProps) {
  const badge = useDecisionBadge(priorityToAction[item.priority] || 'watch');
  const isBought = item.status === 'bought';

  const translateX = new Animated.Value(0);
  const completionThreshold = 80;

  const onGestureEvent = Animated.event(
    [{ nativeEvent: { translationX: translateX } }],
    { useNativeDriver: true }
  );

  const onHandlerStateChange = ({ nativeEvent }: { nativeEvent: { state: number; translationX: number } }) => {
    if (nativeEvent.state === State.END) {
      if (nativeEvent.translationX > completionThreshold && !isBought) {
        Animated.timing(translateX, {
          toValue: 120,
          duration: 200,
          useNativeDriver: true,
        }).start(() => {
          onToggleBought?.(item.item_id, true);
        });
      } else if (nativeEvent.translationX < -completionThreshold && isBought) {
        Animated.timing(translateX, {
          toValue: -120,
          duration: 200,
          useNativeDriver: true,
        }).start(() => {
          onToggleBought?.(item.item_id, false);
        });
      } else {
        Animated.spring(translateX, {
          toValue: 0,
          useNativeDriver: true,
        }).start();
      }
    }
  };

  const animatedStyle = {
    transform: [{ translateX }],
  };

  return (
    <PanGestureHandler
      onGestureEvent={onGestureEvent}
      onHandlerStateChange={onHandlerStateChange}
      activeOffsetX={[-10, 10]}
    >
      <Animated.View style={[styles.rowWrapper, animatedStyle]}>
        <Card style={styles.row} padded={false}>
          <View style={styles.inner}>
            <View style={styles.main}>
              <Text style={[styles.name, isBought && styles.bought]}>
                {item.canonical_name}
              </Text>
              <Text style={styles.meta}>
                {item.requested_quantity ? `${item.requested_quantity} ${item.unit || ''}` : ''}
                {item.reason ? ` · ${item.reason}` : ''}
              </Text>
            </View>
            <Badge kind={badge.kind} label={badge.label} />
          </View>
          <View style={styles.swipeHint} pointerEvents="none">
            <Text style={styles.swipeText}>
              {isBought ? 'Swipe left to undo' : 'Swipe right to mark bought'}
            </Text>
          </View>
        </Card>
      </Animated.View>
    </PanGestureHandler>
  );
}

const styles = StyleSheet.create({
  rowWrapper: {
    marginHorizontal: spacing[4],
    marginBottom: spacing[3],
  },
  row: {
    overflow: 'hidden',
  },
  inner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: spacing[4],
  },
  main: {
    flex: 1,
    paddingRight: spacing[3],
  },
  name: {
    fontSize: typography.sizes.base.size,
    fontWeight: typography.weight.semibold,
    color: semantic.textPrimary,
  },
  bought: {
    textDecorationLine: 'line-through',
    color: semantic.textTertiary,
  },
  meta: {
    fontSize: typography.sizes.sm.size,
    color: semantic.textSecondary,
    marginTop: 2,
  },
  swipeHint: {
    position: 'absolute',
    right: spacing[4],
    top: 0,
    bottom: 0,
    justifyContent: 'center',
  },
  swipeText: {
    fontSize: typography.sizes.xs.size,
    color: semantic.textTertiary,
  },
});
