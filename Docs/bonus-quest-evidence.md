# Bonus Quest Coverage

This document tracks which bonus quests from the product dossiers are addressed by the current implementation.

## Covered

| Quest | Status | Implementation |
|-------|--------|----------------|
 | Indian/Hinglish support | ✅ Mock | Mock STT returns Hinglish phrases; all labels in English (design choice for Gradio) |
| Voice-first interaction | ✅ | Microphone input on Market Lens tab; VoiceCommand schema; STT provider interface |
| Image recognition (scan to inventory) | ✅ | Market Lens tab; Vision + ObjectDetection + OCR provider interfaces |
| Purchase decision engine | ✅ | `compare_visible_item_to_inventory` tool with buy/skip/optional logic |
| Price memory | ✅ | `record_price_observation` tool; Price History tab; PriceObservation schema |
| Use soon alerts | ✅ | `get_use_soon_items` tool; Use Soon tab; expiry date tracking |
| Agent trace logging | ✅ | Trace schema; Agent Trace tab; full input→decision→tool call→response pipeline |
| PII redaction | ✅ | `traces/export.py` with phone, email, address, name, PAN, Aadhar redaction |
| Shopping list generation | ✅ | `create_or_update_shopping_list` tool; Shopping List tab |
| Household map | ✅ | Household Map tab with item counts per location |
| 18 seeded locations | ✅ | Database `_seed_locations()` creates hierarchical household tree |
| Total params ≤32B | ✅ | `model_registry.py` enforces parameter budget |
| Off the Grid | ✅ | `Settings.off_the_grid` flag; all providers default to mock |
| Swappable providers | ✅ | 11 ABC interfaces + ProviderRegistry with config-based wiring |
| Local-only persistence | ✅ | SQLite with WAL mode; no cloud DB |

## Partially Covered

| Quest | Status | Missing |
|-------|--------|---------|
| Fine-tuned model compliance | 🟡 | Model registry defines entry schema with hardware targets; no actual fine-tuning pipeline yet |
| Barcode/QR scanning | 🟡 | OCR interface supports it; no dedicated barcode tool |
| Time-series price trends | 🟡 | PriceMemory tab shows history as table; no chart visualization |
| Field Notes full implementation | 🟡 | Tab exists showing trace summaries; no write/edit capability |

## Not Yet Covered

| Quest | Notes |
|-------|-------|
| Auto-expiry detection on add | Currently requires manual date entry |
| Multi-user support | Single-user SQLite; no auth |
| Export/import inventory | Only trace export is implemented |
| Real model implementations | GGUF wrappers, Whisper.cpp, etc. all future |
| Built-in barcode scanning | Requires real camera access and barcode library |
| LLM grading of traces | Planner can grade, but no auto-grading loop |
