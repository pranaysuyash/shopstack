# ShopStack — Time-Series, Price Heatmaps, Travel Context, Weather, and Geo-Market Intelligence Addendum

## Purpose

ShopStack can grow beyond household inventory into a private market-intelligence and shopping-context system:

> **What should I buy, where should I buy it, when should I buy it, and is it worth travelling there today?**

This addendum covers time-series purchase memory, price heatmaps, open-source maps, store intelligence, travel-time context, weather context, visit history, embeddings, graph links, and privacy rules.

---

## Product Thesis

Most households do not remember:

- where an item was cheapest last time,
- whether a shop consistently gives better quality,
- whether today's price is unusually high,
- whether travelling to a cheaper market is worth the time,
- whether rain/heat/traffic made a market trip inconvenient,
- which day/time is better for buying fresh produce,
- whether online convenience was worth the extra cost,
- where good-quality items were bought before,
- how price, distance, time, weather, and freshness trade off.

ShopStack can turn ordinary shopping into a household commerce memory layer.

---

## Core User Questions

### Before shopping

- “Where should I buy tomatoes today?”
- “Is it worth going to the market or should I buy nearby?”
- “Which store was cheapest for detergent last month?”
- “What time did we usually get better vegetables?”
- “Was the Sunday market actually cheaper after travel time?”
- “Should I go now or later?”
- “Is the rain going to make the market trip annoying?”
- “What should I buy near the route I am already taking?”

### During shopping

- “Is this price okay?”
- “I see ₹60/kg tomato. Should I buy?”
- “Is this cheaper than last time?”
- “Which nearby shop should I check next?”
- “Do we usually buy this brand?”
- “Is this worth carrying home?”

### After shopping

- “Log this price for this shop.”
- “Mark this store as good quality.”
- “We bought tomatoes for ₹55/kg from the vendor near gate 2.”
- “It rained; mark this trip inconvenient.”
- “The market was crowded at 7 PM.”
- “This trip took 35 minutes total.”
- “Add this receipt to price history.”

---

## Data Layers

### 1. Purchase Time Series

```python
PurchasePriceObservation:
    id
    item_id
    canonical_item_name
    item_alias
    category
    brand
    quantity
    unit
    normalized_unit_price
    total_price
    currency
    store_id
    store_name
    store_type
    latitude
    longitude
    geo_precision
    purchase_timestamp
    source_type  # receipt, manual, voice, photo, live_search
    confidence
    quality_rating
    freshness_rating
    notes
```

Derived features:

- rolling average price,
- lowest observed price,
- highest observed price,
- price volatility,
- day-of-week patterns,
- time-of-day patterns,
- store-specific averages,
- item-store affinity,
- last paid price,
- acceptable price band.

---

### 2. Store Memory

```python
Store:
    id
    name
    type  # kirana, vegetable_vendor, supermarket, quick_commerce, pharmacy, online
    address_text
    latitude
    longitude
    osm_place_id
    user_label
    trust_score
    quality_score
    price_score
    freshness_score
    convenience_score
    notes
```

Store notes can include:

- good for vegetables,
- expensive but fresh,
- cheap for cleaning supplies,
- nearby but poor quality,
- usually has milk,
- avoid for fruits,
- good Sunday vendor,
- crowded in evenings,
- difficult parking,
- bad during rain.

---

### 3. Shopping Trip Context

A shopping trip is not just purchases. It includes time, route, weather, travel effort, and user outcome.

```python
ShoppingTrip:
    id
    started_at
    ended_at
    origin_label
    destination_store_ids
    destination_area
    travel_mode  # walking, bike, car, bus, metro, delivery
    estimated_travel_minutes
    actual_travel_minutes
    wait_minutes
    parking_difficulty
    crowd_level
    weather_summary
    temperature_c
    rain_intensity
    humidity
    trip_effort_score
    total_spend
    total_savings_estimate
    user_satisfaction
    notes
```

This lets ShopStack answer:

> “The market was ₹80 cheaper, but it took 45 minutes and was rainy. For this basket, nearby shop was probably better.”

---

### 4. Item-Store Edges

```python
ItemStoreEdge:
    item_id
    store_id
    avg_price
    min_price
    max_price
    last_price
    last_seen_at
    sample_count
    price_rank
    quality_rank
    freshness_rank
    convenience_adjusted_rank
    user_preference_rank
```

