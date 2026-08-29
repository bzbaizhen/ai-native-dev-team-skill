"""Plan, apply, verify, and roll back the suite's bounded component rename."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from typing import Any, Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "suite-manifest.json"
OLD_COMPONENT_NAME = "bootstrap-ai-native-dev-team"
STAGE_PREFIX = ".stage-"
TASK_PREFIX = "ai-native-dev-team-suite-"
REPARSE_POINT = 0x0400
SECRET_NAME_PARTS = (
    "credential",
    "password",
    "passwd",
    "secret",
    "token",
    "id_rsa",
)


class MigrationError(Exception):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _load_manifest() -> dict[str, Any]:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationError(f"cannot load suite manifest: {exc}") from exc
    if manifest.get("schema_version") != 1:
        raise MigrationError("suite manifest schema_version must be 1")
    components = manifest.get("components")
    if not isinstance(components, list) or len(components) != 2:
        raise MigrationError("suite manifest must declare exactly two components")
    if [item.get("id") for item in components] != ["ai-native-dev-team", "ai-native-model-router"]:
        raise MigrationError("suite manifest component order or ids are not canonical")
    if manifest.get("legacy", {}).get("id") != OLD_COMPONENT_NAME:
        raise MigrationError("suite manifest legacy component is not canonical")
    for component in components:
        _manifest_files(component)
    return manifest


def _manifest_files(component: dict[str, Any]) -> list[str]:
    files = component.get("files")
    if not isinstance(files, list) or not all(isinstance(item, str) for item in files):
        raise MigrationError(f"manifest files must be a string array: {component.get('id')}")
    if files != sorted(files) or len(files) != len(set(files)):
        raise MigrationError(f"manifest files must be sorted and unique: {component.get('id')}")
    for relative in files:
        path = Path(relative)
        if not relative or path.is_absolute() or ".." in path.parts or "\\" in relative:
            raise MigrationError(f"manifest file path is not a safe relative path: {relative}")
    return files


def _explicit_path(value: str | os.PathLike[str], label: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise MigrationError(f"{label} must be an absolute path")
    if any(part == ".." for part in path.parts):
        raise MigrationError(f"{label} contains traversal")
    if path == Path(path.anchor):
        raise MigrationError(f"{label} must not be a filesystem root")
    normalized = Path(os.path.normpath(os.fspath(path)))
    _validate_path_safety(normalized, label)
    return normalized


def _validate_path_safety(path: Path, label: str) -> None:
    """Reject symlink/reparse components among all existing path ancestors."""
    components: list[Path] = []
    current = path
    while True:
        components.append(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    for component in reversed(components):
        try:
            info = os.lstat(component)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise MigrationError(f"cannot inspect {label} path component {component}: {exc}") from exc
        if stat.S_ISLNK(info.st_mode):
            raise MigrationError(f"{label} has a symlink ancestor: {component}")
        if os.name == "nt" and getattr(info, "st_file_attributes", 0) & REPARSE_POINT:
            raise MigrationError(f"{label} has a Windows reparse/junction ancestor: {component}")


def _same_or_nested(left: Path, right: Path) -> bool:
    try:
        left.relative_to(right)
        return True
    except ValueError:
        try:
            right.relative_to(left)
            return True
        except ValueError:
            return False


def _entry_is_unsupported(entry: os.DirEntry[str]) -> str | None:
    try:
        info = entry.stat(follow_symlinks=False)
    except OSError as exc:
        return f"cannot inspect {entry.path}: {exc}"
    if entry.is_symlink():
        return f"symlink is unsupported: {entry.path}"
    if os.name == "nt" and info.st_file_attributes & REPARSE_POINT:
        return f"reparse point is unsupported: {entry.path}"
    if stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode):
        return None
    return f"unsupported file type: {entry.path}"


def _secret_name(name: str) -> bool:
    lowered = name.casefold()
    return (
        lowered in {".env", ".env.local", "credentials", "secrets"}
        or lowered.endswith((".pem", ".key", ".p12", ".pfx", ".secret"))
        or any(part in lowered for part in SECRET_NAME_PARTS)
    )


def _inventory_directory(directory: Path) -> list[dict[str, Any]]:
    _validate_path_safety(directory, "inventory directory")
    if not directory.exists():
        raise MigrationError(f"missing directory: {directory}")
    if not directory.is_dir():
        raise MigrationError(f"expected directory: {directory}")

    inventory: list[dict[str, Any]] = []

    def visit(current: Path, prefix: tuple[str, ...]) -> None:
        try:
            entries = sorted(os.scandir(current), key=lambda item: item.name.casefold())
        except OSError as exc:
            raise MigrationError(f"cannot read {current}: {exc}") from exc
        for entry in entries:
            relative_parts = prefix + (entry.name,)
            relative = "/".join(relative_parts)
            if entry.name in {"__pycache__", ".pytest_cache"} or entry.name.endswith(".pyc"):
                raise MigrationError(f"pycache/generated file is not allowed: {relative}")
            if _secret_name(entry.name):
                raise MigrationError(f"secret or credential-looking file is not allowed: {relative}")
            unsupported = _entry_is_unsupported(entry)
            if unsupported:
                raise MigrationError(unsupported)
            if entry.is_dir(follow_symlinks=False):
                visit(Path(entry.path), relative_parts)
            else:
                try:
                    size = entry.stat(follow_symlinks=False).st_size
                    sha256 = _file_hash(Path(entry.path))
                except OSError as exc:
                    raise MigrationError(f"cannot hash {entry.path}: {exc}") from exc
                inventory.append({"path": relative, "size": size, "sha256": sha256})

    visit(directory, ())
    return sorted(inventory, key=lambda item: item["path"])


def _file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _inventory_digest(inventory: list[dict[str, Any]]) -> str:
    return digest_json(inventory)


def _state(path: Path) -> dict[str, Any]:
    _validate_path_safety(path, "state target")
    if not path.exists():
        return {"exists": False, "kind": "absent", "inventory": [], "digest": _inventory_digest([])}
    if not path.is_dir():
        raise MigrationError(f"component collision is not a directory: {path}")
    inventory = _inventory_directory(path)
    return {
        "exists": True,
        "kind": "directory",
        "inventory": inventory,
        "digest": _inventory_digest(inventory),
    }


def _source_base(source_root: Path) -> Path:
    skills = source_root / "skills"
    if skills.is_dir() and not skills.is_symlink():
        return skills
    return source_root


def _path_map(roots: Iterable[Path]) -> list[Path]:
    unique: dict[str, Path] = {}
    for root in roots:
        normalized = _explicit_path(root, "install-root")
        key = os.path.normcase(os.path.normpath(os.fspath(normalized)))
        if key in unique:
            raise MigrationError(
                f"duplicate install roots after normalization: {unique[key]} and {normalized}"
            )
        unique[key] = normalized
    return [unique[key] for key in sorted(unique)]


def _validate_roots(source_root: Path, install_roots: list[Path], backup_root: Path) -> list[str]:
    blockers: list[str] = []
    all_roots = [("source-root", source_root), ("backup-root", backup_root)]
    all_roots.extend(("install-root", root) for root in install_roots)
    for label, path in all_roots:
        if path.is_symlink():
            blockers.append(f"{label} is a symlink: {path}")
    for index, left in enumerate(install_roots):
        for right in install_roots[index + 1:]:
            if _same_or_nested(left, right):
                blockers.append(f"install roots are nested or colliding: {left} and {right}")
    for label, other in (("source-root", source_root), ("backup-root", backup_root)):
        for install in install_roots:
            if _same_or_nested(other, install):
                blockers.append(f"{label} and install-root are nested or colliding: {other} and {install}")
    if not source_root.exists() or not source_root.is_dir():
        blockers.append(f"missing source-root: {source_root}")
    if not backup_root.exists() or not backup_root.is_dir():
        blockers.append(f"missing backup-root: {backup_root}")
    elif backup_root.is_symlink():
        blockers.append(f"backup-root is a symlink: {backup_root}")
    for install in install_roots:
        if install.exists() and not install.is_dir():
            blockers.append(f"install-root is not a directory: {install}")
        if not install.exists() and not install.parent.is_dir():
            blockers.append(f"install-root parent is missing: {install.parent}")
    return sorted(set(blockers))


def _empty_plan(source_root: Path, install_roots: list[Path], backup_root: Path, blockers: list[str]) -> dict[str, Any]:
    manifest = _load_manifest()
    plan = {
        "schema_version": 1,
        "state": "plan",
        "suite_id": manifest["suite"]["id"],
        "old_component": OLD_COMPONENT_NAME,
        "source_root": os.fspath(source_root),
        "install_roots": [os.fspath(path) for path in install_roots],
        "backup_root": os.fspath(backup_root),
        "source": {"base": None, "components": []},
        "roots": [],
        "compatibility_matrix": manifest["compatibility_matrix"],
        "blockers": sorted(set(blockers)),
    }
    plan["plan_digest"] = digest_json(plan)
    return plan


def build_plan(source_root: Path | str, install_roots: Iterable[Path | str], backup_root: Path | str) -> dict[str, Any]:
    manifest = _load_manifest()
    source_root = _explicit_path(source_root, "source-root")
    roots = _path_map([Path(item) for item in install_roots])
    backup_root = _explicit_path(backup_root, "backup-root")
    blockers = _validate_roots(source_root, roots, backup_root)
    if blockers:
        return _empty_plan(source_root, roots, backup_root, blockers)

    base = _source_base(source_root)
    source_components: list[dict[str, Any]] = []
    for component in manifest["components"]:
        component_path = base / component["id"]
        try:
            inventory = _inventory_directory(component_path)
            declared_files = _manifest_files(component)
            actual_files = [item["path"] for item in inventory]
            if actual_files != declared_files:
                missing = sorted(set(declared_files) - set(actual_files))
                extra = sorted(set(actual_files) - set(declared_files))
                details = []
                if missing:
                    details.append("missing=" + ",".join(missing))
                if extra:
                    details.append("extra=" + ",".join(extra))
                raise MigrationError(
                    f"source inventory does not match manifest files for {component['id']}: "
                    + "; ".join(details)
                )
            source_components.append({
                "id": component["id"],
                "version": component["version"],
                "role": component["role"],
                "files": declared_files,
                "path": os.fspath(component_path),
                "inventory": inventory,
                "digest": _inventory_digest(inventory),
            })
        except MigrationError as exc:
            blockers.append(str(exc))

    roots_payload: list[dict[str, Any]] = []
    for root in roots:
        targets: dict[str, Any] = {}
        for name in [OLD_COMPONENT_NAME] + [component["id"] for component in manifest["components"]]:
            try:
                targets[name] = _state(root / name)
            except MigrationError as exc:
                blockers.append(str(exc))
        roots_payload.append({
            "install_root": os.fspath(root),
            "root_exists": root.exists(),
            "root_kind": "directory" if root.is_dir() else "absent",
            "targets": targets,
        })

    plan = {
        "schema_version": 1,
        "state": "plan",
        "suite_id": manifest["suite"]["id"],
        "old_component": OLD_COMPONENT_NAME,
        "new_components": [component["id"] for component in manifest["components"]],
        "source_root": os.fspath(source_root),
        "install_roots": [os.fspath(path) for path in roots],
        "backup_root": os.fspath(backup_root),
        "source": {"base": os.fspath(base), "components": source_components},
        "roots": roots_payload,
        "compatibility_matrix": manifest["compatibility_matrix"],
        "blockers": sorted(set(blockers)),
    }
    plan["plan_digest"] = digest_json(plan)
    return plan


def _remove_path(path: Path) -> None:
    if path.is_symlink():
        raise MigrationError(f"refusing to remove symlink: {path}")
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _copy_tree(source: Path, target: Path) -> None:
    if target.exists() or target.is_symlink():
        raise MigrationError(f"staging target already exists: {target}")
    target.mkdir(parents=True)
    for item in _inventory_directory(source):
        source_file = source.joinpath(*item["path"].split("/"))
        target_file = target.joinpath(*item["path"].split("/"))
        target_file.parent.mkdir(parents=True, exist_ok=True)
        with source_file.open("rb") as reader, target_file.open("xb") as writer:
            shutil.copyfileobj(reader, writer)
    actual = _inventory_directory(target)
    if actual != _inventory_directory(source):
        raise MigrationError(f"staged bytes do not match source: {source}")


def _copy_backup(source: Path, target: Path) -> None:
    if target.exists() or target.is_symlink():
        raise MigrationError(f"backup target already exists: {target}")
    _copy_tree(source, target)


def _state_matches(path: Path, expected: dict[str, Any]) -> bool:
    try:
        return _state(path) == expected
    except MigrationError:
        return False


def _backup_one_root(root_entry: dict[str, Any], backup_task: Path, root_index: int) -> dict[str, str | None]:
    root = Path(root_entry["install_root"])
    target_states = root_entry["targets"]
    root_backup = backup_task / f"root-{root_index:04d}"
    root_backup.mkdir(parents=True, exist_ok=False)
    paths: dict[str, str | None] = {}
    for name in [OLD_COMPONENT_NAME, "ai-native-dev-team", "ai-native-model-router"]:
        target = root / name
        if target_states[name]["exists"]:
            destination = root_backup / name
            _copy_backup(target, destination)
            paths[name] = os.fspath(destination)
        else:
            paths[name] = None
    return paths


def _apply_one_root(
    plan: dict[str, Any], root_entry: dict[str, Any], backup_task: Path, source_base: Path, root_index: int
) -> dict[str, Any]:
    root = Path(root_entry["install_root"])
    root_created = not root.exists()
    root.mkdir(parents=True, exist_ok=True)
    stage = root / f"{STAGE_PREFIX}{plan['plan_digest'][:16]}"
    if stage.exists() or stage.is_symlink():
        raise MigrationError(f"staging directory already exists: {stage}")
    stage.mkdir()
    operations = ["stage source inventories", "verify staged bytes"]
    backup_paths: dict[str, str | None] | None = None
    try:
        for component in plan["source"]["components"]:
            _copy_tree(source_base / component["id"], stage / component["id"])
        backup_paths = _backup_one_root(root_entry, backup_task, root_index)
        operations.append("backup existing old/new targets")
        for component in plan["source"]["components"]:
            target = root / component["id"]
            _remove_path(target)
            os.replace(stage / component["id"], target)
        operations.append("atomically replace new components")
        for component in plan["source"]["components"]:
            expected = next(item for item in plan["source"]["components"] if item["id"] == component["id"])["inventory"]
            if _inventory_directory(root / component["id"]) != expected:
                raise MigrationError(f"installed bytes do not match source: {component['id']} at {root}")
        operations.append("verify both new components")
        _remove_path(root / OLD_COMPONENT_NAME)
        operations.append("remove legacy component after verification")
        _remove_path(stage)
        return {
            "install_root": os.fspath(root),
            "backup_paths": backup_paths,
            "operations": operations,
            "root_created": root_created,
        }
    except Exception as apply_error:
        try:
            _remove_path(stage)
            if backup_paths is not None:
                _restore_root(root_entry, backup_paths, root_created)
            elif root_created and root.exists() and not any(root.iterdir()):
                root.rmdir()
        except Exception as rollback_error:
            raise MigrationError(
                f"root apply failed: {apply_error}; automatic rollback failed: {rollback_error}"
            ) from apply_error
        raise


def _restore_root(
    root_entry: dict[str, Any],
    backup_paths: dict[str, str | None],
    root_created: bool,
    *,
    remove_root_if_absent: bool = False,
) -> None:
    root = Path(root_entry["install_root"])
    for name in [OLD_COMPONENT_NAME, "ai-native-dev-team", "ai-native-model-router"]:
        _remove_path(root / name)
    for name, backup in backup_paths.items():
        if backup:
            source = Path(backup)
            destination = root / name
            _copy_tree(source, destination)
    if (root_created or remove_root_if_absent) and root.exists() and not any(root.iterdir()):
        root.rmdir()


def _current_states(roots: Iterable[Path]) -> list[dict[str, Any]]:
    result = []
    for root in roots:
        targets = {
            name: _state(root / name)
            for name in [OLD_COMPONENT_NAME, "ai-native-dev-team", "ai-native-model-router"]
        }
        result.append({
            "install_root": os.fspath(root),
            "root_exists": root.exists(),
            "root_kind": "directory" if root.is_dir() else "absent",
            "targets": targets,
        })
    return result


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    if not path.parent.is_dir():
        raise MigrationError(f"receipt parent directory is missing: {path.parent}")
    encoded = canonical_json(payload) + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        readback = json.loads(path.read_text(encoding="utf-8"))
        if readback != payload:
            raise MigrationError(f"receipt readback mismatch: {path}")
        return readback
    finally:
        if temporary.exists():
            temporary.unlink()


def _without(payload: dict[str, Any], key: str) -> dict[str, Any]:
    copy = dict(payload)
    copy.pop(key, None)
    return copy


def _validate_plan_digest(plan: dict[str, Any], supplied: str) -> None:
    expected = plan.get("plan_digest")
    if not isinstance(expected, str) or digest_json(_without(plan, "plan_digest")) != expected:
        raise MigrationError("plan self-digest is invalid")
    if supplied != expected:
        raise MigrationError("stale plan digest")


def _validate_receipt_path(path: Path) -> None:
    if path.exists():
        raise MigrationError(f"receipt already exists: {path}")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise MigrationError(f"receipt parent must be an existing directory: {path.parent}")


def _preflight_apply(
    plan: dict[str, Any], backup_root: Path | str, receipt_path: Path | str, plan_digest: str
) -> tuple[Path, Path, Path]:
    if plan.get("state") != "plan":
        raise MigrationError("plan state must be plan")
    _validate_plan_digest(plan, plan_digest)
    backup_root = _explicit_path(backup_root, "backup-root")
    receipt_path = _explicit_path(receipt_path, "receipt")
    _validate_receipt_path(receipt_path)
    if not backup_root.is_dir() or backup_root.is_symlink():
        raise MigrationError(f"backup-root must be an existing directory: {backup_root}")

    source_root = _explicit_path(plan["source_root"], "source-root")
    source_base = _explicit_path(plan["source"]["base"], "source-base")
    roots = _path_map([Path(item) for item in plan["install_roots"]])
    if [os.fspath(root) for root in roots] != plan["install_roots"]:
        raise MigrationError("plan install roots are not canonical")
    if os.fspath(source_root) != plan["source_root"] or os.fspath(backup_root) != plan["backup_root"]:
        raise MigrationError("plan root binding is invalid")

    # Complete the source and root snapshot before creating a backup task or
    # invoking any operation that can mutate an install root.
    for component in plan["source"]["components"]:
        current = _inventory_directory(source_base / component["id"])
        if [item["path"] for item in current] != component["files"] or current != component["inventory"]:
            raise MigrationError("source drifted since plan was created")
    for root_entry in plan["roots"]:
        root = _explicit_path(root_entry["install_root"], "install-root")
        if root.exists() and not root.is_dir():
            raise MigrationError(f"install-root is not a directory: {root}")
        if root.exists() != root_entry.get("root_exists", root.exists()):
            raise MigrationError("install root state drifted since plan was created")
        for name, expected in root_entry["targets"].items():
            if not _state_matches(root / name, expected):
                raise MigrationError("install target state drifted since plan was created")

    backup_task = backup_root / f"{TASK_PREFIX}{plan_digest[:16]}"
    _validate_path_safety(backup_task, "backup task")
    if backup_task.exists() or backup_task.is_symlink():
        raise MigrationError(f"backup task already exists: {backup_task}")
    return backup_root, receipt_path, backup_task


def _verify_plan_restored(plan: dict[str, Any]) -> None:
    for root_entry in plan["roots"]:
        root = Path(root_entry["install_root"])
        if root.exists() != root_entry.get("root_exists", root.exists()):
            raise MigrationError(f"automatic rollback root verification failed: {root}")
        stage = root / f"{STAGE_PREFIX}{plan['plan_digest'][:16]}"
        if stage.exists() or stage.is_symlink():
            raise MigrationError(f"automatic rollback left staging data: {stage}")
        for name, expected in root_entry["targets"].items():
            if not _state_matches(root / name, expected):
                raise MigrationError(f"automatic rollback verification failed: {root / name}")


def _automatic_rollback(
    plan: dict[str, Any],
    applied: list[dict[str, Any]],
    backup_task: Path,
    receipt_path: Path,
) -> None:
    errors: list[str] = []
    for entry in reversed(applied):
        try:
            root_entry = next(
                item for item in plan["roots"] if item["install_root"] == entry["install_root"]
            )
            _restore_root(root_entry, entry["backup_paths"], entry["root_created"])
        except Exception as exc:
            errors.append(f"restore {entry['install_root']}: {exc}")
    try:
        _verify_plan_restored(plan)
    except Exception as exc:
        errors.append(str(exc))
    if errors:
        raise MigrationError("; ".join(errors))

    # Cleanup is deliberately after complete rollback verification. If cleanup
    # itself fails, retain the backup task as recovery evidence.
    if receipt_path.exists() or receipt_path.is_symlink():
        _remove_path(receipt_path)
    if backup_task.exists() or backup_task.is_symlink():
        _remove_path(backup_task)


def apply_plan(
    plan: dict[str, Any],
    backup_root: Path | str,
    receipt_path: Path | str,
    *,
    confirm_breaking_rename: bool,
    plan_digest: str,
    failure_hook: Callable[[int, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if not confirm_breaking_rename:
        raise MigrationError("apply requires --confirm-breaking-rename")
    if plan.get("blockers"):
        raise MigrationError("plan has blockers: " + "; ".join(plan["blockers"]))
    _validate_plan_digest(plan, plan_digest)
    backup_root, receipt_path, backup_task = _preflight_apply(
        plan, backup_root, receipt_path, plan_digest
    )
    backup_task.mkdir()

    source_base = Path(plan["source"]["base"])
    roots = [Path(item["install_root"]) for item in plan["roots"]]
    applied: list[dict[str, Any]] = []
    try:
        for index, root_entry in enumerate(plan["roots"]):
            if failure_hook:
                failure_hook(index + 1, root_entry)
            applied.append(_apply_one_root(plan, root_entry, backup_task, source_base, index + 1))
        # All post-mutation receipt work stays inside the transaction boundary.
        receipt: dict[str, Any] = {
            "schema_version": 1,
            "state": "applied",
            "suite_id": plan["suite_id"],
            "old_component": OLD_COMPONENT_NAME,
            "new_components": plan["new_components"],
            "plan_digest": plan_digest,
            "source_digests": {component["id"]: component["digest"] for component in plan["source"]["components"]},
            "install_roots": [os.fspath(root) for root in roots],
            "backup_root": os.fspath(backup_root),
            "backup_task": os.fspath(backup_task),
            "before": [{"install_root": item["install_root"], "root_exists": item.get("root_exists", True), "root_kind": item.get("root_kind", "directory"), "targets": item["targets"]} for item in plan["roots"]],
            "after": _current_states(roots),
            "backup_paths": [{"install_root": item["install_root"], "targets": result["backup_paths"]} for item, result in zip(plan["roots"], applied)],
            "operations": [{"install_root": result["install_root"], "actions": result["operations"]} for result in applied],
        }
        receipt["receipt_hash"] = digest_json(receipt)
        # Atomic write and its readback are part of the same transaction too.
        return _atomic_write_json(receipt_path, receipt)
    except Exception as exc:
        try:
            _automatic_rollback(plan, applied, backup_task, receipt_path)
        except Exception as rollback_error:
            raise MigrationError(
                f"apply failed: {exc}; automatic rollback failed: {rollback_error}"
            ) from exc
        raise MigrationError(f"apply failed: {exc}") from exc


def _read_applied_receipt(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise MigrationError(f"applied receipt is missing: {path}")
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationError(f"cannot read applied receipt: {exc}") from exc
    if not isinstance(receipt, dict) or receipt.get("state") != "applied":
        raise MigrationError("applied receipt state is invalid")
    receipt_hash = receipt.get("receipt_hash")
    if not isinstance(receipt_hash, str) or digest_json(_without(receipt, "receipt_hash")) != receipt_hash:
        raise MigrationError("applied receipt self-hash is invalid")
    required = (
        "schema_version", "suite_id", "old_component", "new_components", "plan_digest",
        "source_digests", "install_roots", "backup_root", "backup_task",
        "before", "after", "backup_paths", "operations",
    )
    for key in required:
        if key not in receipt:
            raise MigrationError(f"applied receipt is missing {key}")
    if receipt["schema_version"] != 1 or receipt["old_component"] != OLD_COMPONENT_NAME:
        raise MigrationError("applied receipt schema or legacy binding is invalid")
    if receipt["new_components"] != ["ai-native-dev-team", "ai-native-model-router"]:
        raise MigrationError("applied receipt component list is invalid")
    return receipt


def _bind_receipt_to_plan(plan: dict[str, Any], receipt: dict[str, Any]) -> None:
    if receipt.get("suite_id") != plan["suite_id"]:
        raise MigrationError("receipt suite binding is invalid")
    if receipt.get("new_components") != plan["new_components"]:
        raise MigrationError("receipt component binding is invalid")
    source_digests = {
        item["id"]: item["digest"] for item in plan["source"]["components"]
    }
    if receipt.get("source_digests") != source_digests:
        raise MigrationError("receipt source digest binding is invalid")
    bound = dict(plan)
    bound["roots"] = receipt["before"]
    bound["blockers"] = []
    bound.pop("plan_digest", None)
    if digest_json(bound) != receipt.get("plan_digest"):
        raise MigrationError("receipt plan binding is invalid")


def verify_install(
    source_root: Path | str,
    install_roots: Iterable[Path | str],
    backup_root: Path | str,
    receipt_path: Path | str,
) -> dict[str, Any]:
    receipt_path = _explicit_path(receipt_path, "receipt")
    receipt = _read_applied_receipt(receipt_path)
    roots = _path_map([Path(item) for item in install_roots])
    if [os.fspath(root) for root in roots] != receipt.get("install_roots"):
        raise MigrationError("verify install roots do not match the applied receipt")
    backup_root = _explicit_path(backup_root, "backup-root")
    if os.fspath(backup_root) != receipt.get("backup_root"):
        raise MigrationError("verify backup root does not match the applied receipt")
    plan = build_plan(source_root, roots, backup_root)
    if plan["blockers"]:
        raise MigrationError("verification plan has blockers: " + "; ".join(plan["blockers"]))
    _bind_receipt_to_plan(plan, receipt)

    source_components = {item["id"]: item for item in plan["source"]["components"]}
    failures: list[str] = []
    for after, root in zip(receipt["after"], roots):
        actual = _current_states([root])[0]
        if actual != after:
            failures.append(f"installed state does not match applied receipt: {root}")
        if actual["targets"][OLD_COMPONENT_NAME]["exists"]:
            failures.append(f"legacy component is still present: {root / OLD_COMPONENT_NAME}")
        for component_id, component in source_components.items():
            expected = {
                "exists": True,
                "kind": "directory",
                "inventory": component["inventory"],
                "digest": component["digest"],
            }
            if actual["targets"].get(component_id) != expected:
                failures.append(f"exact inventory mismatch: {root / component_id}")
    if len(receipt["after"]) != len(roots):
        failures.append("applied receipt root count is invalid")
    if failures:
        raise MigrationError("; ".join(failures))
    return {
        "schema_version": 1,
        "state": "verified",
        "suite_id": plan["suite_id"],
        "install_roots": plan["install_roots"],
        "source_digests": {item["id"]: item["digest"] for item in plan["source"]["components"]},
        "receipt_hash": receipt["receipt_hash"],
    }


def _validate_backup_evidence(receipt: dict[str, Any]) -> None:
    backup_root = _explicit_path(receipt["backup_root"], "receipt backup-root")
    backup_task = _explicit_path(receipt.get("backup_task", ""), "receipt backup task")
    if backup_task.parent != backup_root or backup_task.name != f"{TASK_PREFIX}{receipt['plan_digest'][:16]}":
        raise MigrationError("backup task is not directly bounded by receipt backup root")
    if not backup_task.is_dir() or backup_task.is_symlink():
        raise MigrationError("receipt backup task is not a safe regular tree")
    expected_root_names = {f"root-{index:04d}" for index in range(1, len(receipt["before"]) + 1)}
    actual_root_names = {item.name for item in backup_task.iterdir()}
    if actual_root_names != expected_root_names:
        raise MigrationError("receipt backup task contains unexpected root evidence")
    names = [OLD_COMPONENT_NAME, "ai-native-dev-team", "ai-native-model-router"]
    for index, (before, backup_entry) in enumerate(zip(receipt["before"], receipt["backup_paths"]), 1):
        root_backup = backup_task / f"root-{index:04d}"
        _validate_path_safety(root_backup, "receipt backup root")
        if not root_backup.is_dir() or root_backup.is_symlink():
            raise MigrationError(f"receipt backup root is not a safe regular tree: {root_backup}")
        targets = backup_entry.get("targets")
        if backup_entry.get("install_root") != before.get("install_root") or not isinstance(targets, dict):
            raise MigrationError("receipt backup root binding is invalid")
        expected_names = {name for name in names if before["targets"][name]["exists"]}
        if {item.name for item in root_backup.iterdir()} != expected_names:
            raise MigrationError(f"receipt backup inventory is not exact: {root_backup}")
        for name in names:
            expected = before["targets"][name]
            backup = targets.get(name)
            if not expected["exists"]:
                if backup is not None:
                    raise MigrationError(f"unexpected backup for absent target: {name}")
                continue
            if not isinstance(backup, str):
                raise MigrationError(f"missing backup for target: {name}")
            candidate = _explicit_path(backup, "receipt backup path")
            if candidate != root_backup / name:
                raise MigrationError(f"backup path is not bounded by its receipt task: {candidate}")
            if not candidate.is_dir() or not _state_matches(candidate, expected):
                raise MigrationError(f"backup does not match receipt before state: {candidate}")


def _create_rollback_guard(applied: dict[str, Any]) -> Path:
    backup_task = _explicit_path(applied["backup_task"], "receipt backup task")
    # Keep the guard bounded by the same backup root while avoiding an
    # unnecessary path-depth increase on Windows installations.
    guard = backup_task.parent / f".rollback-{applied['plan_digest'][:16]}"
    _validate_path_safety(guard, "rollback guard")
    if guard.exists() or guard.is_symlink():
        raise MigrationError(f"rollback guard already exists: {guard}")
    try:
        guard.mkdir()
        for index, after in enumerate(applied["after"], 1):
            root = Path(after["install_root"])
            root_guard = guard / f"r{index}"
            root_guard.mkdir()
            for name, expected in after["targets"].items():
                if expected["exists"]:
                    _copy_tree(root / name, root_guard / name)
        _verify_rollback_guard(applied, guard)
        return guard
    except Exception as exc:
        try:
            if guard.exists() or guard.is_symlink():
                _remove_path(guard)
        except Exception as cleanup_error:
            raise MigrationError(f"rollback guard creation failed: {exc}; guard cleanup failed: {cleanup_error}") from exc
        raise


def _verify_rollback_guard(applied: dict[str, Any], guard: Path) -> None:
    if not guard.is_dir() or guard.is_symlink():
        raise MigrationError(f"rollback guard is not a safe regular tree: {guard}")
    expected_roots = {f"r{index}" for index in range(1, len(applied["after"]) + 1)}
    if {item.name for item in guard.iterdir()} != expected_roots:
        raise MigrationError(f"rollback guard roots are not exact: {guard}")
    for index, after in enumerate(applied["after"], 1):
        root_guard = guard / f"r{index}"
        if not root_guard.is_dir() or root_guard.is_symlink():
            raise MigrationError(f"rollback guard root is not a safe regular tree: {root_guard}")
        expected_names = {name for name, state in after["targets"].items() if state["exists"]}
        if {item.name for item in root_guard.iterdir()} != expected_names:
            raise MigrationError(f"rollback guard inventory is not exact: {root_guard}")
        for name, expected in after["targets"].items():
            candidate = root_guard / name
            if expected["exists"] and not _state_matches(candidate, expected):
                raise MigrationError(f"rollback guard state mismatch: {candidate}")
            if not expected["exists"] and (candidate.exists() or candidate.is_symlink()):
                raise MigrationError(f"rollback guard contains absent target: {candidate}")


def _verify_receipt_states(entries: list[dict[str, Any]], label: str) -> None:
    for entry in entries:
        root = Path(entry["install_root"])
        if root.exists() != entry.get("root_exists", True):
            raise MigrationError(f"{label} root verification failed: {root}")
        for name, expected in entry["targets"].items():
            if not _state_matches(root / name, expected):
                raise MigrationError(f"{label} verification failed: {root / name}")


def _restore_one_root_from_guard(after: dict[str, Any], root_guard: Path) -> None:
    root = Path(after["install_root"])
    if after.get("root_exists", True):
        root.mkdir(parents=True, exist_ok=True)
    for name in after["targets"]:
        _remove_path(root / name)
    for name, expected in after["targets"].items():
        if expected["exists"]:
            _copy_tree(root_guard / name, root / name)
    if not after.get("root_exists", True) and root.exists() and not any(root.iterdir()):
        root.rmdir()


def _recover_to_applied(applied: dict[str, Any], guard: Path) -> None:
    errors: list[str] = []
    for index, after in enumerate(applied["after"], 1):
        try:
            _restore_one_root_from_guard(after, guard / f"r{index}")
        except Exception as exc:
            errors.append(f"restore applied {after['install_root']}: {exc}")
    try:
        _verify_receipt_states(applied["after"], "recovery to applied")
    except Exception as exc:
        errors.append(str(exc))
    if errors:
        raise MigrationError("; ".join(errors))


def rollback_receipt(
    receipt_path: Path | str,
    rollback_path: Path | str,
    install_roots: Iterable[Path | str],
    *,
    receipt_hash: str,
    confirm_rollback: bool,
) -> dict[str, Any]:
    if not confirm_rollback:
        raise MigrationError("rollback requires --confirm-rollback")
    receipt_path = _explicit_path(receipt_path, "receipt")
    rollback_path = _explicit_path(rollback_path, "rollback-receipt")
    _validate_receipt_path(rollback_path)
    applied = _read_applied_receipt(receipt_path)
    if applied.get("receipt_hash") != receipt_hash:
        raise MigrationError("receipt hash or applied state does not match")
    roots = _path_map([Path(item) for item in install_roots])
    if [os.fspath(root) for root in roots] != applied.get("install_roots"):
        raise MigrationError("rollback install roots do not match the applied receipt")

    if len(applied["before"]) != len(roots) or len(applied["after"]) != len(roots) or len(applied["backup_paths"]) != len(roots):
        raise MigrationError("applied receipt root state counts are invalid")
    # All validation is deliberately completed before the first restore write.
    for after, root in zip(applied["after"], roots):
        if _current_states([root])[0] != after:
            raise MigrationError(f"current target state does not match receipt.after: {root}")
    _validate_backup_evidence(applied)

    guard = _create_rollback_guard(applied)
    try:
        restored: list[dict[str, Any]] = []
        for before, backups, root in zip(applied["before"], applied["backup_paths"], roots):
            target_states = before["targets"]
            current_entry = {
                "install_root": os.fspath(root),
                "root_exists": before.get("root_exists", True),
                "targets": target_states,
            }
            paths = backups["targets"]
            _restore_root(
                current_entry,
                paths,
                False,
                remove_root_if_absent=not before.get("root_exists", True),
            )
            _verify_receipt_states([current_entry], "rollback")
            restored.append(_current_states([root])[0])

        _verify_receipt_states(applied["before"], "rollback")
        rollback: dict[str, Any] = {
            "schema_version": 1,
            "state": "rolled_back",
            "suite_id": applied["suite_id"],
            "applied_receipt_hash": receipt_hash,
            "install_roots": applied["install_roots"],
            "before": applied["after"],
            "after": restored,
            "operations": [{"install_root": os.fspath(root), "actions": ["remove installed candidates", "restore backed-up old/new targets", "verify byte-exact prior state"]} for root in roots],
        }
        rollback["rollback_receipt_hash"] = digest_json(rollback)
        result = _atomic_write_json(rollback_path, rollback)
        _remove_path(guard)
        return result
    except Exception as rollback_error:
        try:
            _recover_to_applied(applied, guard)
            if rollback_path.exists() or rollback_path.is_symlink():
                _remove_path(rollback_path)
            if guard.exists() or guard.is_symlink():
                _remove_path(guard)
        except Exception as recovery_error:
            raise MigrationError(
                f"rollback failed: {rollback_error}; recovery to applied failed: {recovery_error}"
            ) from rollback_error
        raise MigrationError(f"rollback failed: {rollback_error}") from rollback_error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="bounded AI Native Dev Team Suite migration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("plan", "apply", "verify", "rollback"):
        sub = subparsers.add_parser(command)
        if command in {"plan", "apply", "verify"}:
            sub.add_argument("--source-root", required=True)
        sub.add_argument("--install-root", action="append", required=True)
        if command in {"plan", "apply", "verify"}:
            sub.add_argument("--backup-root", required=True)
        if command in {"apply", "verify", "rollback"}:
            sub.add_argument("--receipt", required=True)
        if command == "apply":
            sub.add_argument("--plan-digest", required=True)
            sub.add_argument("--confirm-breaking-rename", action="store_true")
        if command == "rollback":
            sub.add_argument("--receipt-hash", required=True)
            sub.add_argument("--rollback-receipt", required=True)
            sub.add_argument("--confirm-rollback", action="store_true")
    return parser


def _run(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.command == "plan":
        return build_plan(arguments.source_root, arguments.install_root, arguments.backup_root)
    if arguments.command == "apply":
        plan = build_plan(arguments.source_root, arguments.install_root, arguments.backup_root)
        return apply_plan(
            plan,
            arguments.backup_root,
            arguments.receipt,
            confirm_breaking_rename=arguments.confirm_breaking_rename,
            plan_digest=arguments.plan_digest,
        )
    if arguments.command == "verify":
        return verify_install(
            arguments.source_root,
            arguments.install_root,
            arguments.backup_root,
            arguments.receipt,
        )
    return rollback_receipt(
        arguments.receipt,
        arguments.rollback_receipt,
        arguments.install_root,
        receipt_hash=arguments.receipt_hash,
        confirm_rollback=arguments.confirm_rollback,
    )


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        output = _run(arguments)
    except MigrationError as exc:
        if arguments.command == "plan":
            print(json.dumps({"schema_version": 1, "state": "plan", "blockers": [str(exc)]}, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if not output.get("blockers") else 2


if __name__ == "__main__":
    raise SystemExit(main())
