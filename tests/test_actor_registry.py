import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "generate_index.py"
SPEC = importlib.util.spec_from_file_location("actor_registry", MODULE)
registry = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(registry)


class ActorRegistryTest(unittest.TestCase):
    def entries(self):
        return sorted((ROOT / "actors").glob("*.toml"))

    def test_bridge_and_message_store_entries_are_valid(self):
        index = registry.build_index(self.entries(), "2026-01-01T00:00:00Z")
        self.assertEqual(
            list(index["actors"]), ["obcx.bridge", "obcx.message-store"]
        )
        self.assertTrue(all(row["abi"] == 2 for row in index["actors"].values()))

    def test_unsupported_abi_is_rejected(self):
        value = registry.load_actor(ROOT / "actors" / "bridge.toml")
        value = copy.deepcopy(value)
        value["actor"]["abi"] = 1
        with self.assertRaisesRegex(registry.RegistryError, "abi must equal 2"):
            registry.validate_actor(value)

    def test_unknown_metadata_fields_are_rejected(self):
        value = registry.load_actor(ROOT / "actors" / "bridge.toml")
        value = copy.deepcopy(value)
        value["plugin"] = {"name": "legacy"}
        with self.assertRaisesRegex(registry.RegistryError, "unknown field"):
            registry.validate_actor(value)

    def test_generation_is_deterministic(self):
        first = registry.build_index(self.entries(), "2026-01-01T00:00:00Z")
        second = registry.build_index(
            list(reversed(self.entries())), "2026-01-01T00:00:00Z"
        )
        self.assertEqual(
            json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True)
        )

    def test_artifact_and_source_resolution_are_explicit(self):
        record = registry.build_index(
            self.entries(), "2026-01-01T00:00:00Z"
        )["actors"]["obcx.bridge"]
        self.assertEqual(record["source"]["revision"], "v0.1.0")
        self.assertEqual(
            record["artifact"]["release_url"],
            "https://github.com/vollate/obcx-actor-bridge/releases/download/v0.1.0/bridge",
        )

    def test_writer_replaces_stale_actor_files(self):
        index = registry.build_index(self.entries(), "2026-01-01T00:00:00Z")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            stale = output / "actors" / "stale.json"
            stale.parent.mkdir(parents=True)
            stale.write_text("{}", encoding="utf-8")
            registry.write_index(index, output)
            self.assertFalse(stale.exists())
            self.assertTrue((output / "actors" / "obcx.bridge.json").exists())


if __name__ == "__main__":
    unittest.main()
