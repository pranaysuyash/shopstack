# ShopStack — Gradio UI Surface and Off-Brand Custom Frontend Strategy

**Project:** ShopStack / GharStock  
**Purpose:** Define what Gradio gives by default, what should be customized, and how ShopStack can claim the Off-Brand bonus quest without losing the speed and reliability of Gradio.

_Last updated: 2026-06-05_

---

## 1. Why This Matters

The Build Small Hackathon requires the app to be built on Gradio and hosted as a Hugging Face Space. One of the bonus quests is:

> **Off-Brand** — a custom frontend that pushes past the default Gradio look.

For ShopStack, this should not mean abandoning Gradio. It should mean using Gradio as the product canvas while making the app feel like a real household shopping system:

- market lens,
- voice-first controls,
- inventory cards,
- item crops,
- fridge/pantry dashboard,
- shopping decision panel,
- trace drawer,
- price memory,
- household location map,
- mobile-friendly layout.

The judges should immediately see that this is not a default `gr.Interface` wrapper.

---

## 2. What Gradio Supports by Default

### 2.1 App Construction

Gradio supports:

- `Interface` for simple one-function demos,
- `ChatInterface` for chat-style apps,
- `TabbedInterface` for combining demos,
- `Blocks` for custom layouts, multi-step flows, events, and richer application logic.

For ShopStack, use **Blocks** as the main app structure.

Recommended top-level tabs:

1. Home / Today
2. Shopping List
3. Market Lens
4. Add Purchase
5. Inventory
6. Use Soon
7. Price Memory
8. Household Map
9. Agent Trace
10. Field Notes

---

### 2.2 Layout Primitives

Useful default layout primitives:

- Row
- Column
- Group
- Tab
- Accordion
- Sidebar
- Navbar
- Walkthrough
- render

ShopStack use:

- Sidebar for current list, inventory alerts, and mode selector.
- Tabs for major product surfaces.
- Rows/Columns for image + decision split.
- Accordions for traces, raw OCR, raw detections, model metadata.
- Walkthrough for onboarding.

---

### 2.3 Core Components

Useful default components for ShopStack:

#### Text / Structured Data

- Textbox
- Markdown
- JSON
- Label
- HighlightedText
- Code
- Dataframe
- Dataset
- Number
- Slider
- Dropdown
- Radio
- Checkbox / CheckboxGroup
- DateTime

ShopStack uses:

- command input,
- parsed tool calls,
- inventory tables,
- price history,
- JSON trace viewer,
- item classification confidence,
- expiry/date corrections.

#### Media

- Image
- ImageEditor
- SimpleImage
- AnnotatedImage
- ImageSlider
- Gallery
- Audio
- Video
- File
- UploadButton
- DownloadButton
- Model3D

ShopStack uses:

- market photo input,
- receipt/packet close-up upload,
- short video scan input,
- voice input,
- spoken answer output,
- annotated image output,
- segmented item crops,
- downloadable CSV/JSON reports,
- future 3D/household map explorations.

#### Chat / Dialogue

- Chatbot
- Dialogue
- MultimodalTextbox

ShopStack uses:

- “Ask ShopStack” voice/text assistant,
- multimodal ask: image + voice/text question,
- household member conversation history,
- market-mode quick Q&A.

#### Plots / Analytics

- Plot
- BarPlot
- LinePlot
- ScatterPlot

ShopStack uses:

- price history chart,
- consumption trend,
- category spend,
- store comparison,
- time-of-day price pattern,
- weather/trip effort analytics.

#### State / Events

- State
- Timer
- Button
- ClearButton
- DuplicateButton
- event listeners
- queue

ShopStack uses:

- session inventory state,
- pending tool-call state,
- confirmation state,
- periodic status updates,
- queued model inference,
- interactive corrections.

---

## 3. What Should Be Custom for ShopStack

### 3.1 Custom Visual Identity

Create a ShopStack visual system:

- name: ShopStack,
- tagline: “Remember what’s at home while you shop.”
- palette inspired by grocery shelves / receipts / fridge labels,
- rounded item cards,
- receipt-like trace drawer,
- fridge/pantry section headers,
- market lens status chips,
- clear buy / skip / check-expiry / already-home states.

Avoid looking like raw Gradio default.

---

### 3.2 Custom CSS

Use Gradio custom CSS for:

- item cards,
- status badges,
- mobile-first layout,
- sticky shopping list,
- trace drawer,
- confidence chips,
- fridge/pantry color grouping,
- segmented crop grids,
- price warning states,
- voice mode pulse,
- map panel styling,
- “use soon” urgency cards.