The useful score is not just price. It should be:

```text
value_score = price_score + quality_score + freshness_score + convenience_score - travel_effort_penalty
```

---

### 5. Geo Buckets / Heatmap Cells

For private local use, exact store coordinates can be stored locally. For public/shared traces, use coarse geospatial buckets.

```python
GeoPriceCell:
    h3_cell
    item_category
    canonical_item_name
    avg_price
    min_price
    max_price
    observation_count
    last_observed_at
    confidence
```

For privacy:

- exact home location should never be published,
- exact route history should not be shared,
- public heatmaps should use coarse cells and minimum observation counts.

---

## Heatmap Concepts

### Household Price Heatmap

A private map showing where the household has bought items and at what price.

Views:

- tomato price by location,
- milk price by store,
- cleaning supplies map,
- where we spent money this month,
- shops with best price-to-quality score,
- markets that are worth travelling to.

### Time-of-Day Heatmap

- morning vegetable prices,
- evening discount patterns,
- crowded hours,
- market closing bargains,
- freshness by time window.

### Weather-Aware Heatmap

- rain makes walking markets inconvenient,
- summer heat makes nearby stores more valuable,
- cloudy mornings may be better for fresh produce trips,
- delivery may be preferable in heavy rain.

Example response:

> “The Sunday market is usually cheaper for vegetables, but your last two rainy trips took 40+ minutes. Today, buy only urgent items nearby.”

---

## Open-Source Map Stack

Recommended stack:

- **OpenStreetMap** for base map data.
- **MapLibre GL JS** or **Leaflet** for browser map rendering.
- **H3** hex indexing for area-level aggregation.
- **SQLite/SpatiaLite** or **DuckDB spatial** for local analytics.
- **OSRM / OpenRouteService / Valhalla** as future routing engines if route-time estimation is needed.
- Local manual travel-time entry as the first reliable path.

Product UI should not feel like a GIS dashboard. It should answer shopping questions first.

---

## Travel-Time and Weather Context

### Travel Time Sources

Priority order:

1. user-stated travel time,
2. observed trip timestamps,
3. manual travel mode + distance estimate,
4. offline/open routing estimate,
5. optional connected map/routing provider.

Example tool calls:

```python
record_trip_context(store_id, started_at, ended_at, travel_mode, notes)
estimate_travel_effort(store_id, travel_mode, weather_context)
compare_price_vs_travel(item, observed_price, store_id)
```

### Weather Sources

Weather can be part of the decision layer, but it affects Off the Grid claims.

Priority order:

1. user-stated weather: “it was raining”,
2. locally cached weather snapshots,
3. optional connected weather lookup,
4. historical weather APIs for Field Notes/analysis.

Weather fields:

```python
WeatherContext:
    timestamp
    area_label
    temperature_c
    rain
    humidity
    condition
    source
```

Use weather to answer:

- “Should I go now?”
- “Was that market trip worth it?”
- “Does heat/rain affect where we buy?”
- “Should we use delivery for this basket?”

For the local-first hackathon path, weather can be manually entered or mocked with sample data. Connected weather lookup should be optional and clearly disabled in Off the Grid mode.

---

## Time-Series Analytics

Use time-series analysis for:

- price trends,
- consumption rate,
- restock prediction,
- seasonal patterns,
- store reliability,
- travel effort,
- weather-adjusted convenience,
- household spend categories,
- deal detection.

Example calculations:

```python
rolling_avg_price(item, days=30)
price_z_score(item, current_price)
days_until_stockout(item)
next_buy_prediction(item)
store_price_rank(item)
quality_adjusted_price_score(item, store)
travel_adjusted_savings(item, store)
weather_adjusted_trip_score(store, weather)
```

### Deal Detection

```text
Current tomato price: ₹70/kg
Household 30-day average: ₹52/kg
Household 90-day average: ₹48/kg
Decision: expensive today; buy only if needed.
```

### Travel-Adjusted Decision

```text
Market tomato price: ₹45/kg
Nearby tomato price: ₹58/kg
Quantity needed: 1 kg
Savings: ₹13
Extra travel: 30 minutes
Decision: not worth a special trip; buy nearby unless already going.
```

---

## Graph + Map Integration

Nodes:

