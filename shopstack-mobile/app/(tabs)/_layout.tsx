import { Tabs } from 'expo-router';
import { StyleSheet, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { semantic, spacing, typography } from '../../src/theme';
import { SearchFab } from '../../src/components/composite/SearchFab';

type TabName = 'index' | 'inventory' | 'shopping' | 'recipes' | 'trips' | 'more';

const TABS: { name: TabName; label: string; icon: keyof typeof Ionicons.glyphMap; activeIcon: keyof typeof Ionicons.glyphMap }[] = [
  { name: 'index', label: 'Home', icon: 'home-outline', activeIcon: 'home' },
  { name: 'inventory', label: 'Pantry', icon: 'basket-outline', activeIcon: 'basket' },
  { name: 'shopping', label: 'Shop', icon: 'cart-outline', activeIcon: 'cart' },
  { name: 'recipes', label: 'Cook', icon: 'restaurant-outline', activeIcon: 'restaurant' },
  { name: 'trips', label: 'Trips', icon: 'map-outline', activeIcon: 'map' },
];

export default function TabsLayout() {
  return (
    <View style={styles.container}>
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarStyle: styles.tabBar,
          tabBarActiveTintColor: semantic.primary,
          tabBarInactiveTintColor: semantic.textTertiary,
          tabBarShowLabel: true,
          tabBarLabelStyle: styles.label,
        }}
      >
        {TABS.map((tab) => (
          <Tabs.Screen
            key={tab.name}
            name={tab.name}
            options={{
              title: tab.label,
              tabBarIcon: ({ color, focused, size }) => (
                <Ionicons
                  name={focused ? tab.activeIcon : tab.icon}
                  size={size}
                  color={color}
                />
              ),
            }}
          />
        ))}
        <Tabs.Screen
          name="more"
          options={{
            title: 'More',
            tabBarIcon: ({ color, focused, size }) => (
              <Ionicons
                name={focused ? 'ellipsis-horizontal' : 'ellipsis-horizontal'}
                size={size}
                color={color}
              />
            ),
          }}
        />
      </Tabs>
      <SearchFab />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  tabBar: {
    backgroundColor: semantic.surface,
    borderTopWidth: 1,
    borderTopColor: semantic.divider,
    paddingTop: spacing[2],
    paddingBottom: spacing[3],
    height: 84,
    elevation: 8,
    shadowColor: semantic.shadow,
    shadowOffset: { width: 0, height: -2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
  },
  label: {
    fontSize: typography.sizes.xs.size,
    fontWeight: typography.weight.medium,
    marginTop: 2,
  },
});
