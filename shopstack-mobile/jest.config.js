/**
 * Jest config for shopstack-mobile.
 *
 * Runner choice (first-principles): React Native / Expo apps are exercised by
 * Jest + jest-expo + @testing-library/react-native. Vitest is web/Vite-targeted
 * and does not resolve RN native modules, so it is NOT used here.
 *
 * jest-expo provides the RN environment + transform (babel-preset-expo). Per
 * motto_v5 third-layer rule, tests stay in a separate layer (/__tests__/)
 * and never reach into persistence or network — both are mocked below.
 */
module.exports = {
  preset: 'jest-expo',
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
  transformIgnorePatterns: [
    'node_modules/(?!((jest-)?react-native|@react-native(-community)?|expo(nent)?|@expo(nent)?|expo-|@expo-|@expo/vector-icons|react-navigation|@react-navigation|@unimodules|unimodules|react-native-reanimated|react-native-gesture-handler|react-native-safe-area-context|react-native-screens|@tanstack))',
  ],
  testPathIgnorePatterns: ['/node_modules/', '/.expo/', '/e2e/'],
  // Keep output readable; CI can override with --verbose.
  verbose: false,
};
