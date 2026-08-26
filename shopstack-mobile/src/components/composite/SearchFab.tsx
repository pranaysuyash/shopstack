import { TouchableOpacity, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { Icon } from '../primitives';
import { semantic, shadow, radius, spacing } from '../../theme';

export function SearchFab() {
  const router = useRouter();

  return (
    <TouchableOpacity
      style={styles.fab}
      activeOpacity={0.85}
      onPress={() => router.push('/search')}
      accessibilityLabel="Search"
    >
      <Icon name="search" size={24} color={semantic.onPrimary} />
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  fab: {
    position: 'absolute',
    right: spacing[4],
    bottom: spacing[4] + 84, // above tab bar
    width: 56,
    height: 56,
    borderRadius: radius.full,
    backgroundColor: semantic.primary,
    justifyContent: 'center',
    alignItems: 'center',
    ...shadow.lg,
  },
});
