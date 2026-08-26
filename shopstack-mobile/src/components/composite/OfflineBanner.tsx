import { View, Text, StyleSheet } from 'react-native';
import { Icon } from '../primitives';
import { semantic, spacing, typography } from '../../theme';

interface OfflineBannerProps {
  isOnline: boolean;
  isFetching: boolean;
}

export function OfflineBanner({ isOnline, isFetching }: OfflineBannerProps) {
  if (isOnline && !isFetching) return null;

  return (
    <View style={[styles.banner, isOnline && styles.syncBanner]}>
      <Icon
        name={isOnline ? 'cloud-done-outline' : 'cloud-offline-outline'}
        size={14}
        color={isOnline ? semantic.onPrimary : semantic.onPrimary}
      />
      <Text style={styles.text}>
        {isOnline ? 'Syncing with your household...' : 'Offline — showing cached pantry'}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing[2],
    backgroundColor: semantic.danger,
    paddingHorizontal: spacing[3],
    paddingVertical: spacing[2],
  },
  syncBanner: {
    backgroundColor: semantic.primary,
  },
  text: {
    fontSize: typography.sizes.xs.size,
    fontWeight: typography.weight.medium,
    color: semantic.onPrimary,
  },
});
