#!/usr/bin/env python3
"""
Generate index.json and per-plugin JSON files from plugins/ directory.

For each .toml file in plugins/:
  1. Read the github repo address
  2. Fetch plugin.toml from that repo (via GitHub raw URL)
  3. Fetch latest tags via GitHub API
  4. Produce index.json (all plugins) and plugins/<name>.json (per-plugin)
"""

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("ERROR: Python 3.11+ (tomllib) or tomli package required", file=sys.stderr)
        sys.exit(1)


GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REGISTRY_ROOT = Path(__file__).parent.parent
PLUGINS_DIR = REGISTRY_ROOT / "plugins"
OUTPUT_DIR = REGISTRY_ROOT / "dist"


def github_fetch(url: str) -> str:
    """Fetch a URL, with optional GitHub token auth."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "obcx-plugin-registry")
    if GITHUB_TOKEN:
        req.add_header("Authorization", f"token {GITHUB_TOKEN}")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def fetch_plugin_toml(github_repo: str) -> dict | None:
    """Fetch plugin.toml from the default branch of a GitHub repo."""
    for branch in ["main", "master"]:
        url = f"https://raw.githubusercontent.com/{github_repo}/{branch}/plugin.toml"
        try:
            content = github_fetch(url)
            return tomllib.loads(content)
        except urllib.error.HTTPError:
            continue
    print(f"  WARNING: Could not fetch plugin.toml from {github_repo}", file=sys.stderr)
    return None


def fetch_tags(github_repo: str) -> list[dict]:
    """Fetch tags from GitHub API, return sorted by creation date (newest first)."""
    url = f"https://api.github.com/repos/{github_repo}/tags?per_page=20"
    try:
        data = json.loads(github_fetch(url))
        return [{"name": t["name"]} for t in data]
    except Exception as e:
        print(f"  WARNING: Could not fetch tags for {github_repo}: {e}", file=sys.stderr)
        return []


def fetch_releases(github_repo: str) -> list[dict]:
    """Fetch releases from GitHub API."""
    url = f"https://api.github.com/repos/{github_repo}/releases?per_page=10"
    try:
        data = json.loads(github_fetch(url))
        return data
    except Exception:
        return []


def process_plugin(toml_path: Path) -> dict | None:
    """Process a single plugin registration file."""
    plugin_name = toml_path.stem
    print(f"Processing: {plugin_name}")

    with open(toml_path, "rb") as f:
        reg_data = tomllib.load(f)

    github_repo = reg_data.get("source", {}).get("github", "")
    if not github_repo:
        print(f"  ERROR: No source.github in {toml_path}", file=sys.stderr)
        return None

    # Fetch plugin.toml from the repo
    plugin_meta = fetch_plugin_toml(github_repo)
    if not plugin_meta:
        return None

    plugin_info = plugin_meta.get("plugin", {})
    compat_info = plugin_meta.get("compatibility", {})
    dep_info = plugin_meta.get("dependencies", {})
    build_info = plugin_meta.get("build", {})

    # Fetch version info from tags/releases
    tags = fetch_tags(github_repo)
    releases = fetch_releases(github_repo)

    # Build version list
    versions = []
    if releases:
        for rel in releases:
            if rel.get("draft", False):
                continue
            ver = {
                "version": rel.get("tag_name", "").lstrip("v"),
                "tag": rel.get("tag_name", ""),
                "obcx_abi_version": compat_info.get("obcx_abi_version", 0),
                "obcx_min_version": compat_info.get("obcx_min_version", ""),
                "required_plugins": dep_info.get("required_plugins", []),
                "published_at": rel.get("published_at", ""),
                "source": {
                    "git": f"https://github.com/{github_repo}.git",
                    "tag": rel.get("tag_name", ""),
                },
            }
            versions.append(ver)
    elif tags:
        # Fallback to tags if no releases
        for tag in tags[:5]:
            tag_name = tag["name"]
            ver = {
                "version": tag_name.lstrip("v"),
                "tag": tag_name,
                "obcx_abi_version": compat_info.get("obcx_abi_version", 0),
                "obcx_min_version": compat_info.get("obcx_min_version", ""),
                "required_plugins": dep_info.get("required_plugins", []),
                "published_at": "",
                "source": {
                    "git": f"https://github.com/{github_repo}.git",
                    "tag": tag_name,
                },
            }
            versions.append(ver)
    else:
        # No tags/releases — use plugin.toml version with HEAD
        versions.append({
            "version": plugin_info.get("version", "0.0.0"),
            "tag": "",
            "obcx_abi_version": compat_info.get("obcx_abi_version", 0),
            "obcx_min_version": compat_info.get("obcx_min_version", ""),
            "required_plugins": dep_info.get("required_plugins", []),
            "published_at": "",
            "source": {
                "git": f"https://github.com/{github_repo}.git",
                "tag": "HEAD",
            },
        })

    result = {
        "name": plugin_info.get("name", plugin_name),
        "description": plugin_info.get("description", ""),
        "authors": plugin_info.get("authors", []),
        "license": plugin_info.get("license", ""),
        "homepage": plugin_info.get("homepage", f"https://github.com/{github_repo}"),
        "repository": f"https://github.com/{github_repo}",
        "versions": versions,
        "vcpkg_deps": build_info.get("vcpkg_deps", []),
    }

    print(f"  OK: {len(versions)} version(s)")
    return result


def generate_web_page(plugins: dict, output_dir: Path):
    """Generate a static HTML page for browsing plugins."""
    web_src = REGISTRY_ROOT / "web" / "index.html"
    if web_src.exists():
        # Copy the template and inject data
        html = web_src.read_text()
        # The template will fetch index.json at runtime
        (output_dir / "index.html").write_text(html)
    else:
        # Generate a basic page
        html = generate_default_html(plugins)
        (output_dir / "index.html").write_text(html)


def generate_default_html(plugins: dict) -> str:
    """Generate a simple browsable HTML page."""
    rows = ""
    for name, info in sorted(plugins.items()):
        latest = info["versions"][0]["version"] if info["versions"] else "N/A"
        abi = info["versions"][0].get("obcx_abi_version", "?") if info["versions"] else "?"
        authors = ", ".join(info.get("authors", []))
        rows += f"""
        <tr>
            <td><a href="{info['repository']}" target="_blank">{name}</a></td>
            <td>{info['description']}</td>
            <td>{latest}</td>
            <td>{abi}</td>
            <td>{authors}</td>
            <td>{info.get('license', '')}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OBCX Plugin Registry</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #0d1117; color: #c9d1d9; padding: 2rem; }}
  h1 {{ color: #58a6ff; margin-bottom: 0.5rem; }}
  .subtitle {{ color: #8b949e; margin-bottom: 2rem; }}
  .search {{ width: 100%; max-width: 400px; padding: 0.5rem 1rem; margin-bottom: 1.5rem;
             background: #161b22; border: 1px solid #30363d; border-radius: 6px;
             color: #c9d1d9; font-size: 1rem; }}
  .search:focus {{ outline: none; border-color: #58a6ff; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; padding: 0.75rem; border-bottom: 2px solid #30363d;
       color: #8b949e; font-size: 0.85rem; text-transform: uppercase; }}
  td {{ padding: 0.75rem; border-bottom: 1px solid #21262d; }}
  tr:hover {{ background: #161b22; }}
  a {{ color: #58a6ff; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .api-info {{ margin-top: 2rem; padding: 1rem; background: #161b22;
               border-radius: 6px; border: 1px solid #30363d; }}
  .api-info code {{ background: #0d1117; padding: 0.2rem 0.4rem; border-radius: 3px; }}
  .badge {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 3px;
            font-size: 0.8rem; font-weight: 500; }}
  .badge-abi {{ background: #1f6feb33; color: #58a6ff; }}
</style>
</head>
<body>
<h1>OBCX Plugin Registry</h1>
<p class="subtitle">{len(plugins)} plugin(s) available &middot;
   Updated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</p>

<input type="text" class="search" placeholder="Search plugins..." id="search"
       oninput="filterTable()">

<table id="plugins-table">
<thead>
<tr><th>Name</th><th>Description</th><th>Latest</th><th>ABI</th><th>Authors</th><th>License</th></tr>
</thead>
<tbody>{rows}
</tbody>
</table>

<div class="api-info">
  <strong>API Endpoints:</strong><br>
  All plugins: <code><a href="index.json">index.json</a></code><br>
  Single plugin: <code>plugins/&lt;name&gt;.json</code><br>
  CLI: <code>obcx plugin search &lt;query&gt;</code>
</div>

<script>
function filterTable() {{
  const q = document.getElementById('search').value.toLowerCase();
  const rows = document.querySelectorAll('#plugins-table tbody tr');
  rows.forEach(row => {{
    const text = row.textContent.toLowerCase();
    row.style.display = text.includes(q) ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""


def main():
    # Collect all plugin registration files
    if not PLUGINS_DIR.exists():
        print(f"ERROR: {PLUGINS_DIR} not found", file=sys.stderr)
        sys.exit(1)

    toml_files = sorted(PLUGINS_DIR.glob("*.toml"))
    if not toml_files:
        print("No plugin registrations found in plugins/")
        # Still generate empty index
        toml_files = []

    # Process each plugin
    all_plugins = {}
    for toml_path in toml_files:
        try:
            result = process_plugin(toml_path)
            if result:
                all_plugins[result["name"]] = result
        except Exception as e:
            print(f"  ERROR processing {toml_path.name}: {e}", file=sys.stderr)

    # Generate output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    plugins_output_dir = OUTPUT_DIR / "plugins"
    plugins_output_dir.mkdir(parents=True, exist_ok=True)

    # index.json — full registry (matches what obcx plugin CLI expects)
    index = {
        "registry_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "plugin_count": len(all_plugins),
        "plugins": all_plugins,
    }
    index_path = OUTPUT_DIR / "index.json"
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    print(f"\nGenerated: {index_path} ({len(all_plugins)} plugins)")

    # Per-plugin JSON files
    for name, info in all_plugins.items():
        plugin_path = plugins_output_dir / f"{name}.json"
        with open(plugin_path, "w") as f:
            json.dump(info, f, indent=2, ensure_ascii=False)

    # Generate web page
    generate_web_page(all_plugins, OUTPUT_DIR)
    print(f"Generated: {OUTPUT_DIR / 'index.html'}")
    print(f"\nDone! {len(all_plugins)} plugins indexed.")


if __name__ == "__main__":
    main()
