import { useState } from 'react';
import { View, Text, StyleSheet, Alert, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import {
  setToken, setDeviceId, setDeviceSecret, generateDeviceId, generateDeviceSecret,
  setActiveHouseholdId, setApiBaseUrl,
} from '../../src/storage/token';
import { registerDevice } from '../../src/api/auth';
import { setCachedBaseUrl } from '../../src/api/client';
import { Button, Input, Card } from '../../src/components';
import { semantic, spacing, typography } from '../../src/theme';

export default function RegisterScreen() {
  const router = useRouter();
  const [apiUrl, setApiUrl] = useState('http://localhost:7860');
  const [householdName, setHouseholdName] = useState('My Home');
  const [loading, setLoading] = useState(false);

  async function handleRegister() {
    if (!householdName.trim()) {
      Alert.alert('Required', 'Enter a name for your household.');
      return;
    }
    setLoading(true);
    try {
      // Update both the persisted storage and the in-memory cache
      await setApiBaseUrl(apiUrl);
      setCachedBaseUrl(apiUrl);

      const deviceId = generateDeviceId();
      const deviceSecret = generateDeviceSecret();

      const result = await registerDevice({
        device_id: deviceId,
        device_secret: deviceSecret,
        household_name: householdName.trim(),
      });

      await setToken(result.token);
      await setDeviceId(deviceId);
      await setDeviceSecret(deviceSecret);
      await setActiveHouseholdId(result.household_id);

      router.replace('/');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      Alert.alert('Registration Failed', msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <View style={styles.container}>
      <Card style={styles.card}>
        <Text style={styles.title}>New Household</Text>
        <Text style={styles.subtitle}>Set up ShopStack on this device</Text>

        <Input
          placeholder="http://localhost:7860"
          value={apiUrl}
          onChangeText={setApiUrl}
          autoCapitalize="none"
          autoCorrect={false}
          style={{ marginBottom: spacing[4] }}
        />

        <Input
          placeholder="My Home"
          value={householdName}
          onChangeText={setHouseholdName}
          style={{ marginBottom: spacing[6] }}
        />

        <Button
          title={loading ? 'Registering...' : 'Register &amp; Connect'}
          loading={loading}
          disabled={!householdName.trim()}
          onPress={handleRegister}
          size="lg"
          style={{ marginBottom: spacing[4] }}
        />

        <Button
          title="Already registered? Log in"
          variant="ghost"
          onPress={() => router.push('/(auth)/login')}
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
  },
  title: {
    fontSize: typography.sizes['2xl'].size,
    fontWeight: typography.weight.bold,
    color: semantic.textPrimary,
    textAlign: 'center',
    marginBottom: spacing[1],
  },
  subtitle: {
    fontSize: typography.sizes.base.size,
    color: semantic.textSecondary,
    textAlign: 'center',
    marginBottom: spacing[6],
  },
});