- Item
- ItemLot
- Store
- MarketArea
- GeoCell
- PurchaseEvent
- PriceObservation
- ShoppingTrip
- WeatherContext
- HouseholdLocation
- ShoppingList
- UserPreference

Edges:

- `bought_at`
- `observed_at`
- `stored_in`
- `cheapest_at`
- `best_quality_at`
- `visited_during`
- `near`
- `route_to`
- `weather_affected`
- `price_observed_in`
- `worth_travelling_for`

Example:

```text
tomato → cheapest_at → Sunday Market Vendor 3
tomato → not_worth_special_trip_for → 1kg basket
detergent → cheapest_at → Supermarket
milk → usually_bought_at → Local Dairy
Sunday Market → bad_during → heavy rain
```

---

## Embeddings for Market Intelligence

Use embeddings for:

- item synonym matching,
- store note retrieval,
- similar purchase recall,
- matching receipt lines to canonical items,
- natural-language map queries,
- travel memory recall,
- “where did we buy that thing?” search.

Example aliases:

- Surf / Surf Excel / detergent powder / washing powder
- dahi / curd / yogurt
- atta / wheat flour
- dhaniya / coriander
- nimbu / lemon / lime

---

## Live Pricing and Search Integration

Live pricing should be optional and timestamped.

Priority order:

1. household price memory,
2. user-confirmed current price,
3. receipt OCR,
4. packet MRP OCR,
5. local reference price tables,
6. optional browser/search price checks,
7. optional online store snapshots.

Potential tools:

```python
search_live_price(item, location=None, store_type=None)
parse_online_store_price(page_snapshot)
compare_price_with_memory(item, observed_price, unit)
record_price_observation(item, price, unit, store, source)
```

Rules:

- Do not assume live web prices are accurate.
- Timestamp external price observations.
- Distinguish MRP, sale price, per-unit price, delivery fees, and platform fees.
- Do not scrape logged-in carts or payment flows.
- Do not auto-purchase.
- Present prices as observed/estimated, not universal.

---

## Privacy and Safety

Market intelligence can reveal household routine. Treat it as sensitive.

Rules:

- Store exact household and store coordinates locally by default.
- For shared traces, coarse-grain coordinates or remove them.
- Do not publish exact home coordinates.
- Do not publish exact route history.
- For heatmaps, aggregate by area/cell and require a minimum observation count.
- Use “near home” or “near market” labels instead of precise addresses in public datasets.
- Allow deletion of store/location memory.
- Keep weather/travel logs user-controlled.

---

## Badge Alignment

### Off the Grid

Local price memory, local maps, local SQLite/DuckDB analytics, manually entered weather/travel context, and local model inference support the local-first path.

### Sharing is Caring

Share anonymized, aggregated traces:

```json
{
  "item": "tomato",
  "observed_price": 60,
  "unit": "kg",
  "household_average_band": "45-55",
  "decision": "buy_small_quantity",
  "travel_context": "not_worth_special_trip",
  "weather_context": "rainy",
  "geo_precision": "coarse_area",
  "store_type": "vegetable_vendor"
}
```

### Field Notes

The report can include:

- price memory observations,
- travel-adjusted purchase decisions,
- weather-related shopping frictions,
- where the system was useful,
- where live pricing was unreliable,
- why household memory beats generic online price search.

---

## Agent Instructions

When implementing this layer:

1. Add price observation and shopping trip tables.
2. Add store memory and geo cell tables.
3. Add travel/weather context fields but keep them optional.
4. Add map provider interfaces.
5. Add local-first mode that works without live weather/maps/search.
6. Add connected mode stubs for live price/search/weather/routing.
7. Add privacy redaction for traces.
8. Add tests for price normalization, travel-adjusted decision logic, and trace redaction.
9. Do not make live search/weather/routing required for the core product.
10. Keep all model choices swappable through the model registry.

---

## Summary

The long-term ShopStack intelligence stack should combine:

- home inventory,
- purchase history,
- item-level price memory,
- store memory,
- location/map memory,
- trip effort,
- weather context,
- time-series analytics,
- embeddings,
- graph links,
- and voice/vision interaction.

The product should not only answer:

> “Do we have tomatoes?”

It should answer:

> “Where should we buy tomatoes today, is the current price fair, is it worth travelling there, and what did our household learn from previous trips?”
