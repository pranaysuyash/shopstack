# Swiggy Instamart Fresh Vegetables extraction

Source: active browser page context and current screenshot.

## Summary
- Total cards extracted: 89
- Available cards: 45
- Sold out cards: 44
- Upgrade-tagged sold-out cards: 11
- Ad-tagged available cards: 5
- Cheapest item: Coccinia (Tondekaayi) (250 g) - ₹11, 21% OFF
- Most expensive item: Freshcon Cooked Rajma & Black Chickpeas (1 Combo) - ₹136, 20% OFF
- Highest discount: Lady's Finger (Bendekaayi) (250 g x 2) - ₹22, 26% OFF
- Lowest discount: Green Capsicum (Dappa Menasinakaayi) (2 Medium) - ₹19, 5% OFF
- Average price: ₹47.91
- Median price: ₹35
- Average discount: 20.01%

## Availability
- Available: 45
- Sold Out: 44

## Tags
- Ad: 5
- None: 73
- Upgrade: 11

## Top 10 by price
- Freshcon Cooked Rajma & Black Chickpeas (1 Combo) - ₹136, 20% OFF
- Freshcon Cooked Chickpeas & Sweetcorn (1 Combo) - ₹136, 20% OFF
- Freshcon Cooked Rajma & Sweetcorn (1 Combo) - ₹136, 20% OFF
- Freshcon Cooked Chickpeas & Black Chickpeas (1 Combo) - ₹136, 20% OFF
- Onion, Potato & Hybrid Tomato (1 Combo) - ₹122, 19% OFF
- Onion, Potato & Desi Tomato (1 Combo) - ₹114, 20% OFF
- nectr Small Green Zucchini (Chemical Free) (2 Pieces) - ₹109, 19% OFF
- nectr Small Yellow Zucchini (Chemical Free) (2 Pieces) - ₹109, 19% OFF
- Sambar Veg Combo (1 Combo) - ₹106, 20% OFF
- Pluckk Raw Mango Sliced (200 g) - ₹95, 20% OFF

## Top 10 by discount percent
- Drumstick (Nuggekaayi) (2 Pieces x 2) - ₹28, 26% OFF, discount amount ₹10
- Lady's Finger (Bendekaayi) (250 g x 2) - ₹22, 26% OFF, discount amount ₹8
- Colocasia (Arvi) (250 g x 2) - ₹36, 25% OFF, discount amount ₹12
- Broad Beans (Huralikaayi) (250 g x 2) - ₹50, 24% OFF, discount amount ₹16
- Long Purple Brinjal (Udda Badanekaayi) (250 g x 2) - ₹44, 24% OFF, discount amount ₹14
- Snake Gourd (Padavalakaayi) (2 Pieces x 2) - ₹38, 24% OFF, discount amount ₹12
- Baby Potato (Chikka Aloo Gadde) (500 g x 2) - ₹52, 23% OFF, discount amount ₹16
- Sweet Potato (Sihi Genasu) (500 g x 2) - ₹48, 22% OFF, discount amount ₹14
- Herbs Mix (1 Combo) - ₹31, 22% OFF, discount amount ₹9
- Curry Leaves & Coriander Leaves (1 Combo) - ₹21, 22% OFF, discount amount ₹6

## Master field inventory

| Field | Meaning | Type |
|---|---|---|
| card_index | Sequential card number in extracted order | integer |
| category | Page category | string |
| name | Product card title exactly as captured from page text | string |
| description | Short product description, blank where not shown | string |
| size | Pack size / quantity shown on card | string |
| delivery_time | Delivery ETA where shown | string |
| tag | Visible label such as Ad or Upgrade | string |
| availability | Available or Sold Out | enum |
| discount_percent | Displayed discount percent | integer |
| price_inr | Displayed selling price | integer |
| mrp_inr | Displayed struck-through/original price | integer |
| discount_amount_inr | MRP minus selling price | integer |
| computed_discount_percent | Computed discount from MRP and price | float |

## Size distribution