Preferred pattern:

- assign stable `elem_id` and `elem_classes` to components,
- avoid brittle selectors against Gradio internal DOM,
- store CSS in `assets/shopstack.css`,
- pass it through `css_paths`.

Example component naming:

```python
gr.Markdown("## Market Lens", elem_id="market-lens-title")
gr.JSON(elem_classes=["trace-json"])
gr.Gallery(elem_classes=["item-crop-gallery"])
```

---

### 3.3 Custom JavaScript

Use JS only where it adds real product feel.

Good JS uses:

- microphone affordance animation,
- keyboard shortcuts,
- sticky bottom action bar,
- card selection animations,
- lightweight client-side filtering,
- scroll-to-trace,
- copy-to-clipboard,
- image overlay toggles,
- map interactions,
- progress animations.

Avoid:

- fragile DOM manipulation,
- logic that should be in Python,
- hidden state mutations,
- security-sensitive behavior,
- scraping or browser automation inside the Gradio client.

---

### 3.4 Custom HTML

Use `gr.HTML` or `head` injection for:

- hero header,
- small status chips,
- static card templates,
- SVG icons,
- custom metadata,
- optional map container,
- visual timeline.

But keep factual text and model outputs in controlled components, not hallucinated into generated images.

---

### 3.5 Custom Components

Only create a custom Gradio component if the built-in components and CSS/JS are not enough.

Potential ShopStack custom components:

1. **ItemCardGrid**
   - item crop,
   - name,
   - quantity,
   - location,
   - expiry,
   - confidence,
   - accept/correct buttons.

2. **MarketLensOverlay**
   - uploaded image/video frame,
   - boxes/masks,
   - buy/skip labels,
   - item matching to shopping list.

3. **FridgePantryMap**
   - shelf zones,
   - draggable item locations,
   - last-seen badges.

4. **PriceHeatmap**
   - map/heatmap using MapLibre/Leaflet,
   - store points,
   - price observations,
   - time filters.

5. **TraceTimeline**
   - perception → retrieval → decision → tool call → confirmation → result.

Recommended approach:

- Use built-in Gradio + CSS first.
- Create one custom component only if it materially improves the app’s identity.
- The strongest custom component candidate is **TraceTimeline** or **MarketLensOverlay**.
- For the Off-Brand badge, custom CSS/JS + Blocks may already be enough if executed well.

---

## 4. ShopStack UI Surfaces

### 4.1 Today Dashboard

Shows:

- what to buy,
- what to use soon,
- what is low,
- what was last added,
- quick voice ask,
- next shopping suggestion.

Components:

- Markdown,
- Buttons,
- Dataframe/cards,
- Audio,
- Chatbot,
- Plot.

Custom styling:

- fridge/pantry tiles,
- use-soon urgency cards,
- “shop today” call-to-action.

---

### 4.2 Shopping List

Features:

- voice/text list creation,
- model-parsed items,
- already-at-home warnings,
- route/store hints,
- buy/skip status.

Components:

- Audio,
- Textbox,
- JSON,
- Dataframe,
- CheckboxGroup,
- Buttons.

Custom styling:

- list cards,
- already-have chip,
- urgent chip,
- optional chip.

---

### 4.3 Market Lens

Features:

- upload image or short video,
- ask “do I need this?”,
- identify visible items,
- compare with list and inventory,
- display buy/skip/check-expiry decisions.

Components:

- Image,
- Video,
- Audio,
- AnnotatedImage,
- Gallery,
- JSON,
- Markdown.

Custom styling:

- phone-camera-like panel,
- item overlays,
- decision chips.

---

### 4.4 Add Purchase

Features:

- upload purchase photo,
- upload receipt,
- voice correction,
- item cards,
- proposed inventory mutations,
- confirmation.

Components:

- Image,
- File,
- Audio,
- Gallery,
- Dataframe,
- JSON,
- Buttons.

Custom styling:

- shopping-bag-to-inventory flow,
- item crop cards,
- confirmation drawer.

---

### 4.5 Inventory

Features:

- fridge/pantry/household item list,
- search,
- sort by expiry/location/category,
- mark consumed,
- move location,
- export CSV/JSON.

Components:

- Dataframe,
- Textbox,
- Dropdown,
- Buttons,
- DownloadButton.

Custom styling:

- household sections,
- location chips,
- expiry color states.

---

### 4.6 Household Map

Features:

- user-defined locations,
- item last-seen memory,
- movement events,
- shelf/fridge zones,
- find item query.

