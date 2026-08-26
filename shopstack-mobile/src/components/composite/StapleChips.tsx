import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { semantic, radius, spacing, typography } from '../../theme';

const STAPLES = ['milk', 'rice', 'eggs', 'bread', 'dal', 'onion', 'curd', 'sugar', 'salt', 'oil'];

interface StapleChipsProps {
  onSelect: (name: string) => void;
}

export function StapleChips({ onSelect }: StapleChipsProps) {
  return (
    <View style={styles.container}>
      <Text style={styles.hint}>Tap a staple to add it:</Text>
      <View style={styles.chips}>
        {STAPLES.map((item) => (
          <TouchableOpacity
            key={item}
            style={styles.chip}
            onPress={() => onSelect(item)}
            activeOpacity={0.8}
          >
            <Text style={styles.chipText}>{item}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginTop: spacing[3],
  },
  hint: {
    fontSize: typography.sizes.sm.size,
    color: semantic.textSecondary,
    marginBottom: spacing[2],
  },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing[2],
  },
  chip: {
    backgroundColor: semantic.surfaceElevated,
    borderWidth: 1,
    borderColor: semantic.border,
    borderRadius: radius.full,
    paddingHorizontal: spacing[3],
    paddingVertical: spacing[2],
  },
  chipText: {
    fontSize: typography.sizes.sm.size,
    color: semantic.textPrimary,
    textTransform: 'capitalize',
  },
});
