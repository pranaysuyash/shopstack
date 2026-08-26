/**
 * Global Jest setup for shopstack-mobile.
 *
 * Two native modules have no JS/test environment and MUST be mocked so the
 * suite runs under Node + jest-expo:
 *   1. expo-secure-store  — async keychain; replaced with an in-memory Map.
 *   2. @expo/vector-icons — requires native font assets; replaced with a stub.
 */
import '@testing-library/jest-native/extend-expect';

jest.mock('expo-secure-store', () => {
  const store = new Map();
  return {
    getItemAsync: jest.fn((key) => Promise.resolve(store.get(key) ?? null)),
    setItemAsync: jest.fn((key, value) => {
      store.set(key, value);
      return Promise.resolve();
    }),
    deleteItemAsync: jest.fn((key) => {
      store.delete(key);
      return Promise.resolve();
    }),
    isAvailableAsync: jest.fn(() => Promise.resolve(true)),
  };
});

jest.mock('@expo/vector-icons', () => {
  const React = require('react');
  return {
    Ionicons: (props) => React.createElement('Ionicons', props),
    MaterialIcons: (props) => React.createElement('MaterialIcons', props),
  };
});
