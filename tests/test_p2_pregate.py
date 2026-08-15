from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "skills" / "bootstrap-ai-native-dev-team" / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "p2"
sys.path.insert(0, str(SCRIPT_DIR))

import p2_pregate  # noqa: E402


class CanonicalizationTests(unittest.TestCase):
    def test_frozen_vector_is_reproduced_independently(self) -> None:
        raw = (FIXTURES / "private-binding-vector.json").read_bytes()
        value = p2_pregate.parse_json_bytes(raw)
        canonical = p2_pregate.canonicalize_json_bytes(raw)
        expected = (
            b'{"candidate_commit":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
            b'"created_at":"2026-08-15T00:00:00Z",'
            b'"previous_private_binding_sha256":null,'
            b'"private_anchor_commit":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",'
            b'"private_object_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",'
            b'"record_kind":"window_freeze","schema_version":"1.0",'
            b'"sequence":1,"window_id":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"}'
        )
        self.assertEqual(canonical, expected)
        self.assertEqual(len(canonical), 441)
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), "36d509352dc0deac431c2077c530feee0e6241e6bb48c7b7dff83bfb7027378f")
        expected_commitment = hashlib.sha256(
            b"ai-native-v2-private-binding\x00" + bytes(range(32)) + canonical
        ).hexdigest()
        self.assertEqual(expected_commitment, "983b1d3c160846fa67098fd6c3018c1e285510607c8e305cc84a509bee234482")
        self.assertEqual(p2_pregate.commitment_sha256(value, bytes(range(32))), expected_commitment)

    def test_reordered_keys_have_same_canonical_bytes(self) -> None:
        value = p2_pregate.parse_json_bytes((FIXTURES / "private-binding-vector.json").read_bytes())
        reordered = json.dumps(dict(reversed(list(value.items()))), ensure_ascii=True).encode("ascii")
        self.assertEqual(p2_pregate.canonicalize_json_bytes(reordered), p2_pregate.canonicalize_value(value))

    def test_noncanonical_identity_bytes_are_rejected(self) -> None:
        raw = (FIXTURES / "private-binding-vector.json").read_bytes()
        self.assertFalse(p2_pregate.is_canonical_bytes(raw))
        self.assertFalse(p2_pregate.is_canonical_bytes(p2_pregate.canonicalize_json_bytes(raw) + b"\n"))
        with self.assertRaisesRegex(p2_pregate.CanonicalizationError, "trailing_data"):
            p2_pregate.parse_json_bytes(p2_pregate.canonicalize_json_bytes(raw) + b"{}")

    def test_mandatory_negative_number_and_encoding_vectors(self) -> None:
        cases = [
            (b'{"a":1.0}', "float_forbidden"),
            (b'{"a":1e0}', "float_forbidden"),
            (b'{"a":-0}', "negative_zero_forbidden"),
            (b'{"a":9007199254740992}', "unsafe_integer"),
            (b'{"a":true,"b":1}', None),
            (b'{"a":NaN}', "nonstandard_number"),
            (b'{"a":"\xe4\xb8\xad"}', "non_ascii_or_control"),
            (b'{"a":"line\nfeed"}', "invalid_json"),
            (b'\xef\xbb\xbf{"a":1}', "bom_forbidden"),
        ]
        for raw, code in cases:
            with self.subTest(raw=raw):
                if code is None:
                    self.assertEqual(p2_pregate.parse_json_bytes(raw), {"a": True, "b": 1})
                else:
                    with self.assertRaisesRegex(p2_pregate.P2PregateError, code):
                        p2_pregate.canonicalize_json_bytes(raw)

        with self.assertRaisesRegex(p2_pregate.P2PregateError, "duplicate_key"):
            p2_pregate.parse_json_bytes((FIXTURES / "duplicate-key.json").read_bytes())

    def test_restricted_strings_and_root(self) -> None:
        for value in ({"a": "quote\""}, {"a": "slash\\"}, {"A": 1}, [1, 2]):
            with self.subTest(value=value), self.assertRaises(p2_pregate.P2PregateError):
                p2_pregate.canonicalize_value(value)


def make_binding(sequence: int, kind: str, previous: str | None = None) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "window_id": "0123456789abcdef" * 4,
        "sequence": sequence,
        "record_kind": kind,
        "private_anchor_commit": "a" * 40,
        "private_object_sha256": (f"{sequence:064x}"),
        "candidate_commit": "b" * 40,
        "previous_private_binding_sha256": previous,
        "created_at": f"2026-08-15T00:00:{sequence:02d}Z",
    }


