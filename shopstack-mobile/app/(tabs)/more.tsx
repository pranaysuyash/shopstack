import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Alert } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { deleteToken, clearAll } from '../../src/storage/token';
import { setCachedToken } from '../../src/api/client';

interface SettingsItemProps {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  description: string;
  onPress: () => void;
  color?: string;
}

function SettingsItem({ icon, label, description, onPress, color = '#818cf8' }: SettingsItemProps) {
  return (
    <TouchableOpacity style={styles.item} onPress={onPress}>
      <View style={[styles.iconWrap, { backgroundColor: color + '20' }]}>
        <Ionicons name={icon} size={22} color={color} />
      </View>
      <View style={styles.itemInfo}>
        <Text style={styles.itemLabel}>{label}</Text>
        <Text style={styles.itemDesc}>{description}</Text>
      </View>
      <Ionicons name="chevron-forward" size={18} color="#555" />
    </TouchableOpacity>
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
      <Text style={styles.header}>More</Text>
      <Text style={styles.subheader}>Settings & tools</Text>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Intelligence</Text>
        <SettingsItem
          icon="trending-up-outline"
          label="Recurring Plan"
          description="Items due in your shopping rhythm"
          onPress={() => router.push('/intelligence')}
          color="#22c55e"
        />
        <SettingsItem
          icon="restaurant-outline"
          label="Meal Plan"
          description="Weekly meal suggestions from your pantry"
          onPress={() => router.push('/intelligence')}
          color="#22c55e"
        />
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Account & Privacy</Text>
        <SettingsItem
          icon="shield-checkmark-outline"
          label="Privacy"
          description="Retention settings, purge data"
          onPress={() => router.push('/account')}
          color="#f59e0b"
        />
        <SettingsItem
          icon="arrow-undo-outline"
          label="Undo"
          description="Reverse the last action"
          onPress={() => router.push('/account')}
          color="#f59e0b"
        />
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Activity</Text>
        <SettingsItem
          icon="code-slash-outline"
          label="Command History"
          description="Recently executed commands"
          onPress={() => router.push('/traces')}
          color="#6366f1"
        />
        <SettingsItem
          icon="git-network-outline"
          label="Corrections"
          description="Review and create corrections"
          onPress={() => router.push('/corrections')}
          color="#6366f1"
        />
        <SettingsItem
          icon="bug-outline"
          label="Store Mode"
          description="Check off items while shopping"
          onPress={() => router.push('/store-mode')}
          color="#6366f1"
        />
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Info</Text>
        <SettingsItem
          icon="information-circle-outline"
          label="Server Info"
          description="Runtime mode, app version"
          onPress={() => router.push('/account')}
          color="#8888bb"
        />
      </View>

      <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
        <Ionicons name="log-out-outline" size={20} color="#ef4444" />
        <Text style={styles.logoutText}>Log Out</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f23' },
  content: { padding: 16, paddingTop: 60, paddingBottom: 40 },
  header: { fontSize: 28, fontWeight: '700', color: '#e0e0ff' },
  subheader: { fontSize: 14, color: '#8888bb', marginBottom: 24 },
  section: { marginBottom: 24 },
  sectionTitle: { fontSize: 13, fontWeight: '600', color: '#666', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 },
  item: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: '#1a1a3e',
    borderRadius: 12, padding: 14, marginBottom: 6, borderWidth: 1, borderColor: '#2a2a5e',
  },
  iconWrap: { width: 40, height: 40, borderRadius: 10, justifyContent: 'center', alignItems: 'center', marginRight: 12 },
  itemInfo: { flex: 1 },
  itemLabel: { fontSize: 15, fontWeight: '600', color: '#e0e0ff' },
  itemDesc: { fontSize: 12, color: '#8888bb', marginTop: 2 },
  logoutBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, padding: 16, marginTop: 16, borderWidth: 1, borderColor: '#ef444440', borderRadius: 12 },
  logoutText: { color: '#ef4444', fontSize: 15, fontWeight: '600' },
});
