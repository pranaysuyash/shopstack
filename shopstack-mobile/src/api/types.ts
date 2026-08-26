// ── shopstack-mobile: TypeScript types for the /api/v1 surface ──
// Auto-mapped from shopstack/api/v1/schemas/__init__.py

// ── Common ──────────────────────────────────────────────────────────

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  timestamp?: string;
}

export interface ListResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface Household {
  household_id: string;
  name: string;
  is_active: boolean;
}

// ── Auth ────────────────────────────────────────────────────────────

export interface LoginRequest {
  device_id: string;
  device_secret: string;
  requested_household_id?: string;
}

export interface TokenResponse {
  token: string;
  expires_at: string;
  household_id: string;
  household_name: string;
}

export interface RegisterRequest {
  device_id: string;
  device_secret: string;
  household_name: string;
  household_id?: string;
}

export interface WhoAmI {
  app_name: string;
  app_version?: string;
  household_id: string;
  household_name?: string;
  runtime_mode: string;
  timestamp: string;
}

// ── Inventory ──────────────────────────────────────────────────────

export interface InventoryLot {
  lot_id: string;
  canonical_name: string;
  display_name: string;
  category: string;
  quantity: number;
  unit: string;
  storage_location_id: string;
  storage_location_name: string;
  purchase_date?: string;
  estimated_use_by_date?: string;
  label_expiry_date?: string;
  opened_date?: string;
  price_paid?: number;
  currency: string;
  confidence: number;
  nutrition_per_100g?: Record<string, number> | null;
  status: string;
}

export interface AddInventoryLotRequest {
  canonical_name: string;
  display_name?: string;
  quantity?: number;
  unit?: string;
  storage_location_id?: string;
  purchase_date?: string;
  estimated_use_by_date?: string;
  label_expiry_date?: string;
  opened_date?: string;
  price_paid?: number;
  currency?: string;
  confidence?: number;
  category?: string;
  nutrition_per_100g?: Record<string, number> | null;
}

export interface ConsumeInventoryRequest {
  quantity: number;
  unit?: string;
  consumed_at?: string;
}

// ── Household ──────────────────────────────────────────────────────

export interface CreateHouseholdRequest {
  household_id?: string;
  name: string;
  notes?: string;
}

export interface HouseholdListResponse {
  items: Household[];
  active_household_id: string;
}

// ── Shopping ───────────────────────────────────────────────────────

export interface ShoppingItemInput {
  canonical_name: string;
  requested_quantity?: number;
  unit?: string;
  priority?: string;
  reason?: string;
}

export interface ShoppingListItemWire {
  item_id: string;
  canonical_name: string;
  requested_quantity?: number;
  unit?: string;
  priority: string;
  reason: string;
  status: string;
  linked_inventory_lots: string[];
}

export interface ShoppingListWire {
  list_id: string;
  name: string;
  created_at: string;
  updated_at: string;
  goal: string;
  is_active: boolean;
  items: ShoppingListItemWire[];
}

export interface CreateShoppingListRequest {
  goal?: string;
  items?: ShoppingItemInput[];
}

export interface AddShoppingItemsRequest {
  items: ShoppingItemInput[];
}

export interface CompletionItemWire {
  canonical_name: string;
  lot_id: string;
  quantity: number;
  unit: string;
}

export interface CompleteShoppingListResponse {
  success: boolean;
  list_id: string;
  items_added: CompletionItemWire[];
  items_skipped: number;
  goal: string;
  message: string;
}

export interface CompleteShoppingListRequest {
  purchased_item_ids?: string[];
}

export interface MarkPurchasedItemWire {
  canonical_name: string;
  lot_id: string;
  quantity: number;
  unit: string;
}

export interface MarkPurchasedRequest {
  item_ids: string[];
}

export interface MarkPurchasedResponse {
  success: boolean;
  items_added: MarkPurchasedItemWire[];
  message: string;
}

// ── Dashboard ──────────────────────────────────────────────────────

export interface DashboardSnapshot {
  household_id: string;
  timestamp: string;
  pantry_count: number;
  use_soon_count: number;
  low_items_count: number;
  recent_purchases_count: number;
  use_soon_items: Record<string, unknown>[];
  low_items: Record<string, unknown>[];
  recent_purchases: Record<string, unknown>[];
  has_trip_recommendation: boolean;
}

// ── Search ─────────────────────────────────────────────────────────

export interface SearchResultWire {
  kind: string;
  title: string;
  meta: string;
  score: number;
  action_kind: string;
  action_target: string;
  household_id: string;
}

export interface SearchResponse {
  query: string;
  results: SearchResultWire[];
  count: number;
}

export interface VoiceIntentRequest {
  text: string;
  language?: string;
}

export interface VoiceIntentResponse {
  original_text: string;
  translated_text: string;
  language: string;
  action: string;
  canonical_items: string[];
  target_scene: string;
  confidence: number;
  notes: string[];
}

// ── Command Surface ────────────────────────────────────────────────

export interface CommandRequest {
  text: string;
}