| Size | Count |
|---|---:|
| 250 g | 16 |
| 1 Combo | 14 |
| 500 g | 11 |
| 1 Piece | 11 |
| 2 Pieces | 9 |
| 250 g x 2 | 4 |
| 1 kg | 3 |
| 2 Pieces x 2 | 3 |
| 2 Medium | 2 |
| 1 Medium | 2 |
| 4 Pieces | 2 |
| 500 g x 2 | 2 |
| 1 Pack | 2 |
| 3 Pieces | 2 |
| 3 kg | 2 |
| 8 Pieces | 2 |
| 1 Small | 1 |
| 200 g | 1 |

## Exact structured extraction

| # | Name | Size | Availability | Discount | Price | MRP |
|---:|---|---|---|---:|---:|---:|
| 1 | Ridge Gourd (Herekaayi) | 2 Medium | Available | 19% | ₹33 | ₹41 |
| 2 | Cauliflower (Hoo Kosu) | 1 Medium | Available | 19% | ₹29 | ₹36 |
| 3 | Indian Tomato | 500 g | Available | 20% | ₹28 | ₹35 |
| 4 | Onion (Eerulli) | 1 kg | Available | 20% | ₹31 | ₹39 |
| 5 | Bottle Gourd ( Sorekaayi) | 1 Small | Available | 18% | ₹26 | ₹32 |
| 6 | Carrot | 500 g | Available | 19% | ₹41 | ₹51 |
| 7 | Cluster Beans (Gorikayi) | 250 g | Available | 21% | ₹18 | ₹23 |
| 8 | Lady's Finger (Bendekaayi) | 250 g x 2 | Available | 26% | ₹22 | ₹30 |
| 9 | nectr Ooty Carrot | 4 Pieces | Available | 20% | ₹51 | ₹64 |
| 10 | Onion, Potato & Desi Tomato | 1 Combo | Available | 20% | ₹114 | ₹143 |
| 11 | English Cucumber - Protected Cultivation | 500 g | Available | 20% | ₹32 | ₹40 |
| 12 | Coccinia (Tondekaayi) | 250 g | Available | 21% | ₹11 | ₹14 |
| 13 | French Beans (Bili Hurulikaayi) | 250 g | Available | 20% | ₹32 | ₹40 |
| 14 | Hybrid Tomato | 500 g | Available | 17% | ₹32 | ₹39 |
| 15 | Kateri Brinjal (Geeru Gundu Badanekaayi) | 250 g | Available | 20% | ₹16 | ₹20 |
| 16 | Sweet Potato (Sihi Genasu) | 500 g x 2 | Available | 22% | ₹48 | ₹62 |
| 17 | English Cucumber (Sowthekaayi) | 1 Pack | Available | 20% | ₹28 | ₹35 |
| 18 | Drumstick (Nuggekaayi) | 2 Pieces x 2 | Available | 26% | ₹28 | ₹38 |
| 19 | Haricot Beans (Hurulikayi) | 250 g | Available | 20% | ₹28 | ₹35 |
| 20 | Ooty Carrot | 250 g | Available | 19% | ₹29 | ₹36 |
| 21 | Broad Beans (Huralikaayi) | 250 g x 2 | Available | 24% | ₹50 | ₹66 |
| 22 | Potato (Aloo Gadde) | 1 kg | Available | 20% | ₹27 | ₹34 |
| 23 | Totapuri Raw Mango (Mavinahannu) | 1 Piece | Available | 18% | ₹13 | ₹16 |
| 24 | White Radish (Moolangi) | 2 Pieces | Available | 20% | ₹24 | ₹30 |
| 25 | Bitter Gourd (Haagalakaayi) | 1 Pack | Available | 20% | ₹34 | ₹43 |
| 26 | Beetroot | 500 g | Available | 20% | ₹27 | ₹34 |
| 27 | Onion, Potato & Hybrid Tomato | 1 Combo | Available | 19% | ₹122 | ₹151 |
| 28 | Coconut (Thenginakayi) | 1 Medium | Available | 20% | ₹44 | ₹55 |
| 29 | Cowpea Beans (Karamani) | 250 g | Available | 19% | ₹21 | ₹26 |
| 30 | Sambar Onion (Sambar Eerulli) | 250 g | Available | 19% | ₹25 | ₹31 |
| 31 | Raw Banana (Baalekaayi) | 2 Pieces | Available | 19% | ₹33 | ₹41 |
| 32 | Pointed Gourd (Parwal) | 250 g | Available | 21% | ₹30 | ₹38 |
| 33 | Green Capsicum (Dappa Menasinakaayi) | 2 Medium | Available | 5% | ₹19 | ₹20 |
| 34 | Curry Leaves & Coriander Leaves | 1 Combo | Available | 22% | ₹21 | ₹27 |
| 35 | Mint Leaves & Coriander Leaves | 1 Combo | Available | 22% | ₹21 | ₹27 |
| 36 | Hybrid Tomato & Onion | 1 Combo | Available | 19% | ₹63 | ₹78 |
| 37 | Curry Leaves & Green Chilli | 1 Combo | Available | 22% | ₹21 | ₹27 |
| 38 | Garlic & Ginger | 1 Combo | Available | 17% | ₹81 | ₹98 |
| 39 | Beetroot & Carrot | 1 Combo | Available | 20% | ₹68 | ₹85 |
| 40 | Raw Mango (Mavinakayi) | 2 Pieces | Available | 20% | ₹19 | ₹24 |
| 41 | Herbs Mix | 1 Combo | Available | 22% | ₹31 | ₹40 |
| 42 | Snake Gourd (Padavalakaayi) | 2 Pieces x 2 | Available | 24% | ₹38 | ₹50 |
| 43 | Yellow Zucchini | 1 Piece | Available | 20% | ₹38 | ₹48 |
| 44 | Forest Bitter Gourd (Kaadu Hagalakaayi) | 250 g | Available | 20% | ₹34 | ₹43 |
| 45 | Sambar Veg Combo | 1 Combo | Available | 20% | ₹106 | ₹133 |
| 46 | Snibs Snack Tomatoes(Mixed Colour) | 250 g | Sold Out | 20% | ₹92 | ₹115 |
| 47 | nectr Baby potato (Chemical Free) | 500 g | Sold Out | 20% | ₹35 | ₹44 |
| 48 | Pluckk Ozone Washed Hybrid Tomato | 500 g | Sold Out | 20% | ₹42 | ₹53 |
| 49 | Baby Potato (Chikka Aloo Gadde) | 500 g x 2 | Sold Out | 23% | ₹52 | ₹68 |
| 50 | Red Bell Pepper (Kempu Dappa Menasinakaayi) | 1 Piece | Sold Out | 20% | ₹31 | ₹39 |
| 51 | Long Purple Brinjal (Udda Badanekaayi) | 250 g x 2 | Sold Out | 24% | ₹44 | ₹58 |
| 52 | nectr Coconut (Chemical Free) | 1 Piece | Sold Out | 20% | ₹59 | ₹74 |
| 53 | nectr Small Green Zucchini (Chemical Free) | 2 Pieces | Sold Out | 19% | ₹109 | ₹136 |
| 54 | Broccoli | 1 Piece | Sold Out | 20% | ₹31 | ₹39 |
| 55 | nectr Broccoli (Chemical Free) | 1 Piece | Sold Out | 19% | ₹65 | ₹81 |
| 56 | nectr Red & Yellow Bell Peppers (Chemical Free) | 2 Pieces | Sold Out | 19% | ₹81 | ₹101 |
| 57 | nectr Small Yellow Zucchini (Chemical Free) | 2 Pieces | Sold Out | 19% | ₹109 | ₹136 |
| 58 | Pluckk Ozone Washed Green Capsicum | 250 g | Sold Out | 19% | ₹37 | ₹46 |
| 59 | Freshcon Cooked Rajma & Black Chickpeas | 1 Combo | Sold Out | 20% | ₹136 | ₹170 |
| 60 | Pluckk Raw Mango Sliced | 200 g | Sold Out | 20% | ₹95 | ₹119 |
| 61 | nectr Bottle Gourd (Chemical Free) | 1 Piece | Sold Out | 20% | ₹31 | ₹39 |
| 62 | nectr Raw Banana (Chemical Free) | 3 Pieces | Sold Out | 20% | ₹55 | ₹69 |
| 63 | nectr English Cucumber (Chemical Free) | 4 Pieces | Sold Out | 20% | ₹28 | ₹35 |
| 64 | nectr Red Cabbage (Chemical Free) | 1 Piece | Sold Out | 20% | ₹62 | ₹78 |
| 65 | nectr Green Cucumber (Chemical Free) | 3 Pieces | Sold Out | 20% | ₹46 | ₹58 |
| 66 | Cucumber | 2 Pieces x 2 | Sold Out | 20% | ₹32 | ₹40 |
| 67 | Onion -Value Pack (Eerulli) | 3 kg | Sold Out | 18% | ₹92 | ₹113 |
| 68 | Round Gourd (Dundagina Sorekaayi) | 250 g | Sold Out | 20% | ₹39 | ₹49 |
| 69 | nectr Indian Tomato (Chemical Free) | 8 Pieces | Sold Out | 19% | ₹53 | ₹66 |
| 70 | Pluckk Ozone Washed Desi Tomato | 500 g | Sold Out | 20% | ₹42 | ₹53 |
| 71 | nectr Haricot Beans (Chemical Free) | 250 g | Sold Out | 20% | ₹35 | ₹44 |
| 72 | Freshcon Cooked Chickpeas & Sweetcorn | 1 Combo | Sold Out | 20% | ₹136 | ₹170 |
| 73 | Yam Portion by Urban Harvest | 250 g | Sold Out | 20% | ₹68 | ₹85 |
| 74 | nectr Hybrid Tomato (Chemical Free) | 8 Pieces | Sold Out | 20% | ₹55 | ₹69 |
| 75 | nectr Capsicum Green (Chemical Free) | 2 Pieces | Sold Out | 20% | ₹38 | ₹48 |
| 76 | Potato (Aloo Gadde) Value Pack | 3 kg | Sold Out | 20% | ₹78 | ₹98 |
| 77 | nectr Radish | 2 Pieces | Sold Out | 19% | ₹25 | ₹31 |
| 78 | Freshcon Cooked Rajma & Sweetcorn | 1 Combo | Sold Out | 20% | ₹136 | ₹170 |
| 79 | Green Zucchini | 1 Piece | Sold Out | 20% | ₹34 | ₹43 |
| 80 | nectr Sweet Potato (Chemical Free) | 500 g | Sold Out | 20% | ₹27 | ₹34 |
| 81 | nectr Onion (Chemical Free) | 1 kg | Sold Out | 20% | ₹31 | ₹39 |
| 82 | White Onion (Bili Eerulli) | 500 g | Sold Out | 20% | ₹54 | ₹68 |
| 83 | Yellow Bell Pepper (Haladi Dappa Menasinakaayi) | 1 Piece | Sold Out | 20% | ₹31 | ₹39 |
| 84 | Red & Yellow Bell Pepper - Protected Cultivation | 2 Pieces | Sold Out | 20% | ₹62 | ₹78 |
| 85 | Colocasia (Arvi) | 250 g x 2 | Sold Out | 25% | ₹36 | ₹48 |
| 86 | Freshcon Cooked Chickpeas & Black Chickpeas | 1 Combo | Sold Out | 20% | ₹136 | ₹170 |
| 87 | nectr Ridge Gourd (Chemical Free) | 1 Piece | Sold Out | 19% | ₹21 | ₹26 |
| 88 | nectr Kateri Brinjal (Chemical Free) | 250 g | Sold Out | 20% | ₹20 | ₹25 |
| 89 | Chandramukhi Potato (Aloo Gadde) | 500 g | Sold Out | 20% | ₹56 | ₹70 |