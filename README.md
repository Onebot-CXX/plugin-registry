# OBCX Actor Registry

The registry publishes canonical ABI-2 OBCX actor packages only.

To submit an actor, add `actors/<actor-id>.toml` using the same canonical
`actor.toml` fields as the package repository: identity, semantic version,
`abi = 2`, supported OBCX range, artifact, dependencies, and publication data.
No alternate entry or compatibility schema is supported.

Validate entries and regenerate the deterministic index with:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/generate_index.py
```

Generated files are written to `dist/index.json`, `dist/actors/*.json`, and
`dist/index.html`. Release artifacts resolve from the canonical repository,
semantic version tag, and artifact filename in each entry.