def make_chains() -> tuple[list[dict[str, object]], list[dict[str, object]], bytes]:
    salt = bytes(range(32))
    bindings: list[dict[str, object]] = []
    previous: str | None = None
    for sequence, kind in enumerate(("window_freeze", "task_ready", "task_outcome", "window_closure"), start=1):
        binding = make_binding(sequence, kind, previous)
        bindings.append(binding)
        previous = p2_pregate.canonical_sha256(binding)
    opaque = p2_pregate.opaque_window_id(bindings[0]["window_id"], salt)
    envelopes: list[dict[str, object]] = []
    previous_envelope: str | None = None
    for binding in bindings:
        envelope = {
            "schema_version": "1.0",
            "receipt_type": "opaque_release_audit_commitment",
            "opaque_window_id": opaque,
            "sequence": binding["sequence"],
            "commitment_sha256": p2_pregate.commitment_sha256(binding, salt),
            "previous_envelope_sha256": previous_envelope,
        }
        envelopes.append(envelope)
        previous_envelope = p2_pregate.envelope_sha256(envelope)
    return bindings, envelopes, salt


class SchemaAndChainTests(unittest.TestCase):
    def test_strict_schema_rejects_unknown_fields_and_boolean_sequence(self) -> None:
        binding = make_binding(1, "window_freeze")
        binding["sequence"] = True
        with self.assertRaises(p2_pregate.SchemaValidationError):
            p2_pregate.validate_private_binding(binding)
        binding = make_binding(1, "window_freeze")
        binding["unknown"] = "leak"
        with self.assertRaises(p2_pregate.SchemaValidationError):
            p2_pregate.validate_private_binding(binding)

        leak = json.loads((FIXTURES / "public-leak.json").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(p2_pregate.SchemaValidationError, "unknown fields"):
            p2_pregate.validate_opaque_envelope(leak)

    def test_private_public_chain_and_commitments_are_integral(self) -> None:
        bindings, envelopes, salt = make_chains()
        result = p2_pregate.evaluate_pregate(
            private_bindings=bindings,
            public_envelopes=envelopes,
            window_salt=salt,
        )
        self.assertFalse(result["private_anchor_integral"])  # no trusted Git pair supplied
        self.assertTrue(result["public_chain_integral"])
        self.assertTrue(result["privacy_allowlist_passed"])
        self.assertFalse(result["eligible_for_v2_release_gate"])
        self.assertFalse(result["release_gate_invoked"])
        self.assertIn("trusted_time_missing", {issue["code"] for issue in result["issues"]})

    def test_chain_gap_and_commitment_fork_fail_closed(self) -> None:
        bindings, envelopes, salt = make_chains()
        gap = copy.deepcopy(bindings)
        gap[2]["sequence"] = 5
        gap_result = p2_pregate.evaluate_pregate(
            private_bindings=gap,
            public_envelopes=envelopes,
            window_salt=salt,
        )
        self.assertIn("private_sequence_invalid", {issue["code"] for issue in gap_result["issues"]})

        forked = copy.deepcopy(envelopes)
        forked[1]["commitment_sha256"] = "f" * 64
        fork_result = p2_pregate.evaluate_pregate(
            private_bindings=bindings,
            public_envelopes=forked,
            window_salt=salt,
        )
        self.assertIn("commitment_mismatch", {issue["code"] for issue in fork_result["issues"]})
        self.assertFalse(fork_result["public_chain_integral"])

    def test_proof_self_report_is_not_qualification(self) -> None:
        bindings, envelopes, salt = make_chains()
        proof = {
            "schema_version": "1.0",
            "proof_type": "external_time_transparency_proof",
            "provider": "example",
            "protocol_version": "v1",
            "submitted_digest_sha256": p2_pregate.envelope_sha256(envelopes[0]),
            "retained_files": [{"path": "proof.bin", "sha256": "1" * 64}],
            "verification_policy": {
                "policy_id": "unqualified",
                "tool_version": "0.0",
                "trust_root_sha256": "2" * 64,
            },
            "acquired_at": "2026-08-15T00:00:00Z",
            "verified": True,
        }
        result = p2_pregate.evaluate_pregate(
            private_bindings=bindings,
            public_envelopes=envelopes,
            proof_packages=[proof],
            window_salt=salt,
        )
        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("proof_self_reported_verification", codes)
        self.assertIn("trusted_time_missing", codes)
        self.assertFalse(result["external_receipts_integral"])
        self.assertFalse(result["pre_outcome_order_proven"])


if __name__ == "__main__":
    unittest.main()
