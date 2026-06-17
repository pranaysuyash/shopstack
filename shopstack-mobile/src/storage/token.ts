import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const TOKEN_KEY = 'shopstack_auth_token';
const HOUSEHOLD_KEY = 'shopstack_household_id';
const DEVICE_ID_KEY = 'shopstack_device_id';
const DEVICE_SECRET_KEY = 'shopstack_device_secret';
const API_BASE_KEY = 'shopstack_api_base_url';

// On web, fall back to localStorage since SecureStore is unavailable
const isWeb = Platform.OS === 'web';

function safeGet(key: string): Promise<string | null> {
  if (isWeb) {
    return Promise.resolve(localStorage.getItem(key));
  }
  return SecureStore.getItemAsync(key);
}

function safeSet(key: string, value: string): Promise<void> {
  if (isWeb) {
    localStorage.setItem(key, value);
    return Promise.resolve();
  }
  return SecureStore.setItemAsync(key, value);
}

function safeDelete(key: string): Promise<void> {
  if (isWeb) {
    localStorage.removeItem(key);
    return Promise.resolve();
  }
  return SecureStore.deleteItemAsync(key);
}

// ── Token ───────────────────────────────────────────────────────────

export async function getToken(): Promise<string | null> {
  return safeGet(TOKEN_KEY);
}

export async function setToken(token: string): Promise<void> {
  return safeSet(TOKEN_KEY, token);
}

export async function deleteToken(): Promise<void> {
  return safeDelete(TOKEN_KEY);
}

// ── Device identity ────────────────────────────────────────────────

export async function getDeviceId(): Promise<string | null> {
  return safeGet(DEVICE_ID_KEY);
}

export async function setDeviceId(id: string): Promise<void> {
  return safeSet(DEVICE_ID_KEY, id);
}

export async function getDeviceSecret(): Promise<string | null> {
  return safeGet(DEVICE_SECRET_KEY);
}

export async function setDeviceSecret(secret: string): Promise<void> {
  return safeSet(DEVICE_SECRET_KEY, secret);
}

// ── Household ──────────────────────────────────────────────────────

export async function getActiveHouseholdId(): Promise<string | null> {
  return safeGet(HOUSEHOLD_KEY);
}

export async function setActiveHouseholdId(id: string): Promise<void> {
  return safeSet(HOUSEHOLD_KEY, id);
}

// ── API base URL ───────────────────────────────────────────────────

export async function getApiBaseUrl(): Promise<string> {
  const stored = await safeGet(API_BASE_KEY);
  return stored || 'http://localhost:7860';
}

export async function setApiBaseUrl(url: string): Promise<void> {
  return safeSet(API_BASE_KEY, url);
}

// ── Generate device identity (first launch) ────────────────────────

export function generateDeviceId(): string {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
  let result = 'device_';
  for (let i = 0; i < 24; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

export function generateDeviceSecret(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-';
  let result = '';
  for (let i = 0; i < 43; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

// ── Clear all stored data (logout) ─────────────────────────────────

export async function clearAll(): Promise<void> {
  await Promise.all([
    deleteToken(),
    safeDelete(HOUSEHOLD_KEY),
  ]);
}
