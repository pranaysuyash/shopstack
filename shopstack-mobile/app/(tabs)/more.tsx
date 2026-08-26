import { View, Text, StyleSheet, ScrollView, Alert } from 'react-native';
import { useRouter } from 'expo-router';
import { Card, Button, Icon, type IconName } from '../../src/components';
import { semantic, spacing, typography } from '../../src/theme';
import { clearAll } from '../../src/storage/token';
import { setCachedToken } from '../../src/api/client';

interface MenuItemProps {
  icon: IconName;
  label: string;
  description: string;
  onPress: () => void;
  color?: string;
}

function MenuItem({ icon, label, description, onPress, color = semantic.primary }: MenuItemProps) {
  return (
    <Card onTouchEnd={onPress} style={styles.item} padded={false}>
      <View style={styles.itemInner}>
        <View style={[styles.iconCircle, { backgroundColor: color + '15' }]}>
          <Icon name={icon} size={20} color={color} />
        </View>
        <View style={styles.itemText}>
          <Text style={styles.itemLabel}>{label}</Text>
          <Text style={styles.itemDesc}>{description}</Text>
        </View>
        <Icon name="chevron-forward" size={18} color={semantic.textTertiary} />
      </View>
    </Card>
  );
}

export default function MoreScreen() {
  const router = useRouter();

  function handleLogout() {
    Alert.alert('Log Out', 'Clear your session and log out?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Log Out',
        style: 'destructive',
        onPress: async () => {
          setCachedToken(null);
          await clearAll();
          router.replace('/');
        },
      },
    ]);
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.title}>More</Text>
      <Text style={styles.subtitle}>Settings, tools, and history</Text>

      <Text style={styles.sectionTitle}>Intelligence</Text>
      <MenuItem
        icon="trending-up-outline"
        label="Recurring Plan"
        description="Items due in your shopping rhythm"
        onPress={() => router.push('/intelligence')}
        color={semantic.success}
      />
      <MenuItem
        icon="restaurant-outline"
        label="Meal Plan"
        description="Weekly meal suggestions from your pantry"
        onPress={() => router.push('/intelligence')}
        color={semantic.success}
      />

      <Text style={styles.sectionTitle}>Account &amp; Privacy</Text>
      <MenuItem
        icon="shield-checkmark-outline"
        label="Privacy"
        description="Retention settings and purge data"
        onPress={() => router.push('/account')}
        color={semantic.warning}
      />
      <MenuItem
        icon="arrow-undo-outline"
        label="Undo"
        description="Reverse the last action"
        onPress={() => router.push('/account')}
        color={semantic.warning}
      />

      <Text style={styles.sectionTitle}>Data</Text>
      <MenuItem
        icon="cloud-download-outline"
        label="Backup & Restore"
        description="Export or import your inventory data"
        onPress={() => router.push('/backup')}
        color={semantic.info}
      />

      <Text style={styles.sectionTitle}>Activity</Text>
      <MenuItem
        icon="code-slash-outline"
        label="Command History"
        description="Recently executed commands"
        onPress={() => router.push('/traces')}
        color={semantic.info}
      />
      <MenuItem
        icon="git-network-outline"
        label="Corrections"
        description="Review and create corrections"
        onPress={() => router.push('/corrections')}
        color={semantic.info}
      />
      <MenuItem
        icon="basket-outline"
        label="Store Mode"
        description="Check off items while shopping"
        onPress={() => router.push('/store-mode')}
        color={semantic.info}
      />

      <Button
        title="Log Out"
        variant="danger"
        onPress={handleLogout}
        style={{ marginTop: spacing[6] }}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: semantic.background },
  content: { paddingTop: 64, paddingHorizontal: spacing[4], paddingBottom: 40 },
  title: {
    fontSize: typography.sizes['2xl'].size,
    fontWeight: typography.weight.bold,
    color: semantic.textPrimary,
    marginBottom: spacing[1],
  },
  subtitle: {
    fontSize: typography.sizes.base.size,
    color: semantic.textSecondary,
    marginBottom: spacing[5],
  },
  sectionTitle: {
    fontSize: typography.sizes.xs.size,
    fontWeight: typography.weight.semibold,
    color: semantic.textTertiary,
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginTop: spacing[5],
    marginBottom: spacing[3],
  },
  item: {
    marginBottom: spacing[3],
    overflow: 'hidden',
  },
  itemInner: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing[4],
    gap: spacing[3],
  },
  iconCircle: {
    width: 40,
    height: 40,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
  },
  itemText: {
    flex: 1,
  },
  itemLabel: {
    fontSize: typography.sizes.base.size,
    fontWeight: typography.weight.semibold,
    color: semantic.textPrimary,
  },
  itemDesc: {
    fontSize: typography.sizes.sm.size,
    color: semantic.textSecondary,
    marginTop: 2,
  },
});
