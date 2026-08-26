import { useState } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { searchInventory } from '../../src/api/search';
import { Input, Card, EmptyState } from '../../src/components';
import { semantic, spacing, typography } from '../../src/theme';
import type { SearchResultWire } from '../../src/api/types';

const SUGGESTIONS = ['milk', 'rice', 'eggs', 'dal', 'bread', 'onion'];

export default function SearchScreen() {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResultWire[]>([]);
  const [loading, setLoading] = useState(false);

  async function handleSearch(q: string) {
    setQuery(q);
    if (!q.trim()) {
      setResults([]);
      return;
    }
    setLoading(true);
    try {
      const res = await searchInventory(q.trim());
      setResults(res.results ?? []);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  const renderItem = ({ item }: { item: SearchResultWire }) => (
    <Card style={styles.resultCard} padded={false}>
      <View style={styles.resultInner}>
        <View style={styles.resultText}>
          <Text style={styles.resultTitle}>{item.title}</Text>
          <Text style={styles.resultMeta}>{item.meta}</Text>
        </View>
        <Text style={styles.score}>{(item.score * 100).toFixed(0)}%</Text>
      </View>
    </Card>
  );

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Search</Text>
      </View>

      <Input
        icon="search-outline"
        placeholder="Search pantry, recipes, history..."
        value={query}
        onChangeText={handleSearch}
        autoCapitalize="none"
        autoCorrect={false}
        style={styles.searchInput}
      />

      <View style={styles.suggestions}>
        {SUGGESTIONS.map((s) => (
          <TouchableOpacity
            key={s}
            style={styles.suggestionChip}
            onPress={() => handleSearch(s)}
          >
            <Text style={styles.suggestionText}>{s}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? (
        <ActivityIndicator size="large" color={semantic.primary} style={styles.loader} />
      ) : query.length > 0 ? (
        <FlatList
          data={results}
          keyExtractor={(_, i) => String(i)}
          renderItem={renderItem}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <EmptyState
              icon="search-outline"
              title={`"${query}" didn't match anything.`}
              message="Check spelling, try a broader term, or tap + to add it to your pantry."
            />
          }
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: semantic.background, paddingTop: 64, paddingHorizontal: spacing[4] },
  header: { marginBottom: spacing[4] },
  title: {
    fontSize: typography.sizes['2xl'].size,
    fontWeight: typography.weight.bold,
    color: semantic.textPrimary,
  },
  searchInput: {
    marginBottom: spacing[3],
  },
  suggestions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing[2],
    marginBottom: spacing[4],
  },
  suggestionChip: {
    backgroundColor: semantic.surfaceElevated,
    borderWidth: 1,
    borderColor: semantic.border,
    borderRadius: 999,
    paddingHorizontal: spacing[3],
    paddingVertical: spacing[2],
  },
  suggestionText: {
    fontSize: typography.sizes.sm.size,
    color: semantic.textSecondary,
    textTransform: 'capitalize',
  },
  loader: { marginTop: spacing[10] },
  list: { paddingBottom: spacing[4] },
  resultCard: {
    marginBottom: spacing[3],
    overflow: 'hidden',
  },
  resultInner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: spacing[4],
  },
  resultText: { flex: 1, paddingRight: spacing[3] },
  resultTitle: {
    fontSize: typography.sizes.base.size,
    fontWeight: typography.weight.semibold,
    color: semantic.textPrimary,
  },
  resultMeta: {
    fontSize: typography.sizes.sm.size,
    color: semantic.textSecondary,
    marginTop: 2,
  },
  score: {
    fontSize: typography.sizes.sm.size,
    fontWeight: typography.weight.bold,
    color: semantic.primary,
  },
});
