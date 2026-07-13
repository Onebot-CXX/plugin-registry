# OBCX Actor Registry

This repository is the independent actor-only publication registry for OBCX
ABI 2 packages. A submission is a canonical
`entries/<actor-id>/actor.toml`; no second metadata dialect is accepted.

Validate entries and confirm that the checked-in index is current:

```bash
python3 -m unittest discover -s tests -v
python3 generate_actor_index.py validate
python3 generate_actor_index.py generate --check
```

Regenerate `index/actors.json` after intentionally accepting an entry:

```bash
python3 generate_actor_index.py generate
```

Resolve a built and verified release asset:

```bash
python3 generate_actor_index.py resolve \
  --id vollate.bridge --version 0.1.0 --platform linux-x86_64
```

`artifact.platforms` is authoritative. The generator publishes only declared
OS/architecture assets and gives every raw shared library a platform-qualified
name. `scripts/actor_metadata.py` is the canonical OBCX metadata validator
vendored for standalone registry CI; coordinated OBCX conformance verifies
that the vendored copy remains byte-identical to the SDK validator.
