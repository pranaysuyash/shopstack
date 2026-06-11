from typing import Dict, List, Optional, Tuple
from shopstack.market.schema import NormalizedMarketRecord
from shopstack.catalog.models import WasteRisk
from shopstack.catalog.service import CatalogService

class ComboEvaluator:
    def __init__(self, catalog_service: CatalogService):
        self.catalog = catalog_service

    def evaluate_combo(
        self,
        combo_record: NormalizedMarketRecord,
        individual_options: Dict[str, NormalizedMarketRecord],
        user_inventory: List[str]
    ) -> Dict[str, any]:
        """
        Evaluates a combo against buying individual items.
        Returns a dictionary with savings, waste risk, and recommendation.
        """
        if not combo_record.is_combo:
            return {"error": "Not a combo record"}

        components = combo_record.component_names
        if not components:
            return {"error": "No components detected in combo"}

        total_individual_price = 0.0
        missing_individual_price = False
        component_waste_risks = []
        already_owned = []

        for comp in components:
            # Calculate waste risk if user already owns it
            if comp in user_inventory:
                already_owned.append(comp)
                entry = self.catalog.get_by_canonical_id(comp)
                if entry:
                    component_waste_risks.append(entry.waste_risk.value)
                else:
                    component_waste_risks.append(WasteRisk.MEDIUM.value)

            # Sum individual prices
            if comp in individual_options and individual_options[comp].is_available:
                total_individual_price += individual_options[comp].price_inr
            else:
                missing_individual_price = True

        # Savings calculation
        savings = 0.0
        combo_value_ratio = 1.0
        if not missing_individual_price and total_individual_price > 0:
            savings = total_individual_price - combo_record.price_inr
            combo_value_ratio = combo_record.price_inr / total_individual_price

        # Waste risk calculation
        overall_waste_risk = WasteRisk.LOW.value
        if already_owned:
            if WasteRisk.HIGH.value in component_waste_risks:
                overall_waste_risk = WasteRisk.HIGH.value
            else:
                overall_waste_risk = WasteRisk.MEDIUM.value

        recommendation = "neutral"
        if overall_waste_risk == WasteRisk.HIGH.value:
            recommendation = "skip_due_to_waste_risk"
        elif savings > 0:
            recommendation = "buy_combo"
        elif not missing_individual_price and savings < 0:
            recommendation = "buy_individuals"

        return {
            "components": components,
            "total_individual_price": total_individual_price if not missing_individual_price else None,
            "combo_price": combo_record.price_inr,
            "savings": savings if not missing_individual_price else None,
            "value_ratio": combo_value_ratio if not missing_individual_price else None,
            "already_owned_components": already_owned,
            "waste_risk": overall_waste_risk,
            "recommendation": recommendation
        }
