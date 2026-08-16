from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
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


def make_manifest(bindings: list[dict[str, object]], *, disposition: str = "accepted") -> dict[str, object]:
    candidate = str(bindings[0]["candidate_commit"])
    trial: dict[str, object] = {
        "trial_id": "TRIAL-001",
        "registration_sequence": 1,
        "source_id": "SOURCE-001",
        "task_id": "TASK-001",
        "skill_candidate_commit": candidate,
        "request_evidence": "request.json",
        "request_evidence_sha256": bindings[1]["private_object_sha256"],
        "v1_baseline_id": "V1-BASELINE" if disposition == "accepted" else None,
        "v1_baseline_stratum": "C1|R1|single-worker" if disposition == "accepted" else None,
        "comparable": disposition == "accepted",
        "disposition": disposition,
        "genuine_request": True,
        "synthetic": False,
        "critical_defect_escape": False,
        "material_quality_regression": False,
        "scope_violation": False,
        "write_conflict": False,
        "recovery_executable": True,
        "acceptance_evidence": "outcome.json",
        "acceptance_evidence_sha256": bindings[2]["private_object_sha256"],
        "notes": [],
    }
    if disposition == "accepted":
        trial.update(
            {
                "candidate_commit": candidate,
                "stable_commit": candidate,
                "integration_proof": {"mode": "same_commit"},
            }
        )
    else:
        trial["exclusion_reason"] = "not comparable in this local proof vector"
    return {
        "schema_version": "2.0",
        "candidate_version": "v2.0.0-rc.5",
        "candidate_commit": candidate,
        "candidate_frozen_at": "2026-08-15T00:00:00Z",
        "registry_closed_at": "2026-08-15T01:00:00Z",
        "source_registry": "registry.json",
        "source_registry_sha256": "1" * 64,
        "required_comparable_tasks": 5,
        "sources": [
            {
                "source_id": "SOURCE-001",
                "project_alias": "project-a",
                "project_evidence_id": "project-a-evidence",
                "project_repo": "project-a",
                "stable_branch": "main",
                "ledger": "ledger.jsonl",
                "ledger_prefix_bytes": 0,
                "ledger_prefix_sha256": "2" * 64,
                "ledger_sha256": "3" * 64,
            }
        ],
        "trials": [trial],
    }


def make_alignment(bindings: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "candidate_commit": bindings[0]["candidate_commit"],
        "tasks": [
            {
                "task_id": "TASK-001",
                "ready_binding_sequence": 2,
                "outcome_binding_sequence": 3,
            }
        ],
    }