Components:

- Image,
- AnnotatedImage,
- Plot/HTML map,
- Gallery,
- Dataframe,
- JSON.

Custom styling:

- home map cards,
- heatmap-like overlays,
- shelf zones.

Potential custom component:

- FridgePantryMap.

---

### 4.7 Price Memory

Features:

- item price history,
- store comparison,
- travel-adjusted savings,
- weather/trip context,
- “worth going?” decision.

Components:

- Plot,
- LinePlot,
- BarPlot,
- Dataframe,
- JSON,
- Markdown.

Custom styling:

- deal score cards,
- cheapest store chips,
- travel penalty chips.

Potential custom component:

- PriceHeatmap.

---

### 4.8 Agent Trace

Features:

- model/provider used,
- detections,
- retrieved memory,
- proposed tool calls,
- confirmation,
- final mutation/result,
- export anonymized trace.

Components:

- JSON,
- Code,
- Markdown,
- Buttons,
- DownloadButton.

Custom styling:

- receipt-like trace timeline,
- collapsible sections,
- privacy redaction badges.

Potential custom component:

- TraceTimeline.

---

## 5. Off-Brand Badge Strategy

### Minimum Off-Brand Standard

The app should have:

- custom theme,
- custom CSS,
- non-default layout,
- mobile-first view,
- branded header,
- card-based inventory,
- visual item crops,
- trace drawer,
- polished empty/loading/error states.

### Strong Off-Brand Standard

Add:

- market lens overlay,
- custom item cards,
- status chips,
- voice mode animation,
- use-soon dashboard,
- visual household map,
- price memory charts,
- guided walkthrough.

### Excellent Off-Brand Standard

Add one custom frontend surface:

- TraceTimeline,
- MarketLensOverlay,
- FridgePantryMap,
- or PriceHeatmap.

If only one custom component is built, choose **MarketLensOverlay** because it makes the product visually distinct immediately.

---

## 6. Gradio Features Worth Using Deliberately

### Queue

Enable queue for model inference and image/video processing.

### PWA

Use PWA behavior for Spaces if available/enabled, because ShopStack is naturally mobile-first.

### I18n

Use Gradio static text translation support for English/Hinglish/Hindi labels where useful.

### MCP / API Exposure

Keep documented functions clean. Gradio can expose API endpoints; this helps Codex/benchmark scripts call the app programmatically.

### State

Use `gr.State` for pending purchase, pending tool calls, current shopping list, and session context.

### Launch Options

Use safe paths:

- restrict allowed paths,
- block private data directories,
- clear temp files,
- avoid exposing raw household uploads unintentionally.

---

## 7. Implementation Principles

1. Use `gr.Blocks`, not a single `gr.Interface`.
2. Keep app screens product-like, not notebook-like.
3. Use custom CSS and stable `elem_id` / `elem_classes`.
4. Keep client JS minimal and purposeful.
5. Prefer Python-side state and tool-call logic.
6. Create custom components only where the product interaction demands it.
7. Do not compromise Gradio deployability.
8. Keep the Space README clear about models, badges, traces, and privacy.
9. Make the app usable on mobile.
10. Make every mode visible in the walkthrough video.

---

## 8. Agent Instructions

When implementing ShopStack UI:

- Build with `gr.Blocks`.
- Create `assets/shopstack.css`.
- Use stable `elem_id` and `elem_classes` on important components.
- Add a branded header and mobile-first layout.
- Create card-style visual sections for Today, Shopping List, Market Lens, Add Purchase, Inventory, Use Soon, Price Memory, Household Map, and Agent Trace.
- Implement trace drawer as a first-class UI element.
- Add custom CSS for item cards, status chips, confidence labels, and urgency states.
- Add optional JS only for animations, shortcuts, or UI affordances.
- Do not hardcode Gradio internal DOM selectors.
- Keep the app Space-compatible.
- Consider one custom component only after built-in Gradio + CSS/JS hits a wall.
- Track Off-Brand evidence in README and Field Notes.

---

## 9. Exploration Items to Add to Exploration Map

- Test whether Gradio `AnnotatedImage` is enough for MarketLensOverlay.
- Test whether `Plot` or `gr.HTML` is better for maps/heatmaps.
- Explore custom `TraceTimeline` component.
- Explore custom `ItemCardGrid` component.
- Explore mobile PWA behavior on HF Spaces.
- Explore i18n labels for Indian household UX.
- Benchmark app usability with elderly/parent users.
- Compare default Gradio theme vs custom ShopStack theme in walkthrough video.