export interface CommandPreviewResponse {
  original_text: string;
  intent: CommandIntentWire;
  would_mutate: boolean;
  route_kind: string;
  summary: string;
}

export interface CommandIntentWire {
  action: string;
  canonical_name: string;
  raw_text: string;
}

export interface CommandResultWire {
  success: boolean;
  action: string;
  canonical_name: string;
  message: string;
  toast_html: string;
}

export interface CommandResponse {
  household_id: string;
  original_text: string;
  intent: CommandIntentWire;
  result: CommandResultWire;
}

export interface CommandHistoryItemWire {
  trace_id: string;
  timestamp: string;
  input_type: string;
  original_text: string;
  action: string;
  canonical_name: string;
  success: boolean;
  summary: string;
}

export interface CommandHistoryResponse {
  items: CommandHistoryItemWire[];
  count: number;
}

// ── Intelligence ───────────────────────────────────────────────────

export interface DecisionExplanationWire {
  item_id: string;
  canonical_name: string;
  action: string;
  confidence: number;
  summary: string;
  key_signal: string;
  confidence_label: string;
  confidence_caveat: string;
  warnings: Record<string, string>[];
  override_hint: string;
  evidence_summary: string[];
  freshness_status: string;
  freshness_label: string;
}

export interface RecurringPlanItemWire {
  canonical_name: string;
  display_name: string;
  action: string;
  confidence: number;
  priority: number;
  reasons: string[];
  days_until_next?: number;
  typical_interval_days?: number;
}

export interface RecurringPlanResponse {
  window_days: number;
  summary: string;
  count: number;
  items: RecurringPlanItemWire[];
}

export interface MealPlanDayWire {
  date: string;
  recipe_name?: string;
  recipe_id?: string;
  cuisine?: string;
  cook_minutes?: number;
  score?: number;
  ingredients_used: string[];
  ingredients_missing: string[];
  confidence: string;
  rationale: string;
}

export interface RecipeIngredientWire {
  canonical_name: string;
  quantity: number;
  unit: string;
}

export interface RecipeDetailResponse {
  recipe_id: string;
  name: string;
  cuisine: string;
  dietary: string[];
  prep_minutes: number;
  cook_minutes: number;
  serves: number;
  tags: string[];
  ingredients: RecipeIngredientWire[];
  instructions: string[];
  found: boolean;
}

export interface MealPlanResponse {
  summary: string;
  days: number;
  start_date: string;
  count: number;
  items: MealPlanDayWire[];
}

// ── Account / Privacy / Undo ───────────────────────────────────────

export interface PurgeDataResponse {
  success: boolean;
  traces_purged: number;
  community_observations_purged: number;
  sms_registry_cleared: number;
  voice_memos_purged: number;
  backups_purged: number;
  errors: string[];
}

export interface UndoRequest {
  entry_id?: string;
}

export interface UndoResponse {
  success: boolean;
  entry_id: string;
  kind: string;
  description: string;
  message: string;
}

export interface RetentionPolicyWire {
  trace_ttl_days: number;
  trace_max_rows: number;
  community_pool_retention_days: number;
  voice_memo_retention_days: number;
  sms_registry_retention_days: number;
  backup_retention_days: number;
  locale_persistence: boolean;
  community_optin: boolean;
}

export interface RetentionSummaryResponse {
  summary: RetentionPolicyWire;
}

export interface UpdateRetentionRequest {
  key: string;
  value: string;
}

export interface StoreModeToggleRequest {
  item_id: string;
}

export interface StoreModeToggleResponse {
  success: boolean;
  new_status: string;
  message: string;
}

// ── Corrections ────────────────────────────────────────────────────

export interface CorrectionItemWire {
  event_id: string;
  canonical_name: string;
  was_action: string;
  should_be_action: string;
  source: string;
  timestamp: string;
  accepted: boolean;
}

export interface CorrectionListResponse {
  summary: string;
  count: number;
  items: CorrectionItemWire[];
}

export interface CorrectionCreateRequest {
  canonical_name: string;
  was_action: string;
  should_be_action: string;
  reason?: string;
}

export interface CorrectionCreateResponse {
  event_id: string;
  canonical_name: string;
  was_action: string;
  should_be_action: string;
  source: string;
  timestamp: string;
  accepted: boolean;
}

// ── Traces ────────────────────────────────────────────────────────

export interface TraceSummaryWire {
  trace_id: string;
  input_type: string;
  user_goal: string;
  timestamp: string;
  human_confirmation?: string;
  final_response: string;
  action: string;
  tool_call_count: number;
}

export interface TraceDetailWire extends TraceSummaryWire {
  redacted_user_request: string;
  perception: Record<string, unknown>;
  inventory_context: Record<string, unknown>;
  decision: Record<string, unknown>;
  proposed_tool_calls: Record<string, unknown>[];
  actor_id: string;
}

export interface TraceListResponse {
  summary: string;
  count: number;
  items: TraceSummaryWire[];
}

export interface TraceDetailResponse {
  trace: TraceDetailWire;
}

export interface TraceExportResponse {
  trace_id: string;
  redacted: boolean;
  jsonl: string;
}
