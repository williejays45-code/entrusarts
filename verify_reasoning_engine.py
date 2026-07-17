from era.weight_registry import seed_default_ths_weights
from era.reasoning_engine import ERAReasoningEngine
seed_default_ths_weights("eri_persistence.db")
engine = ERAReasoningEngine("eri_persistence.db")
result = engine.evaluate(
    engine="ERA",
    metric="THS",
    base_score=95.55,
)
print("ENGINE:", result.engine)
print("METRIC:", result.metric)
print("BASE_SCORE:", result.base_score)
print("ADJUSTED_SCORE:", result.adjusted_score)
print("CONFIDENCE:", result.confidence)
print("ACTION:", result.recommended_action)
print("PERSISTED:", result.persisted)
print("REASON:", result.reason)