def git_run(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    return result.stdout.strip()


def make_public_git_repo(envelopes: list[dict[str, object]]) -> tuple[tempfile.TemporaryDirectory[str], Path, str, str, dict[str, object]]:
    temp = tempfile.TemporaryDirectory(prefix="p2-public-")
    repo = Path(temp.name)
    git_run(repo, "init", "-b", "main")
    git_run(repo, "config", "user.email", "p2@example.invalid")
    git_run(repo, "config", "user.name", "P2 Test")
    git_run(repo, "commit", "--allow-empty", "-m", "freeze")
    freeze = git_run(repo, "rev-parse", "HEAD")
    receipts: list[dict[str, object]] = []
    for index, envelope in enumerate(envelopes, start=1):
        relative = Path("receipts") / f"{index:04d}.json"
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(p2_pregate.canonicalize_value(envelope))
        git_run(repo, "add", relative.as_posix())
        git_run(repo, "commit", "-m", f"receipt {index}")
        commit = git_run(repo, "rev-parse", "HEAD")
        receipts.append(
            {
                "sequence": index,
                "commit": commit,
                "path": relative.as_posix(),
                "envelope_sha256": p2_pregate.envelope_sha256(envelope),
            }
        )
    head = git_run(repo, "rev-parse", "HEAD")
    return temp, repo, freeze, head, {"schema_version": "1.0", "public_ref": "refs/heads/main", "freeze_commit": freeze, "head_commit": head, "receipts": receipts}


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

        valid_shape = make_manifest(bindings)
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
                return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
            if "merge-base" in args:
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if "rev-list" in args:
                return SimpleNamespace(returncode=0, stdout="deadbeef\n", stderr="")
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


class StrictCompletionTests(unittest.TestCase):
    def test_public_anchor_manifest_positive_path_is_reachable(self) -> None:
        bindings, envelopes, salt = make_chains()
        temp, repo, freeze, head, anchor_manifest = make_public_git_repo(envelopes)
        try:
            result = p2_pregate.evaluate_pregate(
                private_bindings=bindings,
                public_envelopes=envelopes,
                window_salt=salt,
                public_anchor_repo=repo,
                public_freeze_commit=freeze,
                public_head_commit=head,
                public_anchor_manifest=anchor_manifest,
            )
        finally:
            temp.cleanup()
        self.assertTrue(result["public_content_mapping_proven"])
        self.assertTrue(result["public_chain_integral"])
        self.assertFalse(result["public_control_proven"])
        self.assertFalse(result["external_receipts_integral"])
        self.assertFalse(result["eligible_for_v2_release_gate"])

    def test_public_anchor_manifest_rejects_unsafe_ref_and_reordered_mapping(self) -> None:
        bindings, envelopes, salt = make_chains()
        temp, repo, freeze, head, anchor_manifest = make_public_git_repo(envelopes)
        try:
            unsafe = copy.deepcopy(anchor_manifest)
            unsafe["public_ref"] = "refs/heads/main^"
            unsafe_result = p2_pregate.evaluate_pregate(
                private_bindings=bindings,
                public_envelopes=envelopes,
                window_salt=salt,
                public_anchor_repo=repo,
                public_freeze_commit=freeze,
                public_head_commit=head,
                public_anchor_manifest=unsafe,
            )
            reordered = copy.deepcopy(anchor_manifest)
            reordered["receipts"] = list(reversed(reordered["receipts"]))
            reordered_result = p2_pregate.evaluate_pregate(
                private_bindings=bindings,
                public_envelopes=envelopes,
                window_salt=salt,
                public_anchor_repo=repo,
                public_freeze_commit=freeze,
                public_head_commit=head,
                public_anchor_manifest=reordered,
            )
        finally:
            temp.cleanup()
        self.assertFalse(unsafe_result["public_content_mapping_proven"])
        self.assertIn("public_anchor_manifest_invalid", {issue["code"] for issue in unsafe_result["issues"]})
        self.assertFalse(reordered_result["public_content_mapping_proven"])
        self.assertIn("public_commit_sequence_mismatch", {issue["code"] for issue in reordered_result["issues"]})

    def test_public_mapping_requires_caller_order_and_complete_input(self) -> None:
        bindings, envelopes, salt = make_chains()
        temp, repo, freeze, head, anchor_manifest = make_public_git_repo(envelopes)
        try:
            reversed_result = p2_pregate.evaluate_pregate(
                private_bindings=bindings,
                public_envelopes=list(reversed(envelopes)),
                window_salt=salt,
                public_anchor_repo=repo,
                public_freeze_commit=freeze,
                public_head_commit=head,
                public_anchor_manifest=anchor_manifest,
            )
            with_extra = copy.deepcopy(envelopes)
            with_extra.append({"schema_version": "1.0"})
            extra_result = p2_pregate.evaluate_pregate(
                private_bindings=bindings,
                public_envelopes=with_extra,
                window_salt=salt,
                public_anchor_repo=repo,
                public_freeze_commit=freeze,
                public_head_commit=head,
                public_anchor_manifest=anchor_manifest,
            )
        finally:
            temp.cleanup()
        self.assertFalse(reversed_result["public_content_mapping_proven"])
        self.assertIn("public_mapping_chain_unproven", {issue["code"] for issue in reversed_result["issues"]})
        self.assertFalse(extra_result["public_content_mapping_proven"])
        self.assertIn("public_input_incomplete", {issue["code"] for issue in extra_result["issues"]})

    def test_public_mapping_requires_exact_supplied_file_bytes(self) -> None:
        bindings, envelopes, salt = make_chains()
        temp, repo, freeze, head, anchor_manifest = make_public_git_repo(envelopes)
        supplied = repo / "supplied-public"
        supplied.mkdir()
        try:
            for index, envelope in enumerate(envelopes, start=1):
                (supplied / f"{index:04d}.json").write_bytes(p2_pregate.canonicalize_value(envelope) + b"\n")
            result = p2_pregate.evaluate_pregate(
                private_bindings=bindings,
                public_envelopes=supplied,
                window_salt=salt,
                public_anchor_repo=repo,
                public_freeze_commit=freeze,
                public_head_commit=head,
                public_anchor_manifest=anchor_manifest,
            )
        finally:
            temp.cleanup()
        codes = {issue["code"] for issue in result["issues"]}
        self.assertFalse(result["public_content_mapping_proven"])
        self.assertFalse(result["public_chain_integral"])
        self.assertIn("public_envelope_noncanonical", codes)
        self.assertIn("public_input_incomplete", codes)

    def test_public_anchor_manifest_rejects_noncanonical_and_multi_file_commits(self) -> None:
        bindings, envelopes, salt = make_chains()
        temp, repo, freeze, head, anchor_manifest = make_public_git_repo(envelopes)
        try:
            last = anchor_manifest["receipts"][-1]
            target = repo / str(last["path"])
            target.write_text(json.dumps(envelopes[-1], indent=2), encoding="utf-8", newline="\n")
            git_run(repo, "add", str(last["path"]))
            git_run(repo, "commit", "--amend", "--no-edit")
            new_head = git_run(repo, "rev-parse", "HEAD")
            anchor_manifest["head_commit"] = new_head
            last["commit"] = new_head
            noncanonical_result = p2_pregate.evaluate_pregate(
                private_bindings=bindings,
                public_envelopes=envelopes,
                window_salt=salt,
                public_anchor_repo=repo,
                public_freeze_commit=freeze,
                public_head_commit=new_head,
                public_anchor_manifest=anchor_manifest,
            )
        finally:
            temp.cleanup()
        self.assertFalse(noncanonical_result["public_content_mapping_proven"])
        self.assertIn("public_envelope_noncanonical", {issue["code"] for issue in noncanonical_result["issues"]})

    def test_manifest_alignment_positive_for_all_dispositions(self) -> None:
        for disposition in ("accepted", "in_progress", "blocked", "cancelled", "rejected"):
            with self.subTest(disposition=disposition):
                bindings, envelopes, salt = make_chains()
                result = p2_pregate.evaluate_pregate(
                    private_bindings=bindings,
                    public_envelopes=envelopes,
                    window_salt=salt,
                    final_manifest=make_manifest(bindings, disposition=disposition),
                    manifest_alignment_index=make_alignment(bindings),
                )
                self.assertTrue(result["manifest_alignment_proven"])
                self.assertFalse(result["eligible_for_v2_release_gate"])

    def test_manifest_alignment_rejects_missing_duplicate_and_digest_mismatch(self) -> None:
        bindings, envelopes, salt = make_chains()
        manifest = make_manifest(bindings)
        missing = p2_pregate.evaluate_pregate(
            private_bindings=bindings,
            public_envelopes=envelopes,
            window_salt=salt,
            final_manifest=manifest,
            manifest_alignment_index={
                "schema_version": "1.0",
                "candidate_commit": bindings[0]["candidate_commit"],
                "tasks": [],
            },
        )
        duplicate = make_alignment(bindings)
        duplicate["tasks"].append(copy.deepcopy(duplicate["tasks"][0]))
        duplicate_result = p2_pregate.evaluate_pregate(
            private_bindings=bindings,
            public_envelopes=envelopes,
            window_salt=salt,
            final_manifest=manifest,
            manifest_alignment_index=duplicate,
        )
        mismatch = make_alignment(bindings)
        manifest_mismatch = copy.deepcopy(manifest)
        manifest_mismatch["trials"][0]["acceptance_evidence_sha256"] = "f" * 64
        mismatch_result = p2_pregate.evaluate_pregate(
            private_bindings=bindings,
            public_envelopes=envelopes,
            window_salt=salt,
            final_manifest=manifest_mismatch,
            manifest_alignment_index=mismatch,
        )
        self.assertFalse(missing["manifest_alignment_proven"])
        self.assertFalse(duplicate_result["manifest_alignment_proven"])
        self.assertIn("manifest_alignment_invalid", {issue["code"] for issue in duplicate_result["issues"]})
        self.assertFalse(mismatch_result["manifest_alignment_proven"])
        self.assertIn(
            "manifest_alignment_outcome_digest_mismatch",
            {issue["code"] for issue in mismatch_result["issues"]},
        )

    def test_manifest_alignment_requires_complete_private_input_and_chain(self) -> None:
        bindings, envelopes, salt = make_chains()
        manifest = make_manifest(bindings)
        extra = copy.deepcopy(bindings)
        extra.append({"not": "a binding"})
        extra_result = p2_pregate.evaluate_pregate(
            private_bindings=extra,
            public_envelopes=envelopes,
            window_salt=salt,
            final_manifest=manifest,
            manifest_alignment_index=make_alignment(bindings),
        )
        broken = copy.deepcopy(bindings)
        broken[2]["previous_private_binding_sha256"] = "0" * 64
        broken_result = p2_pregate.evaluate_pregate(
            private_bindings=broken,
            public_envelopes=envelopes,
            window_salt=salt,
            final_manifest=manifest,
            manifest_alignment_index=make_alignment(bindings),
        )
        self.assertFalse(extra_result["manifest_alignment_proven"])
        self.assertIn("manifest_alignment_private_input_incomplete", {issue["code"] for issue in extra_result["issues"]})
        self.assertFalse(broken_result["manifest_alignment_proven"])
        self.assertIn("manifest_alignment_private_chain_invalid", {issue["code"] for issue in broken_result["issues"]})

    def test_manifest_alignment_rejects_empty_and_boundary_only_inputs(self) -> None:
        bindings, envelopes, salt = make_chains()
        empty_manifest = make_manifest(bindings)
        empty_manifest["trials"] = []
        empty_alignment = make_alignment(bindings)
        empty_alignment["tasks"] = []
        empty_result = p2_pregate.evaluate_pregate(
            private_bindings=bindings,
            public_envelopes=envelopes,
            window_salt=salt,
            final_manifest=empty_manifest,
            manifest_alignment_index=empty_alignment,
        )
        boundary_result = p2_pregate.evaluate_pregate(
            private_bindings=[bindings[0], bindings[-1]],
            public_envelopes=envelopes,
            window_salt=salt,
            final_manifest=make_manifest(bindings),
            manifest_alignment_index=make_alignment(bindings),
        )
        self.assertFalse(empty_result["manifest_alignment_proven"])
        self.assertIn("manifest_alignment_empty", {issue["code"] for issue in empty_result["issues"]})
        self.assertFalse(boundary_result["manifest_alignment_proven"])
        self.assertIn("manifest_alignment_no_task_pair", {issue["code"] for issue in boundary_result["issues"]})

    def test_manifest_alignment_rejects_unknown_conditional_and_boolean_integer_fields(self) -> None:
        bindings, envelopes, salt = make_chains()
        manifest = make_manifest(bindings, disposition="blocked")
        missing_outcome = copy.deepcopy(manifest)
        del missing_outcome["trials"][0]["acceptance_evidence"]
        missing_result = p2_pregate.evaluate_pregate(
            private_bindings=bindings,
            public_envelopes=envelopes,
            window_salt=salt,
            final_manifest=missing_outcome,
            manifest_alignment_index=make_alignment(bindings),
        )
        unknown = copy.deepcopy(manifest)
        unknown["trials"][0]["unexpected"] = True
        unknown_result = p2_pregate.evaluate_pregate(
            private_bindings=bindings,
            public_envelopes=envelopes,
            window_salt=salt,
            final_manifest=unknown,
            manifest_alignment_index=make_alignment(bindings),
        )
        bool_sequence = copy.deepcopy(make_alignment(bindings))
        bool_sequence["tasks"][0]["ready_binding_sequence"] = True
        with self.assertRaises(p2_pregate.SchemaValidationError):
            p2_pregate.validate_manifest_alignment_index(bool_sequence)
        uppercase_candidate = copy.deepcopy(make_alignment(bindings))
        uppercase_candidate["candidate_commit"] = str(uppercase_candidate["candidate_commit"]).upper()
        with self.assertRaises(p2_pregate.SchemaValidationError):
            p2_pregate.validate_manifest_alignment_index(uppercase_candidate)
        self.assertFalse(missing_result["manifest_alignment_proven"])
        self.assertFalse(unknown_result["manifest_alignment_proven"])
        self.assertIn("manifest_invalid", {issue["code"] for issue in missing_result["issues"]})
        self.assertIn("manifest_invalid", {issue["code"] for issue in unknown_result["issues"]})

    def test_manifest_alignment_rejects_non_string_skill_candidate_without_leak(self) -> None:
        bindings, envelopes, salt = make_chains()
        malformed = make_manifest(bindings)
        malformed["trials"][0]["skill_candidate_commit"] = {"not": "a string"}
        result = p2_pregate.evaluate_pregate(
            private_bindings=bindings,
            public_envelopes=envelopes,
            window_salt=salt,
            final_manifest=malformed,
            manifest_alignment_index=make_alignment(bindings),
        )
        self.assertFalse(result["manifest_alignment_proven"])
        self.assertIn("manifest_invalid", {issue["code"] for issue in result["issues"]})

    def test_manifest_alignment_rejects_non_string_expected_candidate_without_leak(self) -> None:
        bindings, envelopes, salt = make_chains()
        result = p2_pregate.evaluate_pregate(
            private_bindings=bindings,
            public_envelopes=envelopes,
            window_salt=salt,
            final_manifest=make_manifest(bindings),
            manifest_alignment_index=make_alignment(bindings),
            expected_candidate_commit={"not": "a string"},
        )
        self.assertFalse(result["manifest_alignment_proven"])
        self.assertIn("manifest_invalid", {issue["code"] for issue in result["issues"]})

    def test_expected_candidate_commit_rejects_all_malformed_values_and_preserves_valid_path(self) -> None:
        bindings, envelopes, salt = make_chains()
        temp, repo, freeze, head, anchor_manifest = make_public_git_repo(envelopes)
        try:
            malformed_values: tuple[object, ...] = (
                "",
                0,
                False,
                [],
                {},
                "not-a-sha",
                "A" * 40,
                "b" * 39,
                {"malformed": True},
            )
            for malformed in malformed_values:
                with self.subTest(malformed=repr(malformed)):
                    result = p2_pregate.evaluate_pregate(
                        private_bindings=bindings,
                        public_envelopes=envelopes,
                        window_salt=salt,
                        public_anchor_repo=repo,
                        public_freeze_commit=freeze,
                        public_head_commit=head,
                        public_anchor_manifest=anchor_manifest,
                        final_manifest=make_manifest(bindings),
                        manifest_alignment_index=make_alignment(bindings),
                        expected_candidate_commit=malformed,  # type: ignore[arg-type]
                    )
                    codes = {issue["code"] for issue in result["issues"]}
                    self.assertIn("expected_candidate_invalid", codes)
                    self.assertIn("manifest_invalid", codes)
                    self.assertIn("candidate_mismatch", codes)
                    self.assertIn("public_mapping_private_chain_unproven", codes)
                    self.assertFalse(result["public_content_mapping_proven"])
                    self.assertFalse(result["manifest_alignment_proven"])

            valid = p2_pregate.evaluate_pregate(
                private_bindings=bindings,
                public_envelopes=envelopes,
                window_salt=salt,
                public_anchor_repo=repo,
                public_freeze_commit=freeze,
                public_head_commit=head,
                public_anchor_manifest=anchor_manifest,
                final_manifest=make_manifest(bindings),
                manifest_alignment_index=make_alignment(bindings),
                expected_candidate_commit=str(bindings[0]["candidate_commit"]),
            )
        finally:
            temp.cleanup()
        self.assertNotIn("expected_candidate_invalid", {issue["code"] for issue in valid["issues"]})
        self.assertTrue(valid["public_content_mapping_proven"])
        self.assertTrue(valid["manifest_alignment_proven"])
        self.assertFalse(valid["eligible_for_v2_release_gate"])

    def test_same_tree_refs_reject_unsafe_shapes_and_escaped_nul_file_input(self) -> None:
        bindings, envelopes, salt = make_chains()
        unsafe_refs = (
            "main",
            "a" * 40,
            "refs/heads/foo\x00bar",
            "refs/heads/foo bar",
            "refs/heads/foo..bar",
            "refs/heads/foo//bar",
            "refs/heads/.foo",
            "refs/heads/foo.lock",
            "refs/heads/foo/",
            "refs/heads/foo.",
        )
        for candidate_ref in unsafe_refs:
            with self.subTest(candidate_ref=repr(candidate_ref)):
                malformed = make_manifest(bindings)
                malformed["trials"][0]["integration_proof"] = {
                    "mode": "same_tree",
                    "candidate_ref": candidate_ref,
                    "candidate_tree": "a" * 40,
                    "stable_tree": "a" * 40,
                    "tree_scope": {"history_sensitive": False, "non_tree_dependencies": []},
                }
                result = p2_pregate.evaluate_pregate(
                    private_bindings=bindings,
                    public_envelopes=envelopes,
                    window_salt=salt,
                    final_manifest=malformed,
                    manifest_alignment_index=make_alignment(bindings),
                )
                self.assertFalse(result["manifest_alignment_proven"])
                self.assertIn("manifest_invalid", {issue["code"] for issue in result["issues"]})

        with tempfile.TemporaryDirectory(prefix="p2-manifest-") as directory:
            path = Path(directory) / "manifest.json"
            malformed = make_manifest(bindings)
            malformed["trials"][0]["integration_proof"] = {
                "mode": "same_tree",
                "candidate_ref": "refs/heads/escaped\x00ref",
                "candidate_tree": "a" * 40,
                "stable_tree": "a" * 40,
                "tree_scope": {"history_sensitive": False, "non_tree_dependencies": []},
            }
            path.write_text(json.dumps(malformed, ensure_ascii=True), encoding="utf-8")
            result = p2_pregate.evaluate_pregate(
                private_bindings=bindings,
                public_envelopes=envelopes,
                window_salt=salt,
                final_manifest=path,
                manifest_alignment_index=make_alignment(bindings),
            )
        self.assertFalse(result["manifest_alignment_proven"])
        self.assertIn("manifest_invalid", {issue["code"] for issue in result["issues"]})

    def test_git_helpers_bound_timeout_and_reject_unreadable_process_output(self) -> None:
        with patch.object(
            p2_pregate.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["git"], p2_pregate.GIT_TIMEOUT_SECONDS),
        ):
            self.assertIsNone(p2_pregate._run_git_text(Path("."), "rev-parse", "HEAD"))
        unreadable = subprocess.CompletedProcess(["git"], 0, stdout=None, stderr=None)
        with patch.object(p2_pregate.subprocess, "run", return_value=unreadable):
            self.assertIsNone(p2_pregate._run_git_text(Path("."), "rev-parse", "HEAD"))
            self.assertFalse(p2_pregate._git_commit_exists(Path("."), "a" * 40))
            self.assertIsNone(p2_pregate._git_blob_bytes(Path("."), "a" * 40, "receipt.json"))

        valid_outputs = ((b"", b""), (bytearray(), bytearray()), (memoryview(b""), memoryview(b"")))
        for stdout, stderr in valid_outputs:
            with self.subTest(stdout_type=type(stdout).__name__, stderr_type=type(stderr).__name__):
                result = subprocess.CompletedProcess(["git"], 0, stdout=stdout, stderr=stderr)
                with patch.object(p2_pregate.subprocess, "run", return_value=result):
                    self.assertTrue(p2_pregate._git_commit_exists(Path("."), "a" * 40))

        malformed_returncodes = (None, False, True, 0.0, "0", [], {})
        for returncode in malformed_returncodes:
            with self.subTest(returncode=repr(returncode)):
                result = subprocess.CompletedProcess(["git"], returncode, stdout=b"", stderr=b"")
                with patch.object(p2_pregate.subprocess, "run", return_value=result):
                    self.assertFalse(p2_pregate._git_commit_exists(Path("."), "a" * 40))

        malformed_outputs = (None, "", 0, False, [], {}, object())
        for output in malformed_outputs:
            with self.subTest(output_type=type(output).__name__):
                stdout_result = subprocess.CompletedProcess(["git"], 0, stdout=output, stderr=b"")
                with patch.object(p2_pregate.subprocess, "run", return_value=stdout_result):
                    self.assertFalse(p2_pregate._git_commit_exists(Path("."), "a" * 40))
                stderr_result = subprocess.CompletedProcess(["git"], 0, stdout=b"", stderr=output)
                with patch.object(p2_pregate.subprocess, "run", return_value=stderr_result):
                    self.assertFalse(p2_pregate._git_commit_exists(Path("."), "a" * 40))

