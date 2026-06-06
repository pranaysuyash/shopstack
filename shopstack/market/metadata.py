from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProduceMetadata:
    canonical_name: str
    shelf_life_days: int
    storage: str
    waste_risk: str
    use_priority: int
    tips: str


_PRODUCE: dict[str, ProduceMetadata] = {
    "tomato": ProduceMetadata("tomato", 7, "counter", "medium", 2, "Use in cooking within 5 days for best flavor."),
    "onion": ProduceMetadata("onion", 30, "cool_dry", "low", 5, "Store ventilated, away from potatoes."),
    "potato": ProduceMetadata("potato", 21, "cool_dark", "low", 4, "Keep away from onions to prevent sprouting."),
    "baby_potato": ProduceMetadata("baby_potato", 14, "cool_dark", "low", 4, "Use within a week for best texture."),
    "sweet_potato": ProduceMetadata("sweet_potato", 21, "cool_dark", "low", 4, "Cure 10 days at room temp for sweetness."),
    "carrot": ProduceMetadata("carrot", 14, "fridge_crisper", "medium", 3, "Remove greens before storing."),
    "cucumber": ProduceMetadata("cucumber", 7, "fridge_crisper", "high", 1, "Use within 4 days, shrivels quickly."),
    "brinjal": ProduceMetadata("brinjal", 5, "fridge_crisper", "high", 1, "Browns fast once cut — use immediately."),
    "capsicum": ProduceMetadata("capsicum", 10, "fridge_crisper", "medium", 3, "Stays crisp in a paper bag."),
    "bell_pepper": ProduceMetadata("bell_pepper", 10, "fridge_crisper", "medium", 3, "Red/yellow spoil faster than green."),
    "cauliflower": ProduceMetadata("cauliflower", 7, "fridge_crisper", "high", 2, "Brown spots = early spoilage."),
    "broccoli": ProduceMetadata("broccoli", 5, "fridge_crisper", "high", 1, "Yellow florets = over the hill."),
    "ridge_gourd": ProduceMetadata("ridge_gourd", 4, "fridge_crisper", "high", 1, "Use quickly, goes limp fast."),
    "bottle_gourd": ProduceMetadata("bottle_gourd", 5, "fridge_crisper", "high", 2, "Cut away bitter portions."),
    "bitter_gourd": ProduceMetadata("bitter_gourd", 5, "fridge_crisper", "high", 2, "Wrap loosely in paper."),
    "snake_gourd": ProduceMetadata("snake_gourd", 4, "fridge_crisper", "high", 1, "Use within 2 days of purchase."),
    "pointed_gourd": ProduceMetadata("pointed_gourd", 4, "fridge_crisper", "high", 1, "Delicate, use quickly."),
    "round_gourd": ProduceMetadata("round_gourd", 4, "fridge_crisper", "high", 1, "Best same-day."),
    "coccinia": ProduceMetadata("coccinia", 5, "fridge_crisper", "medium", 2, "Good in stir-fry."),
    "cluster_beans": ProduceMetadata("cluster_beans", 4, "fridge_crisper", "high", 1, "String before cooking."),
    "french_beans": ProduceMetadata("french_beans", 5, "fridge_crisper", "high", 2, "Snap off ends before storing."),
    "ladys_finger": ProduceMetadata("ladys_finger", 4, "fridge_crisper", "high", 1, "Keep dry, moisture causes slime."),
    "drumstick": ProduceMetadata("drumstick", 5, "fridge_crisper", "medium", 2, "Use in sambar or curry."),
    "beetroot": ProduceMetadata("beetroot", 14, "fridge_crisper", "low", 4, "Leaves edible, cook like spinach."),
    "radish": ProduceMetadata("radish", 7, "fridge_crisper", "low", 3, "Remove leaves before storing."),
    "raw_banana": ProduceMetadata("raw_banana", 5, "counter", "medium", 2, "Ripens at room temp."),
    "raw_mango": ProduceMetadata("raw_mango", 7, "counter", "medium", 2, "Use in pickles or curries."),
    "yam": ProduceMetadata("yam", 14, "cool_dark", "low", 4, "Peel deeply to remove oxalates."),
    "colocasia": ProduceMetadata("colocasia", 14, "cool_dark", "low", 4, "Boil before peeling."),
    "zucchini": ProduceMetadata("zucchini", 7, "fridge_crisper", "medium", 3, "Pat dry before storing."),
    "red_cabbage": ProduceMetadata("red_cabbage", 14, "fridge_crisper", "low", 4, "Lasts longer than green."),
    "coconut": ProduceMetadata("coconut", 30, "fridge_crisper", "low", 5, "Crack within 2 days for best water."),
    "curry_leaves": ProduceMetadata("curry_leaves", 7, "fridge_crisper", "high", 2, "Strip leaves from stem, freeze extras."),
    "coriander": ProduceMetadata("coriander", 4, "fridge_crisper", "high", 1, "Wrap in paper towel, use early."),
    "mint": ProduceMetadata("mint", 4, "fridge_crisper", "high", 1, "Like coriander, wilts fast."),
    "green_chilli": ProduceMetadata("green_chilli", 10, "fridge_crisper", "medium", 3, "Stems on until use."),
    "garlic": ProduceMetadata("garlic", 60, "cool_dry", "low", 5, "Unpeeled bulbs last months."),
    "ginger": ProduceMetadata("ginger", 30, "fridge_crisper", "low", 5, "Freeze for longer storage."),
    "sambar_onion": ProduceMetadata("sambar_onion", 21, "cool_dry", "low", 4, "Shallots, store like onions."),
    "white_onion": ProduceMetadata("white_onion", 30, "cool_dry", "low", 5, "Milder than red onion."),
}


def get_produce_metadata(canonical_name: str) -> ProduceMetadata | None:
    return _PRODUCE.get(canonical_name)


def waste_risk_ranking() -> list[str]:
    items = list(_PRODUCE.values())
    items.sort(key=lambda p: (p.use_priority, -p.shelf_life_days))
    return [p.canonical_name for p in items]


def use_first(items: list[str]) -> list[str]:
    ranked = []
    for name in items:
        meta = _PRODUCE.get(name)
        if meta:
            ranked.append((name, meta.use_priority))
        else:
            ranked.append((name, 99))
    ranked.sort(key=lambda x: x[1])
    return [name for name, _ in ranked]
