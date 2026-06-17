import { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, Alert, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { setToken, setDeviceId, setDeviceSecret, generateDeviceId, generateDeviceSecret, setActiveHouseholdId, setApiBaseUrl } from '../../src/storage/token';
import { registerDevice } from '../../src/api/auth';
import { setCachedBaseUrl } from '../../src/api/client';

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
      <View style={styles.card}>
        <Text style={styles.title}>New Household</Text>
        <Text style={styles.subtitle}>Set up ShopStack on this device</Text>

        <Text style={styles.label}>Server URL</Text>
        <TextInput
          style={styles.input}
          value={apiUrl}
          onChangeText={setApiUrl}
          placeholder="http://localhost:7860"
          placeholderTextColor="#666"
          autoCapitalize="none"
          autoCorrect={false}
        />

        <Text style={styles.label}>Household Name</Text>
        <TextInput
          style={styles.input}
          value={householdName}
          onChangeText={setHouseholdName}
          placeholder="My Home"
          placeholderTextColor="#666"
        />

        <TouchableOpacity
          style={[styles.button, loading && styles.buttonDisabled]}
          onPress={handleRegister}
          disabled={loading}
        >
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.buttonText}>Register & Connect</Text>
          )}
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.linkButton}
          onPress={() => router.push('/(auth)/login')}
        >
          <Text style={styles.linkText}>Already registered? Log in</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#0f0f23',
    padding: 24,
  },
  card: {
    width: '100%',
    maxWidth: 400,
    backgroundColor: '#1a1a3e',
    borderRadius: 16,
    padding: 32,
    borderWidth: 1,
    borderColor: '#2a2a5e',
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: '#e0e0ff',
    textAlign: 'center',
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 14,
    color: '#8888bb',
    textAlign: 'center',
    marginBottom: 32,
  },
  label: {
    fontSize: 13,
    color: '#aaaacc',
    marginBottom: 8,
    fontWeight: '600',
  },
  input: {
    backgroundColor: '#0f0f23',
    borderWidth: 1,
    borderColor: '#2a2a5e',
    borderRadius: 10,
    padding: 14,
    fontSize: 16,
    color: '#e0e0ff',
    marginBottom: 20,
  },
  button: {
    backgroundColor: '#6366f1',
    borderRadius: 10,
    padding: 16,
    alignItems: 'center',
    marginBottom: 16,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  linkButton: {
    alignItems: 'center',
  },
  linkText: {
    color: '#818cf8',
    fontSize: 14,
  },
});
