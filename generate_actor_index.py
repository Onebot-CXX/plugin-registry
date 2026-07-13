#!/usr/bin/env python3
"""Validate actor registry entries, generate an index, and resolve artifacts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


REGISTRY_ROOT = Path(__file__).resolve().parent
METADATA_MODULE = REGISTRY_ROOT / "scripts" / "actor_metadata.py"
SPEC = importlib.util.spec_from_file_location("actor_metadata", METADATA_MODULE)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import canonical validator: {METADATA_MODULE}")
metadata = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = metadata
SPEC.loader.exec_module(metadata)

PLATFORM_SUFFIXES = {
    "linux-x86_64": ".so",
    "linux-arm64": ".so",
    "macos-x86_64": ".dylib",
    "macos-arm64": ".dylib",
    "windows-x86_64": ".dll",
    "windows-arm64": ".dll",
}


class RegistryError(ValueError):
    """Raised when actor registry content is invalid."""


def _release_artifacts(
    repository: str, version: str, name: str, platforms: list[str]
) -> dict[str, Any]:
    files: dict[str, Any] = {}
    for platform in platforms:
        suffix = PLATFORM_SUFFIXES[platform]
        filename = f"{name}-{platform}{suffix}"
        files[platform] = {
            "filename": filename,
            "url": f"{repository}/releases/download/v{version}/{filename}",
        }
    return files


def _entry_record(path: Path, entries_root: Path) -> dict[str, Any]:
    document = metadata.require_metadata(path)
    actor = document["actor"]
    artifact = document["artifact"]
    if path.parent.name != actor["id"]:
        raise RegistryError(
            f"{path}: entry directory must equal actor id {actor['id']!r}"
        )

    relative_path = path.relative_to(entries_root.parent).as_posix()
    return {
        "id": actor["id"],
        "name": actor["name"],
        "version": actor["version"],
        "abi": actor["abi"],
        "artifact": {
            "name": artifact["name"],
            "kind": artifact["kind"],
            "entrypoint": artifact["entrypoint"],
            "platforms": artifact["platforms"],
            "install_directory": "lib/obcx/actors",
            "files": _release_artifacts(
                document["publication"]["repository"],
                actor["version"],
                artifact["name"],
                artifact["platforms"],
            ),
        },
        "dependencies": document["dependencies"],
        "compatibility": document["compatibility"],
        "publication": document["publication"],
        "metadata": {
            "path": relative_path,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
    }


def build_index(entries_root: Path) -> dict[str, Any]:
    paths = sorted(entries_root.glob("*/actor.toml"))
    if not paths:
        raise RegistryError(f"no actor.toml entries found under {entries_root}")
    actors = [_entry_record(path, entries_root) for path in paths]
    actors.sort(key=lambda actor: (actor["id"], actor["version"]))

    identities: set[tuple[str, str]] = set()
    for actor in actors:
        identity = (actor["id"], actor["version"])
        if identity in identities:
            raise RegistryError(
                f"duplicate actor registry entry {identity[0]} {identity[1]}"
            )
        identities.add(identity)
    return {"schema_version": 1, "actors": actors}


def encoded_index(index: dict[str, Any]) -> str:
    return json.dumps(index, indent=2, sort_keys=True) + "\n"


def write_index(entries_root: Path, output: Path, check: bool = False) -> None:
    content = encoded_index(build_index(entries_root))
    if check:
        if not output.exists() or output.read_text(encoding="utf-8") != content:
            raise RegistryError(f"generated actor index is stale: {output}")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")


def resolve_artifact(
    index: dict[str, Any], actor_id: str, version: str, platform: str
) -> dict[str, Any]:
    for actor in index.get("actors", []):
        if actor.get("id") == actor_id and actor.get("version") == version:
            files = actor["artifact"]["files"]
            if platform not in files:
                raise RegistryError(f"unsupported artifact platform: {platform}")
            return {
                "id": actor_id,
                "version": version,
                "abi": actor["abi"],
                "entrypoint": actor["artifact"]["entrypoint"],
                "install_directory": actor["artifact"]["install_directory"],
                **files[platform],
            }
    raise RegistryError(f"actor artifact not found: {actor_id} {version}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument(
        "--entries", type=Path, default=REGISTRY_ROOT / "entries"
    )

    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument(
        "--entries", type=Path, default=REGISTRY_ROOT / "entries"
    )
    generate_parser.add_argument(
        "--output", type=Path, default=REGISTRY_ROOT / "index" / "actors.json"
    )
    generate_parser.add_argument("--check", action="store_true")

    resolve_parser = subparsers.add_parser("resolve")
    resolve_parser.add_argument(
        "--index", type=Path, default=REGISTRY_ROOT / "index" / "actors.json"
    )
    resolve_parser.add_argument("--id", required=True)
    resolve_parser.add_argument("--version", required=True)
    resolve_parser.add_argument(
        "--platform", required=True, choices=tuple(sorted(PLATFORM_SUFFIXES))
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            index = build_index(args.entries)
            print(f"valid actor registry: {len(index['actors'])} entries")
        elif args.command == "generate":
            write_index(args.entries, args.output, args.check)
            print(f"valid actor index: {args.output}")
        else:
            index = json.loads(args.index.read_text(encoding="utf-8"))
            print(
                json.dumps(
                    resolve_artifact(
                        index, args.id, args.version, args.platform
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
    except (metadata.ActorMetadataError, RegistryError, OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
