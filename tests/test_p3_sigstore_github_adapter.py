from __future__ import annotations

import base64
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "skills" / "bootstrap-ai-native-dev-team" / "scripts"
FIXTURE = ROOT / "tests" / "fixtures" / "p3-public"
PROOF = FIXTURE / "proof"
sys.path.insert(0, str(SCRIPT_DIR))

import p3_sigstore_github_adapter as p3  # noqa: E402


TOOL_ENV = {
    "cosign": "P3_COSIGN_PATH",
    "timestamp_cli": "P3_TIMESTAMP_CLI_PATH",
    "openssl": "P3_OPENSSL_PATH",
    "openssl_config": "P3_OPENSSL_CONFIG_PATH",
}


def load_inventory() -> dict[str, object]:
    return p3.parse_json_bytes((FIXTURE / "inventory.json").read_bytes())


def configured_tools(test: unittest.TestCase) -> dict[str, str]:
    values = {name: os.environ.get(variable) for name, variable in TOOL_ENV.items()}
    missing = [variable for name, variable in TOOL_ENV.items() if not values[name]]
    if missing:
        test.skipTest("pinned local verifier paths not supplied: " + ",".join(missing))
    assert all(values.values())
    return {name: str(value) for name, value in values.items()}


def update_artifact(inventory: dict[str, object], field: str, data: bytes) -> None:
    item = inventory[field]
    assert isinstance(item, dict)
    item["bytes"] = len(data)
    item["sha256"] = hashlib.sha256(data).hexdigest()


def copy_proof(root: Path) -> Path:
    target = root / "proof"
    shutil.copytree(PROOF, target)
    return target


def pem_with_oid_replaced(raw: bytes, old: bytes, new: bytes) -> bytes:
    lines = raw.decode("ascii").strip().splitlines()
    der = base64.b64decode("".join(lines[1:-1]))
    if der.count(old) != 1:
        raise AssertionError("expected one certificate OID")
    changed = der.replace(old, new)
    encoded = base64.b64encode(changed).decode("ascii")
    body = "\n".join(encoded[index:index + 64] for index in range(0, len(encoded), 64))
    return (lines[0] + "\n" + body + "\n" + lines[-1] + "\n").encode("ascii")


