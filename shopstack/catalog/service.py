from typing import Dict, List, Optional
from shopstack.catalog.models import ProductCatalogEntry

class CatalogService:
    def __init__(self):
        self._catalog: Dict[str, ProductCatalogEntry] = {}
        self._alias_map: Dict[str, str] = {}
        
    def add_entry(self, entry: ProductCatalogEntry):
        self._catalog[entry.canonical_id] = entry
        self._alias_map[entry.canonical_name.lower()] = entry.canonical_id
        for alias in entry.aliases:
            self._alias_map[alias.lower()] = entry.canonical_id
            
    def get_by_canonical_id(self, canonical_id: str) -> Optional[ProductCatalogEntry]:
        return self._catalog.get(canonical_id)
        
    def get_by_name(self, name: str) -> Optional[ProductCatalogEntry]:
        canonical_id = self._alias_map.get(name.lower().strip())
        if canonical_id:
            return self._catalog.get(canonical_id)
        return None
