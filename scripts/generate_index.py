#!/usr/bin/env python3
"""Generate the deterministic actor-only OBCX registry index."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
ACTORS_DIR = ROOT / "actors"
OUTPUT_DIR = ROOT / "dist"
_ID = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_SEMVER = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
_TOP = {"schema_version", "actor", "artifact", "dependencies", "publication"}
_ACTOR = {"id", "name", "version", "abi", "obcx"}
_ARTIFACT = {"target", "filename"}
_DEPENDENCIES = {"actors", "vcpkg"}
_DEPENDENCY = {"id", "version"}
_PUBLICATION = {"repository", "license", "description"}


class RegistryError(ValueError):
    pass


def _table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise RegistryError(f"{key} must be a table")
    return value


def _text(data: dict[str, Any], key: str, path: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"{path}.{key} must be a non-empty string")
    return value


def _fields(data: dict[str, Any], allowed: set[str], path: str) -> None:
    extra = sorted(set(data) - allowed)
    if extra:
        raise RegistryError(f"{path} has unknown field: {extra[0]}")


def validate_actor(data: dict[str, Any]) -> dict[str, Any]:
    _fields(data, _TOP, "root")
    if data.get("schema_version") != 1:
        raise RegistryError("schema_version must equal 1")
    actor = _table(data, "actor")
    _fields(actor, _ACTOR, "actor")
    actor_id = _text(actor, "id", "actor")
    if not _ID.fullmatch(actor_id):
        raise RegistryError("actor.id is invalid")
    name = _text(actor, "name", "actor")
    if not _ID.fullmatch(name):
        raise RegistryError("actor.name is invalid")
    if not _SEMVER.fullmatch(_text(actor, "version", "actor")):
        raise RegistryError("actor.version must be semantic version text")
    if actor.get("abi") != 2:
        raise RegistryError("actor.abi must equal 2")
    _text(actor, "obcx", "actor")

    artifact = _table(data, "artifact")
    _fields(artifact, _ARTIFACT, "artifact")
    _text(artifact, "target", "artifact")
    filename = _text(artifact, "filename", "artifact")
    if Path(filename).name != filename:
        raise RegistryError("artifact.filename must be a basename")

    dependencies = _table(data, "dependencies")
    _fields(dependencies, _DEPENDENCIES, "dependencies")
    actor_dependencies = dependencies.get("actors", [])
    vcpkg_dependencies = dependencies.get("vcpkg", [])
    if not isinstance(actor_dependencies, list):
        raise RegistryError("dependencies.actors must be an array")
    seen: set[str] = set()
    for index, dependency in enumerate(actor_dependencies):
        path = f"dependencies.actors[{index}]"
        if not isinstance(dependency, dict):
            raise RegistryError(f"{path} must be a table")
        _fields(dependency, _DEPENDENCY, path)
        dependency_id = _text(dependency, "id", path)
        _text(dependency, "version", path)
        if dependency_id == actor_id or dependency_id in seen:
            raise RegistryError(f"{path}.id is invalid or duplicated")
        seen.add(dependency_id)
    if not isinstance(vcpkg_dependencies, list) or any(
        not isinstance(item, str) or not item for item in vcpkg_dependencies
    ):
        raise RegistryError("dependencies.vcpkg must contain package names")
    if len(set(vcpkg_dependencies)) != len(vcpkg_dependencies):
        raise RegistryError("dependencies.vcpkg contains duplicates")

    publication = _table(data, "publication")
    _fields(publication, _PUBLICATION, "publication")
    repository = _text(publication, "repository", "publication").rstrip("/")
    if not repository.startswith("https://github.com/"):
        raise RegistryError("publication.repository must be a GitHub HTTPS URL")
    _text(publication, "license", "publication")
    _text(publication, "description", "publication")
    return data


def load_actor(path: Path) -> dict[str, Any]:
    if path.suffix != ".toml":
        raise RegistryError(f"registry entry must be TOML: {path}")
    try:
        with path.open("rb") as source:
            return validate_actor(tomllib.load(source))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise RegistryError(f"{path}: {error}") from error


def actor_record(data: dict[str, Any]) -> dict[str, Any]:
    actor = data["actor"]
    artifact = data["artifact"]
    publication = data["publication"]
    repository = publication["repository"].rstrip("/")
    tag = f"v{actor['version']}"
    return {
        "id": actor["id"],
        "name": actor["name"],
        "version": actor["version"],
        "abi": actor["abi"],
        "obcx": actor["obcx"],
        "artifact": {
            "target": artifact["target"],
            "filename": artifact["filename"],
            "release_url": f"{repository}/releases/download/{tag}/{artifact['filename']}",
        },
        "dependencies": data["dependencies"],
        "publication": publication,
        "source": {"git": f"{repository}.git", "revision": tag},
    }


def build_index(paths: list[Path], generated_at: str) -> dict[str, Any]:
    actors: dict[str, dict[str, Any]] = {}
    for path in sorted(paths):
        record = actor_record(load_actor(path))
        if record["id"] in actors:
            raise RegistryError(f"duplicate actor id: {record['id']}")
        actors[record["id"]] = record
    ordered = {actor_id: actors[actor_id] for actor_id in sorted(actors)}
    return {
        "registry_version": 1,
        "generated_at": generated_at,
        "actor_count": len(ordered),
        "actors": ordered,
    }


def render_html(index: dict[str, Any]) -> str:
    rows = "\n".join(
        "<tr><td>{id}</td><td>{version}</td><td>{description}</td></tr>".format(
            id=record["id"],
            version=record["version"],
            description=record["publication"]["description"],
        )
        for record in index["actors"].values()
    )
    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>OBCX Actor Registry</title>
<style>body{{font:16px system-ui;max-width:960px;margin:3rem auto;padding:0 1rem}}
table{{border-collapse:collapse;width:100%}}th,td{{padding:.7rem;border-bottom:1px solid #aaa;text-align:left}}</style>
</head><body><h1>OBCX Actor Registry</h1>
<p>{index['actor_count']} actor package(s). <a href=\"index.json\">JSON index</a></p>
<table><thead><tr><th>Actor</th><th>Version</th><th>Description</th></tr></thead>
<tbody>{rows}</tbody></table></body></html>\n"""


def write_index(index: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    actors_output = output_dir / "actors"
    actors_output.mkdir(parents=True, exist_ok=True)
    for stale in actors_output.glob("*.json"):
        stale.unlink()
    (output_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for actor_id, record in index["actors"].items():
        (actors_output / f"{actor_id}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    (output_dir / "index.html").write_text(render_html(index), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actors", type=Path, default=ACTORS_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--generated-at")
    arguments = parser.parse_args(argv)
    generated_at = arguments.generated_at or datetime.now(timezone.utc).isoformat()
    try:
        paths = sorted(arguments.actors.glob("*.toml"))
        if not paths:
            raise RegistryError(f"no actor entries found in {arguments.actors}")
        index = build_index(paths, generated_at)
        write_index(index, arguments.output)
    except RegistryError as error:
        print(f"actor registry generation failed: {error}", file=sys.stderr)
        return 1
    print(f"generated {len(index['actors'])} actor package(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