class SchemaAndInventoryTests(unittest.TestCase):
    def test_schema_is_strict_and_contains_no_result_fields(self) -> None:
        schema = json.loads(
            (ROOT / "skills" / "bootstrap-ai-native-dev-team" / "references" /
             "p3-sigstore-github-proof.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(schema["properties"]))
        rendered = json.dumps(schema, sort_keys=True)
        for forbidden in ("verified", "passed", "eligible", "proof_set_integral"):
            self.assertNotIn(forbidden, rendered)

    def test_rekor_protobuf_unsigned_integers_reject_boolean_and_number(self) -> None:
        inventory = load_inventory()
        public_key = (PROOF / "disposable-cosign.pub").read_bytes()
        signature = (PROOF / "signature.raw").read_bytes()
        for value in (True, 1, "01", "-1"):
            bundle = p3.parse_json_bytes((PROOF / "p3-submitted.bundle.json").read_bytes())
            bundle["verificationMaterial"]["tlogEntries"][0]["logIndex"] = value
            with self.subTest(value=value), self.assertRaisesRegex(p3.AdapterError, "unsigned integer"):
                p3._strict_bundle(bundle, inventory["submitted_envelope_sha256"], public_key, signature)
    def test_json_and_inventory_fail_closed(self) -> None:
        for raw in (b'{}{}', b'\xef\xbb\xbf{}', b'{"a":1.0}', b'{"a":1,"a":2}'):
            with self.subTest(raw=raw), self.assertRaises(p3.AdapterError):
                p3.parse_json_bytes(raw)
        inventory = load_inventory()
        p3.validate_proof_inventory(inventory)
        cases = []
        unknown = copy.deepcopy(inventory)
        unknown["verified"] = True
        cases.append(unknown)
        profile = copy.deepcopy(inventory)
        profile["profile_id"] = "rotated"
        cases.append(profile)
        tool = copy.deepcopy(inventory)
        tool["tool_inventory"][0]["sha256"] = "0" * 64
        cases.append(tool)
        certificate = copy.deepcopy(inventory)
        certificate["github_root"]["sha256"] = "0" * 64
        cases.append(certificate)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(p3.AdapterError):
                p3.validate_proof_inventory(value)

    def test_bundle_nested_unknown_fields_are_rejected(self) -> None:
        inventory = load_inventory()
        bundle = p3.parse_json_bytes((PROOF / "p3-submitted.bundle.json").read_bytes())
        public_key = (PROOF / "disposable-cosign.pub").read_bytes()
        signature = (PROOF / "signature.raw").read_bytes()
        for location in ("message", "digest", "timestamp"):
            changed = copy.deepcopy(bundle)
            if location == "message":
                changed["messageSignature"]["unknown"] = 1
            elif location == "digest":
                changed["messageSignature"]["messageDigest"]["unknown"] = 1
            else:
                changed["verificationMaterial"]["timestampVerificationData"]["unknown"] = 1
            with self.subTest(location=location), self.assertRaises(p3.AdapterError):
                p3._strict_bundle(
                    changed,
                    inventory["submitted_envelope_sha256"],
                    public_key,
                    signature,
                )

    def test_path_extra_file_and_symlink_fail_closed(self) -> None:
        inventory = load_inventory()
        with tempfile.TemporaryDirectory() as temporary:
            proof = copy_proof(Path(temporary))
            (proof / "extra.bin").write_bytes(b"x")
            result = p3.verify_proof(
                inventory,
                (FIXTURE / "opaque-commitment.txt").read_bytes(),
                proof_root=proof,
                tool_paths={name: "missing" for name in TOOL_ENV},
            )
            self.assertFalse(result["proof_set_integral"])
            self.assertEqual(result["issues"][0]["code"], "proof_path_unsafe")
        with tempfile.TemporaryDirectory() as temporary:
            proof = copy_proof(Path(temporary))
            original_lstat = Path.lstat

            def lstat_with_reparse(path):
                stat = original_lstat(path)
                if path.name == "signature.raw":
                    return type("ReparseStat", (), {"st_reparse_tag": 1})()
                return stat

            with patch.object(Path, "lstat", lstat_with_reparse):
                result = p3.verify_proof(
                    inventory,
                    (FIXTURE / "opaque-commitment.txt").read_bytes(),
                    proof_root=proof,
                    tool_paths={name: "missing" for name in TOOL_ENV},
                )
            self.assertEqual(result["issues"][0]["code"], "proof_path_unsafe")


class PositiveAndOfflineTests(unittest.TestCase):
    def test_positive_retained_vector_is_forced_offline(self) -> None:
        tools = configured_tools(self)
        calls: list[list[str]] = []
        original = p3._run_local

        def checked(command, *, cwd, env, timeout=20.0):
            self.assertEqual(env["HTTP_PROXY"], "http://127.0.0.1:9")
            self.assertEqual(env["HTTPS_PROXY"], "http://127.0.0.1:9")
            self.assertEqual(env["ALL_PROXY"], "http://127.0.0.1:9")
            self.assertFalse(any(str(part).startswith(("http://", "https://")) for part in command))
            calls.append(list(command))
            return original(command, cwd=cwd, env=env, timeout=timeout)

        with patch.object(p3, "_run_local", side_effect=checked):
            result = p3.verify_proof(
                FIXTURE / "inventory.json",
                FIXTURE / "opaque-commitment.txt",
                proof_root=PROOF,
                tool_paths=tools,
            )
        self.assertTrue(result["proof_set_integral"], result)
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["submitted_envelope_sha256"], "40ba60b75f180b8e78eb0c913e099531e1a52cf9c640ca8cab8f579782d6a687")
        self.assertEqual(result["sigstore_signed_time"], "2026-08-15T16:27:46Z")
        self.assertEqual(result["github_signed_time"], "2026-08-15T19:17:39Z")
        self.assertEqual(len(calls), 6)

    def test_t1_through_t13_fail_closed_matrix(self) -> None:
        tools = configured_tools(self)
        openssl = Path(tools["openssl"])
        env = p3._offline_environment(Path(tools["openssl_config"]))
        raw_signature = (PROOF / "signature.raw").read_bytes()
        token = (PROOF / "github-tsa-signature.tsr").read_bytes()
        leaf = (PROOF / "github-tsa-leaf.pem").read_bytes()
        root_bytes = (PROOF / "github-tsa-root.pem").read_bytes()
        intermediate = PROOF / "github-tsa-intermediate.pem"

        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            wrong_artifact = temp / "T1.raw"
            wrong_artifact.write_bytes(bytes([raw_signature[0] ^ 1]) + raw_signature[1:])
            one_bit = temp / "T2.tsr"
            one_bit.write_bytes(token[:-1] + bytes([token[-1] ^ 1]))
            truncated = temp / "T3.tsr"
            truncated.write_bytes(token[:-16])
            wrong_leaf = temp / "T4.pem"
            wrong_leaf.write_bytes(root_bytes)
            empty_root = temp / "T6.pem"
            empty_root.write_bytes(b"")
            wrong_eku = temp / "T7.pem"
            wrong_eku.write_bytes(pem_with_oid_replaced(
                leaf,
                bytes.fromhex("06082b06010505070308"),
                bytes.fromhex("06082b06010505070303"),
            ))
            wrong_algorithm = temp / "T9.tsr"
            oid256 = bytes.fromhex("0609608648016503040201")
            oid384 = bytes.fromhex("0609608648016503040202")
            self.assertEqual(token.count(oid256), 1)
            wrong_algorithm.write_bytes(token.replace(oid256, oid384))

            commands = {
                "T1": [str(openssl), "ts", "-verify", "-in", str(PROOF / "github-tsa-signature.tsr"), "-data", str(wrong_artifact), "-CAfile", str(PROOF / "github-tsa-root.pem"), "-untrusted", str(intermediate)],
                "T2": [str(openssl), "ts", "-verify", "-in", str(one_bit), "-data", str(PROOF / "signature.raw"), "-CAfile", str(PROOF / "github-tsa-root.pem"), "-untrusted", str(intermediate)],
                "T3": [str(openssl), "ts", "-verify", "-in", str(truncated), "-data", str(PROOF / "signature.raw"), "-CAfile", str(PROOF / "github-tsa-root.pem"), "-untrusted", str(intermediate)],
                "T4": [str(openssl), "verify", "-purpose", "timestampsign", "-CAfile", str(PROOF / "github-tsa-root.pem"), "-untrusted", str(intermediate), str(wrong_leaf)],
                "T5": [str(openssl), "ts", "-verify", "-in", str(PROOF / "github-tsa-signature.tsr"), "-data", str(PROOF / "signature.raw"), "-CAfile", str(PROOF / "github-tsa-root.pem")],
                "T6": [str(openssl), "ts", "-verify", "-in", str(PROOF / "github-tsa-signature.tsr"), "-data", str(PROOF / "signature.raw"), "-CAfile", str(empty_root), "-untrusted", str(intermediate)],
                "T7": [str(openssl), "verify", "-purpose", "timestampsign", "-CAfile", str(PROOF / "github-tsa-root.pem"), "-untrusted", str(intermediate), str(wrong_eku)],
                "T8": [str(openssl), "ts", "-verify", "-in", str(PROOF / "github-tsa-signature.tsr"), "-data", str(FIXTURE / "opaque-commitment.txt"), "-CAfile", str(PROOF / "github-tsa-root.pem"), "-untrusted", str(intermediate)],
                "T9": [str(openssl), "ts", "-verify", "-in", str(wrong_algorithm), "-data", str(PROOF / "signature.raw"), "-CAfile", str(PROOF / "github-tsa-root.pem"), "-untrusted", str(intermediate)],
                "T10": [str(openssl), "ts", "-verify", "-in", str(PROOF / "github-tsa-signature.tsr"), "-data", str(PROOF / "signature.raw"), "-CAfile", str(empty_root)],
            }
            for case_id, command in commands.items():
                with self.subTest(case_id=case_id):
                    completed = p3._run_local(command, cwd=PROOF, env=env)
                    self.assertNotEqual(completed.returncode, 0)

        inventory = load_inventory()
        drifted = copy.deepcopy(inventory)
        intermediate_bytes = (PROOF / "github-tsa-intermediate.pem").read_bytes() + b"\n"
        update_artifact(drifted, "github_intermediate", intermediate_bytes)
        with self.assertRaisesRegex(p3.AdapterError, "provider certificate identity drifted"):
            p3.validate_proof_inventory(drifted)  # T11
        self.assertFalse(p3._privacy_structure_passes({"project": "private"}, {}))  # T12
        with self.assertRaisesRegex(p3.AdapterError, "earlier"):
            p3._require_signed_time_order(
                datetime(2026, 8, 15, 16, 27, 46, tzinfo=timezone.utc),
                datetime(2026, 8, 15, 16, 27, 45, tzinfo=timezone.utc),
            )  # T13


class ProcessAndCliBoundaryTests(unittest.TestCase):
    def test_timeout_records_pid_without_kill_terminate_or_retry(self) -> None:
        created: list[object] = []

        class TimedOut:
            pid = 43210
            returncode = None

            def __init__(self, *args, **kwargs):
                created.append(self)

            def wait(self, timeout=None):
                raise subprocess.TimeoutExpired(["local"], timeout)

        with patch.object(p3.subprocess, "Popen", TimedOut):
            with self.assertRaises(p3.ToolTimeout) as raised:
                p3._run_local(["local"], cwd=PROOF, env={}, timeout=0.01)
        self.assertEqual(raised.exception.pid, 43210)
        self.assertEqual(len(created), 1)
        self.assertFalse(hasattr(created[0], "kill"))
        self.assertFalse(hasattr(created[0], "terminate"))

    def test_sigstore_decode_failure_uses_sigstore_issue_code(self) -> None:
        failed = subprocess.CompletedProcess(["openssl"], 1, b"", b"failed")
        with patch.object(p3, "_run_local", return_value=failed):
            with self.assertRaises(p3.AdapterError) as raised:
                p3._timestamp_text(
                    Path("openssl"),
                    Path("token"),
                    cwd=PROOF,
                    env={},
                    error_code="sigstore_timestamp_invalid",
                )
        self.assertEqual(raised.exception.code, "sigstore_timestamp_invalid")
    def test_local_output_is_bounded_before_readback(self) -> None:
        class Loud:
            pid = 1
            returncode = 0

            def __init__(self, *args, **kwargs):
                kwargs["stdout"].write(b"x" * (p3.MAX_OUTPUT_BYTES + 1))

            def wait(self, timeout=None):
                return 0

        with patch.object(p3.subprocess, "Popen", Loud):
            with self.assertRaisesRegex(p3.AdapterError, "output exceeded"):
                p3._run_local(["local"], cwd=PROOF, env={})

    def test_cli_malformed_input_has_bounded_json_and_no_traceback(self) -> None:
        script = SCRIPT_DIR / "p3_sigstore_github_adapter.py"
        command = [
            sys.executable,
            "-X", "utf8", "-B", str(script),
            "--inventory", str(FIXTURE / "opaque-commitment.txt"),
            "--public-envelope", str(FIXTURE / "opaque-commitment.txt"),
            "--proof-root", str(PROOF),
            "--cosign", "missing",
            "--timestamp-cli", "missing",
            "--openssl", "missing",
            "--openssl-config", "missing",
        ]
        completed = subprocess.run(command, capture_output=True, timeout=15, check=False)
        self.assertNotEqual(completed.returncode, 0)
        self.assertLessEqual(len(completed.stdout), p3.MAX_OUTPUT_BYTES)
        self.assertNotIn(b"Traceback", completed.stdout + completed.stderr)
        parsed = json.loads(completed.stdout)
        self.assertFalse(parsed["proof_set_integral"])

        output_failure = subprocess.run(
            command + ["--output", str(PROOF)],
            capture_output=True,
            timeout=15,
            check=False,
        )
        self.assertNotEqual(output_failure.returncode, 0)
        self.assertNotIn(b"Traceback", output_failure.stdout + output_failure.stderr)
        self.assertFalse(json.loads(output_failure.stdout)["proof_set_integral"])

    def test_source_has_no_network_or_release_gate_path(self) -> None:
        source = (SCRIPT_DIR / "p3_sigstore_github_adapter.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"(?m)^\s*(?:import|from)\s+(?:socket|urllib|http|requests)\b")
        self.assertNotIn("v2_release_gate", source)
        urls = set(__import__("re").findall(r"https?://[^\"\s]+", source))
        self.assertEqual(urls, {"http://127.0.0.1:9"})
        self.assertNotRegex(source, r"(?m)^\s*(?:from|import)\s+(?:tenacity|retrying)\b")
        self.assertNotRegex(source, r"(?m)^\s*for\s+attempt\b")


if __name__ == "__main__":
    unittest.main()