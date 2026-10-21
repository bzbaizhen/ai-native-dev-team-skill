"""Discover the bundled current-profile regression suite from the release suite."""
import jsonschema  # Test dependency is mandatory: schema verification may not silently disappear.
import importlib.util
from pathlib import Path

def load_tests(loader, tests, pattern):
    path = Path(__file__).resolve().parents[1] / "skills/ai-native-model-router/tests/test_gpt6.py"
    spec = importlib.util.spec_from_file_location("bundled_gpt6_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tests.addTests(loader.loadTestsFromModule(module))
    return tests

class CurrentSchemaNegativeTests(__import__("unittest").TestCase):
    def test_all_risks_reject_wrong_cardinality_mode_and_extra_fields(self):
        import copy
        import json
        root = Path(__file__).resolve().parents[1] / "skills/ai-native-model-router"
        schema = json.loads((root / "assets/route-decision.v2.schema.json").read_text())
        import resolve_route as router
        for risk in ("R1", "R2", "R3"):
            request = dict(router_api_version="route/v2", request_id="schema-negative", route_slot="validator.assurance", writer_route_slot="writer.c1", profile_id="gpt6", explicit_profile_selection=True, explicit_high_volume_selection=False, availability={"openai/gpt-6.1-sol":"available"}, route_failure_evidence={}, risk_level=risk, writer_identity={"provider":"openai", "runtime_provider":"custom", "model":"gpt-6.1-sol"}, candidate_id="candidate-schema")
            decision = router.resolve_route(request)
            jsonschema.validate(decision, schema)
            for mutation in (lambda d: d.update(selected_routes=[]), lambda d: d["selected_routes"].append(copy.deepcopy(d["selected_routes"][0])), lambda d: d.update(validation_mode="dual"), lambda d: d.update(enforcement_status="executed"), lambda d: d.update(extra=True)):
                candidate = copy.deepcopy(decision)
                mutation(candidate)
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.validate(candidate, schema)
            for state in ("blocked", "unknown"):
                candidate = copy.deepcopy(decision)
                candidate["decision_status"] = state
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.validate(candidate, schema)
