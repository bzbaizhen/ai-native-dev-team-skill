from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch


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
        self.assertFalse(result["public_chain_integral"])
        self.assertTrue(result["privacy_allowlist_passed"])
        self.assertFalse(result["eligible_for_v2_release_gate"])
        self.assertFalse(result["release_gate_invoked"])
        self.assertIn("trusted_time_missing", {issue["code"] for issue in result["issues"]})
        self.assertFalse(result["public_chain_integral"])
        self.assertIn("public_anchor_unproven", {issue["code"] for issue in result["issues"]})

    def test_reversed_caller_order_is_rejected_without_sorting(self) -> None:
        bindings, envelopes, salt = make_chains()
        result = p2_pregate.evaluate_pregate(
            private_bindings=list(reversed(bindings)),
            public_envelopes=list(reversed(envelopes)),
            window_salt=salt,
        )
        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("private_sequence_invalid", codes)
        self.assertIn("public_sequence_invalid", codes)
        self.assertFalse(result["public_chain_integral"])

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

    def test_pending_ready_prefix_blocks_orphan_outcome_and_closure(self) -> None:
        bindings, envelopes, salt = make_chains()
        orphan = copy.deepcopy(bindings)
        orphan[1]["record_kind"] = "task_outcome"
        orphan_result = p2_pregate.evaluate_pregate(
            private_bindings=orphan,
            public_envelopes=envelopes,
            window_salt=salt,
        )
        self.assertIn("task_outcome_without_ready", {issue["code"] for issue in orphan_result["issues"]})

        pending = copy.deepcopy(bindings)
        pending[2]["record_kind"] = "task_ready"
        pending_result = p2_pregate.evaluate_pregate(
            private_bindings=pending,
            public_envelopes=envelopes,
            window_salt=salt,
        )
        pending_codes = {issue["code"] for issue in pending_result["issues"]}
        self.assertIn("pending_task_ready_at_closure", pending_codes)
        self.assertFalse(pending_result["private_anchor_integral"])

    def test_recovery_declaration_and_caller_digests_remain_unproven(self) -> None:
        bindings, envelopes, salt = make_chains()
        recovery = {
            "restore_verified": True,
            "source_bundle_sha256": "1" * 64,
            "restored_bundle_sha256": "1" * 64,
        }
        result = p2_pregate.evaluate_pregate(
            private_bindings=bindings,
            public_envelopes=envelopes,
            window_salt=salt,
            recovery_inventory=recovery,
        )
        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("recovery_unproven", codes)
        self.assertFalse(result["recovery_demonstrated"])

    def test_manifest_is_required_and_alignment_is_never_inferred(self) -> None:
        bindings, envelopes, salt = make_chains()
        missing = p2_pregate.evaluate_pregate(
            private_bindings=bindings,
            public_envelopes=envelopes,
            window_salt=salt,
        )
        missing_codes = {issue["code"] for issue in missing["issues"]}
        self.assertIn("manifest_missing", missing_codes)
        self.assertIn("manifest_alignment_unproven", missing_codes)

        arbitrary = p2_pregate.evaluate_pregate(
            private_bindings=bindings,
            public_envelopes=envelopes,
            window_salt=salt,
            final_manifest={"not_a_manifest": True},
        )
        arbitrary_codes = {issue["code"] for issue in arbitrary["issues"]}
        self.assertIn("manifest_invalid", arbitrary_codes)
        self.assertIn("manifest_alignment_unproven", arbitrary_codes)
        self.assertFalse(arbitrary["manifest_alignment_proven"])

        valid_shape = {
            "schema_version": "2.0",
            "candidate_version": "candidate",
            "candidate_commit": "b" * 40,
            "candidate_frozen_at": "2026-08-15T00:00:00Z",
            "registry_closed_at": "2026-08-16T00:00:00Z",
            "source_registry": "registry.json",
            "source_registry_sha256": "1" * 64,
            "required_comparable_tasks": 5,
            "sources": [{"source_id": "source-1"}],
            "trials": [{"task_id": "task-1", "disposition": "accepted"}],
        }
        aligned = p2_pregate.evaluate_pregate(
            private_bindings=bindings,
            public_envelopes=envelopes,
            window_salt=salt,
            final_manifest=valid_shape,
        )
        aligned_codes = {issue["code"] for issue in aligned["issues"]}
        self.assertNotIn("manifest_invalid", aligned_codes)
        self.assertIn("manifest_alignment_unproven", aligned_codes)
        self.assertFalse(aligned["manifest_alignment_proven"])

    def test_private_anchor_endpoints_and_event_anchors_are_required(self) -> None:
        bindings, envelopes, salt = make_chains()
        missing_anchor = copy.deepcopy(bindings)
        missing_anchor[1]["private_anchor_commit"] = None
        result = p2_pregate.evaluate_pregate(
            private_bindings=missing_anchor,
            public_envelopes=envelopes,
            window_salt=salt,
            private_freeze_commit="a" * 40,
            private_head_commit="b" * 40,
        )
        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("private_anchor_missing", codes)
        self.assertFalse(result["private_anchor_integral"])

    def test_public_git_merge_history_is_rejected_and_not_integral(self) -> None:
        issues: list[dict[str, str]] = []

        def fake_run(args: list[str], **_kwargs: object) -> SimpleNamespace:
            if "cat-file" in args:
                return SimpleNamespace(returncode=0, stdout="")
            if "merge-base" in args:
                return SimpleNamespace(returncode=0, stdout="")
            if "rev-list" in args:
                return SimpleNamespace(returncode=0, stdout="deadbeef\n")
            raise AssertionError(args)

        with patch.object(p2_pregate.subprocess, "run", side_effect=fake_run):
            verified = p2_pregate._verify_git_chain(
                SCRIPT_DIR,
                "a" * 40,
                "b" * 40,
                issues,
                "public",
            )
        self.assertFalse(verified)
        self.assertIn("public_anchor_nonlinear", {issue["code"] for issue in issues})

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

    def test_protocol_version_and_retained_paths_are_strict(self) -> None:
        base = {
            "schema_version": "1.0",
            "proof_type": "external_time_transparency_proof",
            "provider": "example",
            "protocol_version": "v1",
            "submitted_digest_sha256": "0" * 64,
            "retained_files": [{"path": "proof.bin", "sha256": "1" * 64}],
            "verification_policy": {
                "policy_id": "policy",
                "tool_version": "tool",
                "trust_root_sha256": "2" * 64,
            },
            "acquired_at": "2026-08-15T00:00:00Z",
        }
        too_long = copy.deepcopy(base)
        too_long["protocol_version"] = "v" * 65
        with self.assertRaises(p2_pregate.SchemaValidationError):
            p2_pregate.validate_external_proof_package(too_long)
        for path in (".", "..", "./proof.bin", "a/../proof.bin", "/proof.bin", "a//proof.bin", "a/./proof.bin"):
            with self.subTest(path=path):
                invalid = copy.deepcopy(base)
                invalid["retained_files"][0]["path"] = path
                with self.assertRaises(p2_pregate.SchemaValidationError):
                    p2_pregate.validate_external_proof_package(invalid)


if __name__ == "__main__":
    unittest.main()
