import {
  View,
  Text,
  StyleSheet,
  Modal,
  Pressable,
  ScrollView,
  ActivityIndicator,
  TouchableOpacity,
  Dimensions,
} from 'react-native';
import { useRecipeDetail } from '../../hooks';
import { Card, Badge, Button, Icon } from '../../components';
import { semantic, spacing, typography, radius } from '../../theme';
import type { MealPlanDayWire, RecipeIngredientWire } from '../../api/types';
import { hapticSuccess, hapticLight } from '../../utils/haptics';

interface RecipeSheetProps {
  day?: MealPlanDayWire;
  onClose: () => void;
  onAddMissing?: (day: MealPlanDayWire) => void;
}

const { height } = Dimensions.get('window');

export function RecipeSheet({ day, onClose, onAddMissing }: RecipeSheetProps) {
  const visible = Boolean(day);
  const recipeId = day?.recipe_id;
  const { data, isLoading } = useRecipeDetail(recipeId);

  function handleAddMissing() {
    if (!day) return;
    hapticSuccess();
    onAddMissing?.(day);
  }

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
    >
      <Pressable style={styles.backdrop} onPress={onClose}>
        <View style={styles.sheet} pointerEvents="box-none">
          <Card elevated style={styles.card} pointerEvents="box-none">
            <View style={styles.handleRow}>
              <View style={styles.handle} />
              <TouchableOpacity onPress={onClose} style={styles.close}>
                <Icon name="close-outline" size={24} color={semantic.textSecondary} />
              </TouchableOpacity>
            </View>

            {isLoading ? (
              <View style={styles.loading}>
                <ActivityIndicator size="large" color={semantic.primary} />
                <Text style={styles.loadingText}>Opening recipe…</Text>
              </View>
            ) : (
              <ScrollView
                showsVerticalScrollIndicator={false}
                contentContainerStyle={styles.scrollContent}
              >
                <View style={styles.header}>
                  <Badge kind="confirm" label="Cook tonight" size="lg" />
                  {data?.cuisine && <Badge kind="watch" label={data.cuisine} />}
                </View>

                <Text style={styles.title}>{day?.recipe_name || data?.name || 'Recipe'}</Text>

                <View style={styles.metaRow}>
                  {data?.prep_minutes ? (
                    <Text style={styles.meta}>Prep {data.prep_minutes} min</Text>
                  ) : null}
                  {data?.cook_minutes ? (
                    <Text style={styles.meta}>Cook {data.cook_minutes} min</Text>
                  ) : null}
                  {data?.serves ? (
                    <Text style={styles.meta}>Serves {data.serves}</Text>
                  ) : null}
                </View>

                {data?.dietary && data.dietary.length > 0 && (
                  <View style={styles.tagRow}>
                    {data.dietary.map((tag: string) => (
                      <Badge key={tag} kind="watch" label={tag} />
                    ))}
                  </View>
                )}

                {data?.ingredients && data.ingredients.length > 0 && (
                  <View style={styles.section}>
                    <Text style={styles.sectionTitle}>Ingredients</Text>
                    {data.ingredients.map((ing: RecipeIngredientWire, i: number) => (
                      <View key={`${ing.canonical_name}-${i}`} style={styles.ingredientRow}>
                        <View style={styles.bullet} />
                        <Text style={styles.ingredientText}>
                          {formatQuantity(ing.quantity)} {ing.unit} {ing.canonical_name}
                        </Text>
                      </View>
                    ))}
                  </View>
                )}

                {data?.instructions && data.instructions.length > 0 && (
                  <View style={styles.section}>
                    <Text style={styles.sectionTitle}>Instructions</Text>
                    {data.instructions.map((step: string, i: number) => (
                      <View key={i} style={styles.stepRow}>
                        <Text style={styles.stepNumber}>{i + 1}</Text>
                        <Text style={styles.stepText}>{step}</Text>
                      </View>
                    ))}
                  </View>
                )}

                {!data?.found && (
                  <Text style={styles.notice}>
                    We couldn't load the full recipe right now. Try again when you're online.
                  </Text>
                )}

                {day && day.ingredients_missing.length > 0 && (
                  <Button
                    title="Add missing to shopping list"
                    onPress={handleAddMissing}
                    style={styles.actionButton}
                  />
                )}

                {day && day.ingredients_missing.length === 0 && (
                  <Button
                    title="You have everything — cook away"
                    variant="secondary"
                    disabled
                    style={styles.actionButton}
                  />
                )}
              </ScrollView>
            )}
          </Card>
        </View>
      </Pressable>
    </Modal>
  );
}

