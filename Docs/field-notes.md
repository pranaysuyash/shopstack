# Field Notes — Design Decisions

## Why All Schemas in One File?

The domain models are deeply interconnected — `InventoryLot` references `Location`, `ShoppingListItem` references `ShoppingList`, `Trace` references `ToolCall`, etc. Splitting them across files creates circular import issues and makes it harder to see the full domain at once. Single file for now; split if it exceeds ~500 lines.

## Why Mock Providers as Default?

The product specification calls for an "Off the Grid" path. Mock providers let us develop and test the full app (UI, persistence, tool logic, traces) without loading any ML model. This means tests run in milliseconds instead of minutes, and the app is immediately usable on any machine.

## Why Gradio Blocks?

- Single-file deployment on Hugging Face Spaces
- Built-in state management, file upload, audio recording
- Gradio's DataFrame component maps directly to inventory tables
- No frontend build step required
- Custom CSS (`elem_id`, `elem_classes`) provides enough visual control

## Why 18 Seeded Locations?

Household inventory is fundamentally about *where things are*. The 18 default locations (Home → Kitchen → Fridge → Fridge Door, Fridge Top Shelf, etc.) cover 90%+ of household storage scenarios. Users can add custom locations via the API.

## Why SQLite with WAL Mode?

- Zero configuration — no server, no Docker, no cloud
- WAL mode allows concurrent reads during writes (future multi-user)
- SQLite is battle-tested and embedded in every Python distribution
- Easy backup: copy the `.db` file
- Migration path: SQLite → PostgreSQL or SQLite → LiteFS when scaling

## Why 32B Parameter Limit?

Local models are the constraint. A 7B parameter model at Q4 quantization uses ~4GB RAM; a 3B model uses ~2GB. The 32B ceiling allows multiple models to run simultaneously (e.g., 7B planner + 0.8B STT + 0.6B embeddings = ~8.4B total, well under budget).

## Why No Auto-Purchase?

Design-level decision. ShopStack is an *inventory awareness* tool, not a purchasing agent. We tell you what to buy and where it's cheapest — we don't buy it for you. This avoids payment processing, fraud liability, and the complexity of multi-store e-commerce integration.

## Why Separate Tool and Provider Registries?

- **Provider Registry**: infrastructure concerns — which model/service powers each capability
- **Tool Registry**: business logic concerns — what actions the system can take
- Separation means you can swap providers without changing tool logic, and add tools without changing provider wiring
