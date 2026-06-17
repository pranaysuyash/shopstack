import { useState } from 'react';
import {
  View, Text, TextInput, StyleSheet, FlatList, TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { searchInventory } from '../../src/api/search';
import type { SearchResultWire } from '../../src/api/types';

export default function SearchScreen() {
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
    <View style={styles.resultCard}>
      <View style={styles.resultInfo}>
        <Text style={styles.resultTitle}>{item.title}</Text>
        <Text style={styles.resultMeta}>{item.meta}</Text>
      </View>
      <Text style={styles.score}>{(item.score * 100).toFixed(0)}%</Text>
    </View>
  );

  return (
    <View style={styles.container}>
      <Text style={styles.header}>Search</Text>

      <View style={styles.searchBar}>
        <Ionicons name="search" size={18} color="#666" style={styles.searchIcon} />
        <TextInput
          style={styles.searchInput}
          placeholder="Search inventory..."
          placeholderTextColor="#666"
          value={query}
          onChangeText={handleSearch}
          autoCapitalize="none"
          autoCorrect={false}
        />
        {query.length > 0 && (
          <TouchableOpacity onPress={() => handleSearch('')}>
            <Ionicons name="close-circle" size={18} color="#666" />
          </TouchableOpacity>
        )}
      </View>

      <View style={styles.quickRow}>
        <TouchableOpacity style={styles.quickBtn} onPress={() => handleSearch('milk')}>
          <Text style={styles.quickText}>🥛 Milk</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.quickBtn} onPress={() => handleSearch('rice')}>
          <Text style={styles.quickText}>🍚 Rice</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.quickBtn} onPress={() => handleSearch('eggs')}>
          <Text style={styles.quickText}>🥚 Eggs</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.quickBtn} onPress={() => handleSearch('dal')}>
          <Text style={styles.quickText}>🫘 Dal</Text>
        </TouchableOpacity>
      </View>

      {loading ? (
        <ActivityIndicator size="large" color="#6366f1" style={{ marginTop: 40 }} />
      ) : (
        <FlatList
          data={results}
          keyExtractor={(_, i) => String(i)}
          renderItem={renderItem}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            query.length > 0 ? (
              <View style={styles.empty}>
                <Text style={styles.emptyText}>No results for "{query}"</Text>
              </View>
            ) : null
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f23', padding: 16, paddingTop: 60 },
  header: { fontSize: 28, fontWeight: '700', color: '#e0e0ff', marginBottom: 16 },
  searchBar: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: '#1a1a3e',
    borderRadius: 12, padding: 4, borderWidth: 1, borderColor: '#2a2a5e',
  },
  searchIcon: { paddingHorizontal: 10 },
  searchInput: { flex: 1, padding: 12, fontSize: 16, color: '#e0e0ff' },
  quickRow: { flexDirection: 'row', gap: 8, marginTop: 16, marginBottom: 16, flexWrap: 'wrap' },
  quickBtn: { backgroundColor: '#1a1a3e', borderRadius: 8, padding: 10, borderWidth: 1, borderColor: '#2a2a5e' },
  quickText: { fontSize: 13, color: '#c0c0dd' },
  list: { paddingBottom: 20 },
  resultCard: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: '#1a1a3e', borderRadius: 10, padding: 14, marginBottom: 8,
    borderWidth: 1, borderColor: '#2a2a5e',
  },
  resultInfo: { flex: 1 },
  resultTitle: { fontSize: 16, fontWeight: '600', color: '#e0e0ff' },
  resultMeta: { fontSize: 12, color: '#8888bb', marginTop: 2 },
  score: { fontSize: 14, fontWeight: '700', color: '#818cf8', marginLeft: 12 },
  empty: { alignItems: 'center', paddingTop: 40 },
  emptyText: { fontSize: 16, color: '#666' },
});
