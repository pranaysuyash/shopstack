"""Seed demo inventory data for developer walkthroughs and testing.

This module lives in shopstack.data so the screen module (inventory.py)
doesn't carry a large static data array in its module body.
"""

DEMO_SEED_INVENTORY = [
    {
        "canonical_name": "milk",
        "display_name": "Milk",
        "quantity": 2.0,
        "unit": "liter",
        "price": 74.0,
        "store": "local milk booth",
        "location": "fridge",
        "category": "dairy",
        "expiry": 7,
    },
    {
        "canonical_name": "rice",
        "display_name": "Basmati Rice",
        "quantity": 5.0,
        "unit": "kg",
        "price": 410.0,
        "store": "Big Bazaar",
        "location": "pantry",
        "category": "grains",
    },
    {
        "canonical_name": "eggs",
        "display_name": "Eggs",
        "quantity": 12.0,
        "unit": "pieces",
        "price": 96.0,
        "store": "Morning Eggstop",
        "location": "fridge_top",
        "category": "protein",
    },
    {
        "canonical_name": "onion",
        "display_name": "Onion",
        "quantity": 1.5,
        "unit": "kg",
        "price": 32.0,
        "store": "Local Vendor",
        "location": "pantry_mid",
        "category": "vegetable",
    },
    {
        "canonical_name": "toothpaste",
        "display_name": "Toothpaste",
        "quantity": 1.0,
        "unit": "unit",
        "price": 129.0,
        "store": "Apna Store",
        "location": "bathroom_cabinet",
        "category": "personal care",
    },
    {
        "canonical_name": "olive oil",
        "display_name": "Olive Oil",
        "quantity": 1.0,
        "unit": "L",
        "price": 690.0,
        "store": "Supermart",
        "location": "pantry_mid",
        "category": "cooking",
    },
    {
        "canonical_name": "curd",
        "display_name": "Curd",
        "quantity": 0.5,
        "unit": "kg",
        "price": 48.0,
        "store": "Fresh Dairy",
        "location": "fridge",
        "category": "dairy",
    },
]
