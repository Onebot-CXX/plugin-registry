# OBCX Actor Registry

This repository is the independent actor-only publication registry for OBCX
ABI 2 packages. A submission is a canonical
`entries/<actor-id>/actor.toml`; no second metadata dialect is accepted.

The checked-in entries are:

- `onebot-cxx.message-store`
- `vollate.bridge`

## Validate And Generate

Run all commands from the repository root:

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

## Metadata And Publication Rules

Validation rejects unknown fields, boolean schema or integer fields,
non-canonical dependency names containing unsafe separators, unsupported ABI
or toolchain ranges, and artifact platforms outside the supported set. Actor
dependencies must use semantic-version ranges and cannot be duplicated or
self-referential.

Index generation is deterministic. `artifact.platforms` is authoritative: the
generator publishes only declared OS/architecture assets and gives every raw
shared library a platform-qualified name. It never invents an asset for an
undeclared platform.

`scripts/actor_metadata.py` is the canonical OBCX metadata validator vendored
for standalone registry CI. The OBCX conformance matrix binds this repository
to the core, bridge, message-store, and actor-template revisions; coordinated
conformance also verifies that the vendored validator remains byte-identical
to the SDK copy.
