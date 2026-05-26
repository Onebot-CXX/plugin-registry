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
    """Generate a responsive, light/dark adaptive HTML page."""
    rows = ""
    for name, info in sorted(plugins.items()):
        latest = info["versions"][0]["version"] if info["versions"] else "N/A"
        authors = ", ".join(info.get("authors", []))
        rows += f"""
        <tr>
            <td><a href="{info['repository']}" target="_blank">{name}</a></td>
            <td>{info['description']}</td>
            <td>{latest}</td>
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
  :root {{
    --bg-primary: #ffffff;
    --bg-secondary: #f6f8fa;
    --bg-tertiary: #eaeef2;
    --text-primary: #1f2328;
    --text-secondary: #656d76;
    --border-color: #d0d7de;
    --accent-color: #0969da;
    --accent-hover: #0550ae;
    --hover-bg: #f6f8fa;
    --code-bg: #eff1f3;
    --shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}

  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg-primary: #0d1117;
      --bg-secondary: #161b22;
      --bg-tertiary: #1c2128;
      --text-primary: #e6edf3;
      --text-secondary: #8b949e;
      --border-color: #30363d;
      --accent-color: #58a6ff;
      --accent-hover: #79c0ff;
      --hover-bg: #161b22;
      --code-bg: #1c2128;
      --shadow: 0 1px 3px rgba(0,0,0,0.3);
    }}
  }}

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    padding: 2rem;
    line-height: 1.6;
    transition: background 0.2s, color 0.2s;
  }}

  .container {{
    max-width: 1200px;
    margin: 0 auto;
  }}

  h1 {{
    color: var(--accent-color);
    margin-bottom: 0.5rem;
    font-size: 1.8rem;
  }}

  .subtitle {{
    color: var(--text-secondary);
    margin-bottom: 2rem;
    font-size: 0.95rem;
  }}

  .search {{
    width: 100%;
    max-width: 400px;
    padding: 0.6rem 1rem;
    margin-bottom: 1.5rem;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--text-primary);
    font-size: 1rem;
    transition: border-color 0.2s, box-shadow 0.2s;
  }}

  .search:focus {{
    outline: none;
    border-color: var(--accent-color);
    box-shadow: 0 0 0 3px rgba(9, 105, 218, 0.15);
  }}

  @media (prefers-color-scheme: dark) {{
    .search:focus {{
      box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.15);
    }}
  }}

  .table-wrapper {{
    overflow-x: auto;
    border-radius: 8px;
    border: 1px solid var(--border-color);
    box-shadow: var(--shadow);
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
    min-width: 600px;
  }}

  th {{
    text-align: left;
    padding: 0.75rem 1rem;
    border-bottom: 2px solid var(--border-color);
    background: var(--bg-secondary);
    color: var(--text-secondary);
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    white-space: nowrap;
  }}

  td {{
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--border-color);
    font-size: 0.9rem;
  }}

  tr:last-child td {{
    border-bottom: none;
  }}

  tbody tr:hover {{
    background: var(--hover-bg);
  }}

  a {{
    color: var(--accent-color);
    text-decoration: none;
    font-weight: 500;
  }}

  a:hover {{
    text-decoration: underline;
    color: var(--accent-hover);
  }}

  .api-info {{
    margin-top: 2rem;
    padding: 1.25rem;
    background: var(--bg-secondary);
    border-radius: 8px;
    border: 1px solid var(--border-color);
    box-shadow: var(--shadow);
  }}

  .api-info strong {{
    display: block;
    margin-bottom: 0.5rem;
    color: var(--text-primary);
  }}

  .api-info code {{
    background: var(--code-bg);
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    font-size: 0.85rem;
    font-family: 'SF Mono', 'Fira Code', 'Fira Mono', Menlo, monospace;
  }}

  .api-info p {{
    margin: 0.3rem 0;
    color: var(--text-secondary);
  }}

  /* Responsive: card layout on small screens */
  @media (max-width: 768px) {{
    body {{
      padding: 1rem;
    }}

    h1 {{
      font-size: 1.5rem;
    }}

    .search {{
      max-width: 100%;
    }}

    .table-wrapper {{
      border: none;
      box-shadow: none;
      overflow-x: visible;
    }}

    table, thead, tbody, th, td, tr {{
      display: block;
    }}

    thead {{
      display: none;
    }}

    table {{
      min-width: unset;
    }}

    tbody tr {{
      margin-bottom: 1rem;
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 1rem;
      background: var(--bg-secondary);
      box-shadow: var(--shadow);
    }}

    tbody tr:hover {{
      background: var(--bg-tertiary);
    }}

    td {{
      padding: 0.3rem 0;
      border: none;
      font-size: 0.9rem;
    }}

    td:first-child {{
      font-size: 1.05rem;
      font-weight: 600;
      margin-bottom: 0.3rem;
    }}

    td:nth-child(2) {{
      color: var(--text-secondary);
      margin-bottom: 0.5rem;
    }}

    td:nth-child(3)::before {{
      content: "Version: ";
      color: var(--text-secondary);
      font-weight: 500;
    }}

    td:nth-child(4)::before {{
      content: "Authors: ";
      color: var(--text-secondary);
      font-weight: 500;
    }}

    td:nth-child(5)::before {{
      content: "License: ";
      color: var(--text-secondary);
      font-weight: 500;
    }}
  }}
</style>
</head>
<body>
<div class="container">
  <h1>OBCX Plugin Registry</h1>
  <p class="subtitle">{len(plugins)} plugin(s) available &middot;
     Updated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</p>

  <input type="text" class="search" placeholder="Search plugins..." id="search"
         oninput="filterTable()">

  <div class="table-wrapper">
    <table id="plugins-table">
    <thead>
    <tr><th>Name</th><th>Description</th><th>Version</th><th>Authors</th><th>License</th></tr>
    </thead>
    <tbody>{rows}
    </tbody>
    </table>
  </div>

  <!-- API Endpoints (TODO: enable when ready)
  <div class="api-info">
    <strong>API Endpoints</strong>
    <p>All plugins: <code><a href="index.json">index.json</a></code></p>
    <p>Single plugin: <code>plugins/&lt;name&gt;.json</code></p>
    <p>CLI: <code>obcx plugin search &lt;query&gt;</code></p>
  </div>
  -->
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
