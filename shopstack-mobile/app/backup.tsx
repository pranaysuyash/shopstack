import { useState, useCallback, useRef } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Alert, Platform,
} from 'react-native';
import { useRouter, useFocusEffect } from 'expo-router';
import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import * as DocumentPicker from 'expo-document-picker';
import { Card, Button, Icon, OfflineBanner } from '../src/components';
import { semantic, spacing, typography } from '../src/theme';
import { exportData, importData, validateImport } from '../src/api/portability';
import { useOnlineStatus } from '../src/hooks';
import { hapticSuccess, hapticError } from '../src/utils/haptics';

export default function BackupScreen() {
  const router = useRouter();
  const isOnline = useOnlineStatus();
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [lastExport, setLastExport] = useState<string | null>(null);
  const mounted = useRef(true);

  useFocusEffect(
    useCallback(() => {
      mounted.current = true;
      return () => { mounted.current = true; };
    }, []),
  );

  async function handleExport() {
    if (!isOnline) {
      Alert.alert('Offline', 'Export requires a network connection.');
      return;
    }
    setExporting(true);
    try {
      const data = await exportData();
      const json = JSON.stringify(data, null, 2);
      const fileName = `shopstack_backup_${data.exported_at?.slice(0, 10) || 'unknown'}.json`;
      const filePath = `${FileSystem.documentDirectory}${fileName}`;
      await FileSystem.writeAsStringAsync(filePath, json);

      const canShare = await Sharing.isAvailableAsync();
      if (canShare) {
        await Sharing.shareAsync(filePath, {
          mimeType: 'application/json',
          dialogTitle: 'Share ShopStack backup',
          UTI: 'public.json',
        });
      } else {
        setLastExport(filePath);
      }
      hapticSuccess();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      Alert.alert('Export Failed', msg);
    } finally {
      if (mounted.current) setExporting(false);
    }
  }

  async function handleImport() {
    if (!isOnline) {
      Alert.alert('Offline', 'Import requires a network connection.');
      return;
    }
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: 'application/json',
        copyToCacheDirectory: true,
      });
      if (result.canceled || !result.assets?.length) return;

      const file = result.assets[0];
      const content = await FileSystem.readAsStringAsync(file.uri);
      const data = JSON.parse(content);

      // Validate first
      const validation = await validateImport(data);
      const summary = [
        `New: ${validation.items_added}`,
        `Updated: ${validation.items_updated}`,
        `Price obs: ${validation.price_observations_added}`,
        ...(validation.errors.length > 0 ? [`Errors: ${validation.errors.length}`] : []),
      ].join(' · ');

      Alert.alert(
        'Import Preview',
        `This import would add:\n\n${summary}\n\nApply this import?`,
        [
          { text: 'Cancel', style: 'cancel' },
          {
            text: 'Import',
            style: 'destructive',
            onPress: async () => {
              setImporting(true);
              try {
                const importResult = await importData(data, 'merge');
                hapticSuccess();
                Alert.alert(
                  'Import Complete',
                  [
                    `Added: ${importResult.items_added}`,
                    `Updated: ${importResult.items_updated}`,
                    `Price obs: ${importResult.price_observations_added}`,
                    ...(importResult.messages.length > 0 ? [''] : []),
                    ...importResult.messages.slice(0, 3),
                    ...(importResult.errors.length > 0 ? ['', 'Errors:'] : []),
                    ...importResult.errors.slice(0, 3),
                  ].join('\n'),
                );
              } catch (err: unknown) {
                const msg = err instanceof Error ? err.message : String(err);
                Alert.alert('Import Failed', msg);
              } finally {
                if (mounted.current) setImporting(false);
              }
            },
          },
        ],
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      Alert.alert('Import Failed', msg);
    }
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <OfflineBanner isOnline={isOnline} isFetching={false} />

      <View style={styles.header}>
        <Button title="Back" variant="ghost" size="sm" onPress={() => router.back()} />
        <Text style={styles.title}>Backup & Restore</Text>
      </View>

      <Card elevated style={styles.card}>
        <View style={styles.cardHeader}>
          <Icon name="cloud-download-outline" size={24} color={semantic.primary} />
          <Text style={styles.cardTitle}>Export Data</Text>
        </View>
        <Text style={styles.cardDesc}>
          Download all your inventory, price history, and field notes as a JSON file.
          Use this to back up your data or transfer to another device.
        </Text>
        <Button
          title={exporting ? 'Exporting...' : 'Export to JSON'}
          loading={exporting}
          disabled={!isOnline}
          onPress={handleExport}
          style={{ marginTop: spacing[4] }}
        />
        {lastExport && (
          <Text style={styles.filePath}>Saved: {lastExport}</Text>
        )}
      </Card>

      <Card elevated style={styles.card}>
        <View style={styles.cardHeader}>
          <Icon name="cloud-upload-outline" size={24} color={semantic.warning} />
          <Text style={styles.cardTitle}>Import Data</Text>
        </View>
        <Text style={styles.cardDesc}>
          Restore from a previous backup JSON file. You'll see a preview of changes
          before the import is applied. Existing items are merged by name.
        </Text>
        <Button
          title={importing ? 'Importing...' : 'Import from JSON'}
          loading={importing}
          disabled={!isOnline}
          variant="secondary"
          onPress={handleImport}
          style={{ marginTop: spacing[4] }}
        />
      </Card>

      <Card style={styles.infoCard}>
        <View style={styles.cardHeader}>
          <Icon name="information-circle-outline" size={20} color={semantic.info} />
          <Text style={styles.infoTitle}>About Backup</Text>
        </View>
        <Text style={styles.infoText}>
          Backups include your full inventory, price observations, and field notes.
          Household settings and account info are not exported. Use the export to
          periodically save your data or transfer it between devices.
        </Text>
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: semantic.background },
  content: { paddingTop: 64, paddingHorizontal: spacing[4], paddingBottom: 40 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[3],
    marginBottom: spacing[6],
  },
  title: {
    fontSize: typography.sizes['2xl'].size,
    fontWeight: typography.weight.bold,
    color: semantic.textPrimary,
  },
  card: {
    marginBottom: spacing[4],
    padding: spacing[5],
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[3],
    marginBottom: spacing[3],
  },
  cardTitle: {
    fontSize: typography.sizes.lg.size,
    fontWeight: typography.weight.semibold,
    color: semantic.textPrimary,
  },
  cardDesc: {
    fontSize: typography.sizes.sm.size,
    color: semantic.textSecondary,
    lineHeight: 20,
  },
  filePath: {
    fontSize: typography.sizes.xs.size,
    color: semantic.textTertiary,
    marginTop: spacing[3],
  },
  infoCard: {
    marginBottom: spacing[4],
    padding: spacing[4],
    backgroundColor: semantic.surfaceElevated,
  },
  infoTitle: {
    fontSize: typography.sizes.base.size,
    fontWeight: typography.weight.semibold,
    color: semantic.textPrimary,
  },
  infoText: {
    fontSize: typography.sizes.sm.size,
    color: semantic.textSecondary,
    lineHeight: 20,
    marginTop: spacing[2],
  },
});