class P3ComputedAdapterIntegrationTests(unittest.TestCase):
    @staticmethod
    def requests(count: int) -> list[dict[str, object]]:
        return [
            {
                "inventory": {"request": index},
                "proof_root": f"proof-{index}",
                "tool_paths": {
                    "cosign": "cosign",
                    "timestamp_cli": "timestamp-cli",
                    "openssl": "openssl",
                    "openssl_config": "openssl.cnf",
                },
            }
            for index in range(count)
        ]

    @staticmethod
    def result_for(envelope: bytes, index: int, *, digest: str | None = None, second: int | None = None) -> dict[str, object]:
        timestamp_second = index if second is None else second
        value: dict[str, object] = {
            "profile_id": p2_pregate.p3_adapter.PROFILE_ID,
            "submitted_envelope_sha256": digest or hashlib.sha256(envelope).hexdigest(),
            "sigstore_signed_time": f"2026-08-15T00:00:{timestamp_second:02d}Z",
            "github_signed_time": f"2026-08-15T00:00:{timestamp_second:02d}Z",
            "artifact_binding_proven": True,
            "rekor_inclusion_proven": True,
            "sigstore_timestamp_proven": True,
            "github_timestamp_proven": True,
            "two_operator_policy_proven": True,
            "offline_verification_proven": True,
            "privacy_allowlist_passed": True,
            "proof_set_integral": True,
            "issues": [],
        }
        return value

    def test_pregate_calls_adapter_and_computes_integrity_and_order(self) -> None:
        bindings, envelopes, salt = make_chains()
        calls: list[bytes] = []

        def computed(_inventory, envelope, *, proof_root, tool_paths):
            calls.append(envelope)
            return self.result_for(envelope, len(calls))

        with patch.object(p2_pregate.p3_adapter, "verify_proof", side_effect=computed):
            result = p2_pregate.evaluate_pregate(
                private_bindings=bindings,
                public_envelopes=envelopes,
                p3_verification_requests=self.requests(len(envelopes)),
                window_salt=salt,
                expected_candidate_commit="b" * 40,
            )
        self.assertEqual(len(calls), len(envelopes))
        self.assertTrue(result["external_receipts_integral"])
        self.assertTrue(result["pre_outcome_order_proven"])
        self.assertTrue(result["privacy_allowlist_passed"])
        self.assertFalse(result["public_control_proven"])
        self.assertFalse(result["recovery_demonstrated"])
        self.assertFalse(result["eligible_for_v2_release_gate"])
        codes = {issue["code"] for issue in result["issues"]}
        self.assertNotIn("trusted_time_missing", codes)
        self.assertNotIn("external_receipts_unproven", codes)
        self.assertNotIn("pre_outcome_order_unproven", codes)

    def test_count_digest_failure_and_surplus_fail_closed(self) -> None:
        bindings, envelopes, salt = make_chains()
        with patch.object(p2_pregate.p3_adapter, "verify_proof") as verifier:
            result = p2_pregate.evaluate_pregate(
                private_bindings=bindings,
                public_envelopes=envelopes,
                p3_verification_requests=self.requests(len(envelopes) + 1),
                window_salt=salt,
                expected_candidate_commit="b" * 40,
            )
        verifier.assert_not_called()
        self.assertFalse(result["external_receipts_integral"])
        self.assertIn("proof_count_mismatch", {issue["code"] for issue in result["issues"]})

        calls = 0

        def wrong_digest(_inventory, envelope, *, proof_root, tool_paths):
            nonlocal calls
            calls += 1
            digest = "0" * 64 if calls == 2 else None
            return self.result_for(envelope, calls, digest=digest)

        with patch.object(p2_pregate.p3_adapter, "verify_proof", side_effect=wrong_digest):
            result = p2_pregate.evaluate_pregate(
                private_bindings=bindings,
                public_envelopes=envelopes,
                p3_verification_requests=self.requests(len(envelopes)),
                window_salt=salt,
                expected_candidate_commit="b" * 40,
            )
        self.assertFalse(result["external_receipts_integral"])
        self.assertFalse(result["pre_outcome_order_proven"])
        self.assertIn("trusted_time_missing", {issue["code"] for issue in result["issues"]})

    def test_equal_or_reversed_signed_time_never_proves_order(self) -> None:
        bindings, envelopes, salt = make_chains()
        for times in ((1, 2, 2, 4), (4, 3, 2, 1)):
            calls = 0

            def timestamped(_inventory, envelope, *, proof_root, tool_paths):
                nonlocal calls
                current = calls
                calls += 1
                return self.result_for(envelope, current + 1, second=times[current])

            with self.subTest(times=times), patch.object(
                p2_pregate.p3_adapter, "verify_proof", side_effect=timestamped
            ):
                result = p2_pregate.evaluate_pregate(
                    private_bindings=bindings,
                    public_envelopes=envelopes,
                    p3_verification_requests=self.requests(len(envelopes)),
                    window_salt=salt,
                    expected_candidate_commit="b" * 40,
                )
                self.assertTrue(result["external_receipts_integral"])
                self.assertFalse(result["pre_outcome_order_proven"])

    def test_broken_chain_never_proves_order_even_with_integral_receipts(self) -> None:
        bindings, envelopes, salt = make_chains()
        envelopes[2]["previous_envelope_sha256"] = "0" * 64
        calls = 0

        def computed(_inventory, envelope, *, proof_root, tool_paths):
            nonlocal calls
            calls += 1
            return self.result_for(envelope, calls)

        with patch.object(p2_pregate.p3_adapter, "verify_proof", side_effect=computed):
            result = p2_pregate.evaluate_pregate(
                private_bindings=bindings,
                public_envelopes=envelopes,
                p3_verification_requests=self.requests(len(envelopes)),
                window_salt=salt,
                expected_candidate_commit="b" * 40,
            )
        self.assertTrue(result["external_receipts_integral"])
        self.assertFalse(result["pre_outcome_order_proven"])
        self.assertIn("pre_outcome_order_unproven", {issue["code"] for issue in result["issues"]})
    def test_generic_self_reports_never_enter_computed_channel(self) -> None:
        bindings, envelopes, salt = make_chains()
        base = {
            "schema_version": "1.0",
            "proof_type": "rfc3161",
            "provider": "provider",
            "protocol_version": "1",
            "submitted_digest_sha256": p2_pregate.envelope_sha256(envelopes[0]),
            "retained_files": [{"path": "proof.json", "sha256": "a" * 64, "bytes": 1}],
            "verification_policy": "local-only",
            "acquired_at": "2026-08-15T00:00:00Z",
        }
        for field in ("verified", "passed", "eligible"):
            proof = dict(base)
            proof[field] = True
            with self.subTest(field=field):
                result = p2_pregate.evaluate_pregate(
                    private_bindings=bindings,
                    public_envelopes=envelopes,
                    proof_packages=[proof],
                    window_salt=salt,
                    expected_candidate_commit="b" * 40,
                )
                self.assertFalse(result["external_receipts_integral"])
                self.assertIn("proof_self_reported_verification", {issue["code"] for issue in result["issues"]})



if __name__ == "__main__":
    unittest.main()
