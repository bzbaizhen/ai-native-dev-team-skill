"""Offline routing checks; availability fixtures are not provider receipts."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import resolve_route as router
try:
    import jsonschema
except ImportError:
    jsonschema = None

class Gpt6Routing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.request = dict(router_api_version='route/v2', request_id='offline-test',
            route_slot='control-plane', writer_route_slot=None, profile_id='gpt6',
            explicit_profile_selection=True, explicit_high_volume_selection=False,
            availability={f'openai/{m}':'available' for m in ['gpt-6-astra','gpt-6-luna','gpt-6.1-sol']},
            route_failure_evidence={}, risk_level=None, writer_identity=None, candidate_id=None)

    def resolve(self, req):
        result=router.resolve_route(req,cwd=self.tmp.name)
        self.assertEqual(result['enforcement_status'],'not-executed')
        if jsonschema:
            jsonschema.validate(req,json.loads((ROOT/'assets/route-request.v2.schema.json').read_text()))
            jsonschema.validate(result,json.loads((ROOT/'assets/route-decision.v2.schema.json').read_text()))
        return result

    def assurance(self, risk):
        r=copy.deepcopy(self.request)
        r.update(route_slot='validator.assurance',writer_route_slot='writer.c3',risk_level=risk,
            writer_identity={'provider':'openai','runtime_provider':'custom','model':'gpt-6.1-sol'},candidate_id='candidate-1')
        return r

    def test_five_writer_and_control_routes(self):
        cases=[('control-plane','gpt-6-astra','medium'),('writer.c0-batch','gpt-6-luna','max'),
               ('writer.c1','gpt-6.1-sol','low'),('writer.c2','gpt-6.1-sol','medium'),('writer.c3','gpt-6.1-sol','high')]
        for slot,model,reason in cases:
            with self.subTest(slot=slot):
                r=copy.deepcopy(self.request); r['route_slot']=slot; d=self.resolve(r)
                self.assertEqual(d['decision_status'],'selected')
                self.assertEqual((d['selected_routes'][0]['model'],d['selected_routes'][0]['reasoning']),(model,reason))

    def test_all_risks_single_and_same_model_reported(self):
        for risk,reason in [('R1','low'),('R2','medium'),('R3','high')]:
            with self.subTest(risk=risk):
                d=self.resolve(self.assurance(risk))
                self.assertEqual(d['validation_mode'],'single')
                self.assertEqual(len(d['selected_routes']),1)
                self.assertEqual(d['selected_routes'][0]['reasoning'],reason)
                self.assertTrue(d['same_model_as_writer'])

    def test_unknown_and_unavailable_do_not_select(self):
        for risk in ['R1','R2','R3']:
            for state,expected in [('unknown','unknown'),('unavailable','blocked')]:
                for evidence in [[],['quota-exhaustion']]:
                    with self.subTest(risk=risk,state=state,evidence=evidence):
                        r=self.assurance(risk); r['availability']['openai/gpt-6.1-sol']=state
                        r['route_failure_evidence']={'openai/gpt-6.1-sol':evidence}
                        d=self.resolve(r)
                        self.assertEqual(d['decision_status'],expected)
                        self.assertEqual(d['selected_routes'],[])

    def test_explicit_selection_and_version_guards(self):
        r=copy.deepcopy(self.request); r['explicit_profile_selection']=False
        with self.assertRaises(ValueError): self.resolve(r)
        r=copy.deepcopy(self.request); r['router_api_version']='route/v1'
        with self.assertRaises(ValueError): self.resolve(r)

    def test_old_profile_rejected(self):
        self.assertEqual(router.PROFILE_IDS,('gpt6',))
        self.assertFalse((ROOT/'assets/profiles/gpt5.6.json').exists())
        with self.assertRaisesRegex(ValueError,'retired'): router.load_profile('gpt5.6')
        r=copy.deepcopy(self.request); r['profile_id']='gpt5.6'
        with self.assertRaisesRegex(ValueError,'retired'): self.resolve(r)

    def test_old_project_config_rejected(self):
        p=Path(self.tmp.name)/'.ai-native'; p.mkdir()
        c=json.loads((ROOT/'assets/model-router-config.example.json').read_text()); c['active_profile']='gpt5.6'
        (p/'model-router.json').write_text(json.dumps(c))
        with self.assertRaisesRegex(ValueError,'retired'): self.resolve(self.request)

    def test_removed_external_routes_cannot_be_selected(self):
        p=router.load_profile('gpt6')
        serialized=json.dumps(p).lower()
        self.assertNotIn('glm',serialized)
        self.assertNotIn('deepseek',serialized)
        self.assertNotIn('writer.high-volume-deterministic',p['slots'])
        for explicit in [False, True]:
            r=copy.deepcopy(self.request)
            r.update(route_slot='writer.high-volume-deterministic',explicit_high_volume_selection=explicit)
            r['availability'].update({'zai/glm-5.3-flash':'available','deepseek/deepseek-v4-flash':'available'})
            with self.assertRaises(ValueError): self.resolve(r)
            if jsonschema:
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.validate(r,json.loads((ROOT/'assets/route-request.v2.schema.json').read_text()))

    def test_retired_sol_models_cannot_be_selected(self):
        catalog = router.load_catalog()['providers']['openai']['models']
        for model in ['gpt-5.6-sol', 'gpt-6-sol']:
            self.assertNotIn(model, catalog)
            p = router.load_profile('gpt6')
            p['slots']['writer.c3']['primary']['model'] = model
            with self.assertRaises(ValueError): router.validate_profile_v2(p)

    def test_profile_drift_rejected(self):
        p=router.load_profile('gpt6')
        p['slots']['validator.assurance']['routes_by_risk']['R3'].append(copy.deepcopy(p['slots']['validator.assurance']['routes_by_risk']['R3'][0]))
        with self.assertRaises(ValueError): router.validate_profile_v2(p)

if __name__=='__main__': unittest.main()
