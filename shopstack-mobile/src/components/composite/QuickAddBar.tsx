import { useState, useRef } from 'react';
import { View, StyleSheet, TouchableOpacity, Text, Modal, Pressable, ScrollView } from 'react-native';
import { Input, Button } from '../primitives';
import { semantic, radius, spacing, typography } from '../../theme';

interface QuickAddBarProps {
  placeholder?: string;
  onSubmit: (text: string) => void;
  loading?: boolean;
}

export function QuickAddBar({ placeholder = 'Add to pantry or list...', onSubmit, loading }: QuickAddBarProps) {
  const [text, setText] = useState('');
  const [pasteModal, setPasteModal] = useState(false);
  const [bulk, setBulk] = useState('');
  const inputRef = useRef<any>(null);

  function handleSubmit() {
    if (!text.trim()) return;
    onSubmit(text.trim());
    setText('');
  }

  function handlePasteSubmit() {
    const lines = bulk
      .split(/\n/)
      .map((l) => l.trim())
      .filter(Boolean);
    if (lines.length === 0) return;
    if (lines.length === 1) {
      onSubmit(lines[0]);
    } else {
      for (const line of lines) {
        onSubmit(line);
      }
    }
    setBulk('');
    setPasteModal(false);
  }

  return (
    <>
      <View style={styles.bar}>
        <Input
          ref={inputRef}
          icon="mic-outline"
          placeholder={placeholder}
          value={text}
          onChangeText={setText}
          onSubmitEditing={handleSubmit}
          returnKeyType="send"
          style={styles.input}
        />
        <Button
          title="Add"
          variant="primary"
          size="md"
          loading={loading}
          disabled={!text.trim()}
          onPress={handleSubmit}
          style={styles.addButton}
        />
        <TouchableOpacity
          style={styles.pasteButton}
          activeOpacity={0.85}
          onPress={() => {
            setPasteModal(true);
            inputRef.current?.blur();
          }}
        >
          <Text style={styles.pasteButtonText}>Bulk</Text>
        </TouchableOpacity>
      </View>

      <Modal
        visible={pasteModal}
        transparent
        animationType="fade"
        onRequestClose={() => setPasteModal(false)}
      >
        <Pressable style={styles.backdrop} onPress={() => setPasteModal(false)}>
          <View style={styles.sheet}>
            <View style={styles.sheetHeader}>
              <Text style={styles.sheetTitle}>Paste multiple items</Text>
              <Text style={styles.sheetHint}>One item per line. Example: 2 kg rice</Text>
            </View>
            <ScrollView style={styles.sheetBody} keyboardShouldPersistTaps="handled">
              <Input
                multiline
                numberOfLines={6}
                placeholder="2 kg rice\n1 litre milk\n6 eggs"
                value={bulk}
                onChangeText={setBulk}
                style={styles.bulkInput}
                textAlignVertical="top"
              />
            </ScrollView>
            <View style={styles.sheetActions}>
              <Button
                title="Cancel"
                variant="ghost"
                onPress={() => setPasteModal(false)}
              />
              <Button
                title={`Add ${bulk.split(/\n/).filter(Boolean).length} items`}
                loading={loading}
                disabled={!bulk.trim()}
                onPress={handlePasteSubmit}
              />
            </View>
          </View>
        </Pressable>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[2],
    paddingHorizontal: spacing[4],
    paddingVertical: spacing[3],
    backgroundColor: semantic.surface,
    borderTopWidth: 1,
    borderTopColor: semantic.divider,
  },
  input: {
    flex: 1,
  },
  addButton: {
    minWidth: 64,
  },
  pasteButton: {
    backgroundColor: semantic.surfaceElevated,
    borderWidth: 1,
    borderColor: semantic.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing[3],
    paddingVertical: spacing[3],
    minHeight: 48,
    justifyContent: 'center',
    alignItems: 'center',
  },
  pasteButtonText: {
    fontSize: typography.sizes.sm.size,
    fontWeight: typography.weight.semibold,
    color: semantic.primary,
  },
  backdrop: {
    flex: 1,
    backgroundColor: semantic.overlay,
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: semantic.surface,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    paddingHorizontal: spacing[5],
    paddingTop: spacing[5],
    paddingBottom: spacing[8],
    maxHeight: '70%',
  },
  sheetHeader: {
    marginBottom: spacing[4],
  },
  sheetTitle: {
    fontSize: typography.sizes.xl.size,
    fontWeight: typography.weight.bold,
    color: semantic.textPrimary,
    marginBottom: spacing[1],
  },
  sheetHint: {
    fontSize: typography.sizes.sm.size,
    color: semantic.textSecondary,
  },
  sheetBody: {
    maxHeight: 240,
  },
  bulkInput: {
    minHeight: 160,
    textAlignVertical: 'top',
  },
  sheetActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: spacing[3],
    marginTop: spacing[4],
  },
});
