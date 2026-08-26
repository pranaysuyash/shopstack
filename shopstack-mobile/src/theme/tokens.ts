/**
 * ShopStack Mobile — Design Tokens
 *
 * Single source of truth for the D2C "Warm Pantry Intelligence" design system.
 * Light-first, offline-capable (system fonts only), semantic-first naming.
 *
 * Aligned with shopstack/ui/theme.py palette and Docs/SHOPSTACK_DESIGN_PLAN.
 */

export const palette = {
  // Warm pantry neutrals
  paper: {
    50: '#FFFCF7',
    100: '#FFF8ED',
    200: '#F5EDE0',
    300: '#EBE2D5',
    400: '#D8CFC2',
    500: '#A8A199',
    600: '#6B655F',
    700: '#4A4641',
    800: '#2E2C28',
    900: '#1A1814',
  },

  // Olive / pantry green
  green: {
    50: '#F1F8F0',
    100: '#DDEEDD',
    200: '#B6D5B4',
    300: '#8EB98C',
    400: '#6F8A6A',
    500: '#4F6B4C',
    600: '#3B5239',
    700: '#2A3D28',
    800: '#1E2B1D',
    900: '#121A12',
  },

  // Terracotta / appetite / urgency
  terracotta: {
    50: '#FFF4EE',
    100: '#FFE3D5',
    200: '#FFC7AA',
    300: '#FFA47C',
    400: '#E58555',
    500: '#C96B3E',
    600: '#A3502E',
    700: '#7F3A20',
    800: '#5C2815',
    900: '#3B160B',
  },

  // Golden mustard / attention
  amber: {
    50: '#FFFBEB',
    100: '#FEF3C7',
    200: '#FDE68A',
    300: '#FCD34D',
    400: '#D4A34B',
    500: '#B58430',
    600: '#966520',
    700: '#714B17',
    800: '#523612',
    900: '#33210B',
  },

  // Soft berry / destructive
  berry: {
    50: '#FEF2F2',
    100: '#FEE2E2',
    200: '#FECACA',
    300: '#FCA5A5',
    400: '#DC4444',
    500: '#B91C1C',
    600: '#991B1B',
    700: '#7F1D1D',
    800: '#5B1818',
    900: '#3B1212',
  },

  // Deep espresso / readable text
  espresso: {
    50: '#F5F0EB',
    100: '#E6DDD4',
    200: '#CFC0B1',
    300: '#B5A08D',
    400: '#8B7A6A',
    500: '#6B5D50',
    600: '#4F443A',
    700: '#3A3129',
    800: '#271F1A',
    900: '#1A1512',
  },
} as const;

export const semantic = {
  background: palette.paper[50],
  surface: '#FFFFFF',
  surfaceElevated: palette.paper[100],
  surfacePressed: palette.paper[200],

  textPrimary: palette.espresso[800],
  textSecondary: palette.espresso[500],
  textTertiary: palette.espresso[400],
  textInverse: palette.paper[50],

  primary: palette.green[500],
  primaryLight: palette.green[100],
  primaryDark: palette.green[700],
  onPrimary: palette.paper[50],

  accent: palette.amber[400],
  accentLight: palette.amber[100],

  success: palette.green[500],
  warning: palette.amber[400],
  danger: palette.terracotta[500],
  info: palette.espresso[400],
  terracotta: palette.terracotta[500],

  border: palette.paper[300],
  borderStrong: palette.paper[400],
  divider: palette.paper[200],

  overlay: 'rgba(26, 24, 20, 0.45)',
  shadow: 'rgba(26, 24, 20, 0.12)',
} as const;

export const decision = {
  buy: { fg: palette.paper[50], bg: palette.green[500], icon: 'cart-outline' as const },
  skip: { fg: palette.espresso[500], bg: palette.paper[200], icon: 'close-circle-outline' as const },
  useSoon: { fg: palette.espresso[800], bg: palette.amber[100], icon: 'time-outline' as const },
  compare: { fg: palette.espresso[800], bg: palette.paper[200], icon: 'git-compare-outline' as const },
  confirm: { fg: palette.paper[50], bg: palette.terracotta[500], icon: 'checkmark-circle-outline' as const },
  watch: { fg: palette.espresso[800], bg: palette.green[100], icon: 'eye-outline' as const },
} as const;

export const spacing = {
  px: 1,
  0: 0,
  1: 4,
  2: 8,
  3: 12,
  4: 16,
  5: 20,
  6: 24,
  8: 32,
  10: 40,
  12: 48,
  16: 64,
} as const;

export const radius = {
  none: 0,
  sm: 6,
  md: 10,
  lg: 14,
  xl: 20,
  full: 999,
} as const;

export const typography = {
  // System-first, offline-capable stack
  family: {
    ios: {
      display: 'Georgia',
      body: '-apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display"',
      mono: 'SFMono-Regular',
    },
    android: {
      display: 'serif',
      body: 'sans-serif',
      mono: 'monospace',
    },
  },

  sizes: {
    xs: { size: 11, lineHeight: 14, letterSpacing: 0.02 },
    sm: { size: 13, lineHeight: 18, letterSpacing: 0 },
    base: { size: 15, lineHeight: 22, letterSpacing: 0 },
    lg: { size: 17, lineHeight: 24, letterSpacing: -0.01 },
    xl: { size: 20, lineHeight: 28, letterSpacing: -0.02 },
    '2xl': { size: 24, lineHeight: 32, letterSpacing: -0.02 },
    '3xl': { size: 30, lineHeight: 38, letterSpacing: -0.03 },
  },

  weight: {
    normal: '400' as const,
    medium: '500' as const,
    semibold: '600' as const,
    bold: '700' as const,
  },
} as const;

export const shadow = {
  sm: {
    shadowColor: semantic.shadow,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 1,
    shadowRadius: 2,
    elevation: 1,
  },
  md: {
    shadowColor: semantic.shadow,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 1,
    shadowRadius: 6,
    elevation: 3,
  },
  lg: {
    shadowColor: semantic.shadow,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 1,
    shadowRadius: 12,
    elevation: 6,
  },
} as const;

export const timing = {
  fast: 150,
  normal: 250,
  slow: 350,
} as const;

export const z = {
  base: 0,
  dropdown: 10,
  sticky: 20,
  modal: 30,
  toast: 40,
} as const;
