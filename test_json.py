from shopstack.schemas.models import DecisionSet, DecisionResult
ds = DecisionSet(decisions=[DecisionResult(canonical_name="apple", display_name="Apple", action="buy")])
print(ds.model_dump_json())
