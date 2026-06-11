from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

class WasteRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class ProductCategory(str, Enum):
    VEGETABLES = "vegetables"
    FRUITS = "fruits"
    DAIRY = "dairy"
    MEAT = "meat"
    GROCERY = "grocery"
    HERBS_AND_SPICES = "herbs_and_spices"
    BEVERAGES = "beverages"
    SNACKS = "snacks"
    OTHER = "other"

@dataclass
class ProductCatalogEntry:
    canonical_id: str
    canonical_name: str
    aliases: List[str] = field(default_factory=list)
    category: ProductCategory = ProductCategory.OTHER
    shelf_life_days: Optional[int] = None
    waste_risk: WasteRisk = WasteRisk.MEDIUM
    storage_hints: str = ""
    unit_preference: str = "pieces"
    variant_family: str = ""
    premium_claims: List[str] = field(default_factory=list)
    substitute_groups: List[str] = field(default_factory=list)
