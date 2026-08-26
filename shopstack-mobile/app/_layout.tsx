/**
 * Root layout — wires QueryClient persistence and AuthContext.
 *
 * Auth-gate fix (motto_v3 §11 Engineering Standards):
 * Previously used a one-shot useEffect([], []) that read the token once on mount.
 * After login, `setIsAuthenticated` was never called again, trapping the stack on (auth).
 *
 * Now: AuthProvider owns auth state. login.tsx calls `signIn(token)` which updates
 * the context synchronously, causing this layout to re-render and swap (auth) → (tabs).
 */
import { useEffect, useState } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { QueryClient } from '@tanstack/react-query';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister';
import { View, ActivityIndicator, StyleSheet, Platform } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import * as SecureStore from 'expo-secure-store';
import { AuthProvider, useAuth } from '../src/storage/AuthContext';
import { semantic } from '../src/theme';

const CACHE_KEY_PREFIX = 'shopstack_query_cache_';
const isWeb = Platform.OS === 'web';

const webStorage = {
  getItem: (key: string): string | null => localStorage.getItem(CACHE_KEY_PREFIX + key),
  setItem: (key: string, value: string): void => {
    localStorage.setItem(CACHE_KEY_PREFIX + key, value);
  },
  removeItem: (key: string): void => {
    localStorage.removeItem(CACHE_KEY_PREFIX + key);
  },
};

const secureStorage = {
  getItem: (key: string): string | null => {
    try {
      return SecureStore.getItem(CACHE_KEY_PREFIX + key);
    } catch {
      return null;
    }
  },
  setItem: (key: string, value: string): void => {
    try {
      SecureStore.setItem(CACHE_KEY_PREFIX + key, value);
    } catch {
      // ignore
    }
  },
  removeItem: (key: string): void => {
    try {
      SecureStore.deleteItemAsync(CACHE_KEY_PREFIX + key);
    } catch {
      // ignore
    }
  },
};

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      staleTime: 30_000,
      gcTime: 24 * 60 * 60 * 1000,
    },
  },
});

const persister = createSyncStoragePersister({
  storage: isWeb ? webStorage : secureStorage,
});

/** Inner navigator — reads from AuthContext reactively */
function AppNavigator() {
  const { isAuthenticated } = useAuth();

  if (isAuthenticated === null) {
    return (
      <View style={styles.loading}>
        <ActivityIndicator size="large" color={semantic.primary} />
      </View>
    );
  }

  return (
    <>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerShown: false }}>
        {isAuthenticated ? (
          <Stack.Screen name="(tabs)" />
        ) : (
          <Stack.Screen name="(auth)" />
        )}
      </Stack>
    </>
  );
}

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={styles.root}>
      <PersistQueryClientProvider client={queryClient} persistOptions={{ persister }}>
        <AuthProvider>
          <AppNavigator />
        </AuthProvider>
      </PersistQueryClientProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  loading: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#FFFCF7',
  },
});