function formatQuantity(qty: number): string {
  if (qty === Math.floor(qty)) return String(qty);
  return qty.toFixed(1).replace(/\.0$/, '');
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: semantic.overlay,
    justifyContent: 'flex-end',
  },
  sheet: {
    maxHeight: height * 0.85,
    paddingHorizontal: spacing[4],
    paddingBottom: spacing[6],
  },
  card: {
    maxHeight: height * 0.85,
    padding: 0,
    overflow: 'hidden',
  },
  handleRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: spacing[3],
    paddingBottom: spacing[2],
    position: 'relative',
  },
  handle: {
    width: 40,
    height: 5,
    borderRadius: radius.full,
    backgroundColor: semantic.borderStrong,
  },
  close: {
    position: 'absolute',
    right: spacing[3],
    top: spacing[3],
    padding: spacing[2],
  },
  loading: {
    paddingVertical: spacing[16],
    alignItems: 'center',
  },
  loadingText: {
    marginTop: spacing[3],
    fontSize: typography.sizes.base.size,
    color: semantic.textSecondary,
  },
  scrollContent: {
    padding: spacing[5],
    paddingBottom: spacing[8],
  },
  header: {
    flexDirection: 'row',
    gap: spacing[2],
    marginBottom: spacing[3],
  },
  title: {
    fontSize: typography.sizes['2xl'].size,
    fontWeight: typography.weight.bold,
    color: semantic.textPrimary,
    marginBottom: spacing[2],
  },
  metaRow: {
    flexDirection: 'row',
    gap: spacing[4],
    marginBottom: spacing[3],
  },
  meta: {
    fontSize: typography.sizes.sm.size,
    color: semantic.textSecondary,
  },
  tagRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing[2],
    marginBottom: spacing[4],
  },
  section: {
    marginTop: spacing[5],
  },
  sectionTitle: {
    fontSize: typography.sizes.lg.size,
    fontWeight: typography.weight.bold,
    color: semantic.textPrimary,
    marginBottom: spacing[3],
  },
  ingredientRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[3],
    paddingVertical: spacing[2],
    borderBottomWidth: 1,
    borderBottomColor: semantic.divider,
  },
  bullet: {
    width: 6,
    height: 6,
    borderRadius: radius.full,
    backgroundColor: semantic.accent,
  },
  ingredientText: {
    fontSize: typography.sizes.base.size,
    color: semantic.textPrimary,
    flex: 1,
  },
  stepRow: {
    flexDirection: 'row',
    gap: spacing[3],
    paddingVertical: spacing[3],
    borderBottomWidth: 1,
    borderBottomColor: semantic.divider,
  },
  stepNumber: {
    width: 24,
    height: 24,
    borderRadius: radius.full,
    backgroundColor: semantic.primaryLight,
    color: semantic.primaryDark,
    fontSize: typography.sizes.sm.size,
    fontWeight: typography.weight.bold,
    textAlign: 'center',
    lineHeight: 24,
  },
  stepText: {
    fontSize: typography.sizes.base.size,
    color: semantic.textPrimary,
    flex: 1,
    lineHeight: typography.sizes.base.lineHeight,
  },
  notice: {
    marginTop: spacing[5],
    fontSize: typography.sizes.sm.size,
    color: semantic.textSecondary,
    fontStyle: 'italic',
  },
  actionButton: {
    marginTop: spacing[6],
  },
});
