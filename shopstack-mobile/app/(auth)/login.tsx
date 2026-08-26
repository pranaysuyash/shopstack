import { useState, useEffect } from 'react';
import { View, Text, StyleSheet, Alert, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import {
  getDeviceId, getDeviceSecret, generateDeviceId, generateDeviceSecret,
  setActiveHouseholdId, setDeviceId, setDeviceSecret,
} from '../../src/storage/token';
import { useAuth } from '../../src/storage/AuthContext';
import { loginDevice } from '../../src/api/auth';
import { Button, Card } from '../../src/components';
import { semantic, spacing, typography } from '../../src/theme';

export default function LoginScreen() {
  const router = useRouter();
  // signIn() stores the token AND reactively flips isAuthenticated in RootLayout
  // so router.replace('/') is no longer needed to swap the navigator stack.
  const { signIn } = useAuth();
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(true);

  // Auto-login if valid stored credentials exist
  useEffect(() => {
    (async () => {
      const existingDeviceId = await getDeviceId();
      const existingSecret = await getDeviceSecret();
      if (existingDeviceId && existingSecret) {
        setLoading(true);
        try {
          const result = await loginDevice({
            device_id: existingDeviceId,
            device_secret: existingSecret,
          });
          await setActiveHouseholdId(result.household_id);
          // signIn persists token + notifies AuthContext → RootLayout re-renders to (tabs)
          await signIn(result.token);
          return;
        } catch {
          // Stored credentials no longer valid — show login form
          setLoading(false);
        }
      }
      setChecking(false);
    })();
  }, []);

  async function handleNewDeviceLogin() {
    setLoading(true);
    try {
      const deviceId = generateDeviceId();
      const deviceSecret = generateDeviceSecret();

      await setDeviceId(deviceId);
      await setDeviceSecret(deviceSecret);

      const result = await loginDevice({
        device_id: deviceId,
        device_secret: deviceSecret,
      });

      await setActiveHouseholdId(result.household_id);
      await signIn(result.token);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      if (msg.includes('unknown_device') || msg.includes('401')) {
        router.push('/(auth)/register');
      } else {
        Alert.alert('Connection Error', `Could not reach the server.\n${msg}`);
      }
    } finally {
      setLoading(false);
    }
  }

  if (checking) {
    return (
      <View style={styles.container}>
        <ActivityIndicator size="large" color={semantic.primary} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <Card style={styles.card}>
        <Text style={styles.title}>ShopStack</Text>
        <Text style={styles.subtitle}>Your home, understood.</Text>

        <Button
          title={loading ? 'Connecting...' : 'Connect this device'}
          loading={loading}
          onPress={handleNewDeviceLogin}
          size="lg"
          style={{ marginBottom: spacing[4] }}
        />

        <Button
          title="Create a household"
          variant="ghost"
          onPress={() => router.push('/(auth)/register')}
        />
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: semantic.background,
    padding: spacing[6],
  },
  card: {
    width: '100%',
    maxWidth: 400,
    padding: spacing[8],
    alignItems: 'center',
  },
  title: {
    fontSize: typography.sizes['3xl'].size,
    fontWeight: typography.weight.bold,
    color: semantic.textPrimary,
    textAlign: 'center',
    marginBottom: spacing[1],
  },
  subtitle: {
    fontSize: typography.sizes.base.size,
    color: semantic.textSecondary,
    textAlign: 'center',
    marginBottom: spacing[8],
  },
});
