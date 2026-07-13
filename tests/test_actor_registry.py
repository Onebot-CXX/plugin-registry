from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "generate_actor_index.py"
SPEC = importlib.util.spec_from_file_location("actor_registry", GENERATOR)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import {GENERATOR}")
registry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(registry)


class ActorRegistryTest(unittest.TestCase):
    def test_canonical_entries_are_actor_only(self) -> None:
        index = registry.build_index(ROOT / "entries")
        self.assertEqual(index["schema_version"], 1)
        self.assertEqual(
            [actor["id"] for actor in index["actors"]],
            ["onebot-cxx.message-store", "vollate.bridge"],
        )
        for actor in index["actors"]:
            self.assertEqual(actor["abi"], 2)
            self.assertEqual(
                actor["artifact"]["entrypoint"], "obcx_create_actor_v2"
            )
            self.assertEqual(actor["artifact"]["platforms"], ["linux-x86_64"])

    def test_invalid_canonical_metadata_is_rejected_by_field(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            entries = Path(temporary) / "entries"
            actor_dir = entries / "vollate.bridge"
            actor_dir.mkdir(parents=True)
            source = ROOT / "entries/vollate.bridge/actor.toml"
            content = source.read_text(encoding="utf-8").replace(
                'platforms = ["linux-x86_64"]\n', ""
            )
            (actor_dir / "actor.toml").write_text(content, encoding="utf-8")
            with self.assertRaises(registry.metadata.ActorMetadataError) as error:
                registry.build_index(entries)
        self.assertIn("[artifact].platforms must be an array", str(error.exception))

    def test_generated_index_is_byte_deterministic_and_current(self) -> None:
        first = registry.encoded_index(registry.build_index(ROOT / "entries"))
        second = registry.encoded_index(registry.build_index(ROOT / "entries"))
        self.assertEqual(first, second)
        self.assertEqual(
            first, (ROOT / "index/actors.json").read_text(encoding="utf-8")
        )

    def test_only_declared_platform_resolves(self) -> None:
        index = registry.build_index(ROOT / "entries")
        result = registry.resolve_artifact(
            index, "vollate.bridge", "0.1.0", "linux-x86_64"
        )
        self.assertEqual(result["filename"], "bridge-linux-x86_64.so")
        with self.assertRaisesRegex(
            registry.RegistryError, "unsupported artifact platform"
        ):
            registry.resolve_artifact(
                index, "vollate.bridge", "0.1.0", "macos-arm64"
            )

    def test_registry_schemas_are_closed(self) -> None:
        entry = json.loads(
            (ROOT / "schemas/actor-registry-entry.schema.json").read_text(
                encoding="utf-8"
            )
        )
        index = json.loads(
            (ROOT / "schemas/actor-index.schema.json").read_text(encoding="utf-8")
        )
        self.assertFalse(entry["additionalProperties"])
        self.assertEqual(index["properties"]["schema_version"]["const"], 1)


if __name__ == "__main__":
    unittest.main()
