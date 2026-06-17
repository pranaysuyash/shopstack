import { useState, useEffect } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, Alert, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { setToken, getDeviceId, getDeviceSecret, generateDeviceId, generateDeviceSecret, setActiveHouseholdId, setDeviceId, setDeviceSecret } from '../../src/storage/token';
import { loginDevice } from '../../src/api/auth';

export default function LoginScreen() {
  const router = useRouter();
  const [apiUrl, setApiUrl] = useState('http://localhost:7860');
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(true);

  // On mount, check if stored device credentials exist.
  // If they do, try logging in automatically. If not, redirect to register.
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
          await setToken(result.token);
          await setActiveHouseholdId(result.household_id);
          router.replace('/');
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

      await setToken(result.token);
      await setDeviceId(deviceId);
      await setDeviceSecret(deviceSecret);
      await setActiveHouseholdId(result.household_id);

      // Force reload to trigger auth gate
      router.replace('/');
    } catch (err: unknown) {
      // Not registered yet — navigate to register
      const msg = err instanceof Error ? err.message : 'Unknown error';
      if (msg.includes('unknown_device') || msg.includes('401')) {
        router.push('/(auth)/register');
      } else {
        Alert.alert('Connection Error', `Could not reach the server at ${apiUrl}.\n${msg}`);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <View style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.title}>ShopStack</Text>
        <Text style={styles.subtitle}>Know what is at home</Text>

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

        <TouchableOpacity
          style={[styles.button, loading && styles.buttonDisabled]}
          onPress={handleNewDeviceLogin}
          disabled={loading}
        >
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.buttonText}>Register New Device & Login</Text>
          )}
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.linkButton}
          onPress={() => router.push('/(auth)/register')}
        >
          <Text style={styles.linkText}>Set up a new household</Text>
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
    fontSize: 32,
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
