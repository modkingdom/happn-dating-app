"""
Reads settings.toml and:
  1. Auto-fills release_date with today if empty
  2. Picks a random unused Bing account from bing-accs.txt
  3. Creates overrides/main.html with Bing meta tag
  4. Creates docs/BingSiteAuth.xml
  5. Replaces <<<PLACEHOLDER>>> values in base docs and mkdocs.yml
  6. Creates stub .md files for each keyword in additional_pages
  7. Adds additional pages to mkdocs.yml nav (<<<ADDITIONAL_NAV>>>)
  8. Adds additional page links to index.md nav table (<<<ADDITIONAL_NAV_TABLE>>>)
  9. Appends entry to publish-log.txt
 10. Reports remaining unfilled placeholders

Run once after copying the template: python setup.py
Re-running is safe — existing stubs and Bing assignment are not overwritten.
"""

import sys
import os
import re
import random
import subprocess
from datetime import date
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit("Python 3.11+ required (uses built-in tomllib).")

import tomllib


# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_DIR  = Path(__file__).parent
READTHEDOCS_ROOT = (PROJECT_DIR / "../../..").resolve()
BING_ACCS_FILE   = READTHEDOCS_ROOT / "bing-accs.txt"
LOG_FILE         = READTHEDOCS_ROOT / "publish-log.txt"


# ── Helpers ───────────────────────────────────────────────────────────────────

def slug(keyword: str) -> str:
    return re.sub(r"\s+", "-", keyword.strip().lower())


def nav_title(keyword: str) -> str:
    return keyword.strip().title()


# ── Settings ──────────────────────────────────────────────────────────────────

def load_settings(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def autofill_release_date(settings_path: Path, p: dict) -> str:
    release_date = p.get("release_date", "").strip()
    if not release_date:
        release_date = date.today().isoformat()
        raw = settings_path.read_text(encoding="utf-8")
        raw = re.sub(r'(release_date\s*=\s*)"[^"]*"', f'\\1"{release_date}"', raw)
        settings_path.write_text(raw, encoding="utf-8")
        print(f"Auto-filled release_date = {release_date}")
    return release_date


def load_theme(project_dir: Path) -> dict:
    theme_path = (project_dir / "../theme.toml").resolve()
    defaults = {"primary": "indigo", "accent": "indigo", "icon": "article"}
    if not theme_path.exists():
        return defaults
    with open(theme_path, "rb") as f:
        t = tomllib.load(f)
    return {**defaults, **t}


def build_replacements(p: dict, release_date: str, bing_code: str, theme: dict) -> dict:
    repo_name = Path(os.getcwd()).name
    return {
        "<<<APP_NAME>>>":                       p["app_name"],
        "<<<SHORT_DESCRIPTION>>>":              p.get("short_description", ""),
        "<<<META_DESCRIPTION_150_300_CHARS>>>": p.get("meta_description", ""),
        "<<<MAIN_KEYWORD>>>":                   p["main_keyword"],
        "<<<RELEASE_DATE>>>":                   release_date,
        "<<<REPO_NAME>>>":                      repo_name,
        "<<<RTFD_SLUG>>>":                      repo_name,
        "<<<BING_VALIDATION_CODE>>>":           bing_code,
        "<<<THEME_PRIMARY>>>":                  theme["primary"],
        "<<<THEME_ACCENT>>>":                   theme["accent"],
        "<<<THEME_ICON>>>":                     theme["icon"],
    }


def validate(replacements: dict) -> list[str]:
    skip = {"<<<BING_VALIDATION_CODE>>>"}
    return [k for k, v in replacements.items() if k not in skip and not v.strip()]


# ── Bing accounts ─────────────────────────────────────────────────────────────

def load_bing_accounts(path: Path) -> list[dict]:
    if not path.exists():
        return []
    accounts = []
    for line in path.read_text(encoding="utf-8").strip().splitlines()[1:]:  # skip header
        parts = line.strip().split(";")
        if len(parts) >= 2:
            accounts.append({
                "email":           parts[0],
                "validation_code": parts[1],
                "api_key":         parts[2] if len(parts) > 2 else "",
            })
    return accounts


def load_used_bing_emails(log_path: Path) -> set[str]:
    if not log_path.exists():
        return set()
    used = set()
    for line in log_path.read_text(encoding="utf-8").splitlines():
        parts = line.split(";")
        if len(parts) >= 6:
            used.add(parts[5].strip())  # bing_email is field index 5
    return used


def pick_bing_account(path: Path) -> dict | None:
    accounts = load_bing_accounts(path)
    if not accounts:
        return None
    used = load_used_bing_emails(LOG_FILE)
    available = [a for a in accounts if a["email"] not in used]
    if not available:
        print("WARNING: all Bing accounts already used. Picking a random one anyway.")
        return random.choice(accounts)
    return random.choice(available)


def load_project_bing_code(project_dir: Path) -> str | None:
    """Return Bing code already assigned to this project (from overrides/main.html)."""
    html = project_dir / "overrides" / "main.html"
    if not html.exists():
        return None
    m = re.search(r'msvalidate\.01["\s]+content="([^"]+)"', html.read_text(encoding="utf-8"))
    return m.group(1) if m else None


# ── File operations ───────────────────────────────────────────────────────────

def replace_in_file(path: Path, replacements: dict) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


# ── Additional pages ──────────────────────────────────────────────────────────

def make_stub(keyword: str, app_name: str, main_keyword: str, all_keywords: list[str]) -> str:
    title = nav_title(keyword)
    other_rows = "\n".join(
        f"| [{nav_title(kw)}]({slug(kw)}.md) | {app_name} on {nav_title(kw).split()[-1]} |"
        for kw in all_keywords if kw != keyword
    )
    return f"""---
description: <!-- 150-300 chars about {title} for {app_name} — fill with LLM -->
---

# {title}

<!-- LLM PROMPT:
     Write 2-3 paragraphs about using {app_name} on {keyword}.
     Target keyword: "{keyword}". Also include "{main_keyword}" naturally.
     Audience: someone searching for "{keyword}" who wants to download or use the app. -->

## How to Use {app_name} on {nav_title(keyword).split()[-1]}

<!-- LLM: Step-by-step guide specific to this platform/context. 4-6 steps. -->

## Frequently Asked Questions

<!-- LLM: 3-5 Q&A pairs specific to "{keyword}". -->

---

## See Also

| Page | What you'll find |
|------|-----------------|
| [Home](index.md) | {app_name} overview |
| [Features](features.md) | Full list of features |
| [How to Download](how-to-download.md) | Download and setup guide |
| [FAQ](faq.md) | General FAQ |
{other_rows}
"""


def create_additional_pages(docs_dir: Path, additional_pages: list[str],
                             app_name: str, main_keyword: str) -> list[str]:
    created = []
    for kw in additional_pages:
        page_path = docs_dir / f"{slug(kw)}.md"
        if not page_path.exists():
            page_path.write_text(make_stub(kw, app_name, main_keyword, additional_pages), encoding="utf-8")
            created.append(page_path.name)
    return created


# ── Nav injection ─────────────────────────────────────────────────────────────

def inject_nav(mkdocs_path: Path, additional_pages: list[str]) -> bool:
    text = mkdocs_path.read_text(encoding="utf-8")
    if "<<<ADDITIONAL_NAV>>>" not in text:
        return False
    nav_lines = "\n".join(f"  - {nav_title(kw)}: {slug(kw)}.md" for kw in additional_pages)
    mkdocs_path.write_text(text.replace("<<<ADDITIONAL_NAV>>>", nav_lines), encoding="utf-8")
    return True


def inject_nav_table(index_path: Path, additional_pages: list[str]) -> bool:
    text = index_path.read_text(encoding="utf-8")
    if "<<<ADDITIONAL_NAV_TABLE>>>" not in text:
        return False
    rows = "\n".join(
        f"| [{nav_title(kw)}]({slug(kw)}.md) | Platform-specific guide |"
        for kw in additional_pages
    )
    index_path.write_text(text.replace("<<<ADDITIONAL_NAV_TABLE>>>", rows), encoding="utf-8")
    return True


# ── Logging ───────────────────────────────────────────────────────────────────

def append_log(p: dict, release_date: str, repo_name: str,
               github_email: str, bing: dict) -> None:
    entry = ";".join([
        release_date,
        p["app_name"],
        p["main_keyword"],
        repo_name,
        github_email,
        bing["email"],
        bing["validation_code"],
    ])
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry + "\n")
    print(f"Logged → {LOG_FILE.name}")


def load_github_email(project_dir: Path) -> str:
    creds = project_dir / "../.gh-credentials"
    if creds.exists():
        for line in creds.read_text().splitlines():
            if line.startswith("GITHUB_EMAIL="):
                return line.split("=", 1)[1].strip()
    return ""


# ── Main ──────────────────────────────────────────────────────────────────────

BASE_FILES = [
    "mkdocs.yml",
    "overrides/main.html",
    "docs/js/tracker.js",
    "docs/BingSiteAuth.xml",
    "docs/index.md",
    "docs/features.md",
    "docs/how-to-download.md",
    "docs/faq.md",
]


def main():
    root = Path(__file__).parent
    settings_path = root / "settings.toml"

    if not settings_path.exists():
        sys.exit("ERROR: settings.toml not found.")

    settings = load_settings(settings_path)
    p = settings["project"]
    additional_pages = p.get("additional_pages") or settings.get("additional_pages", [])

    # 1. Auto-fill release_date
    release_date = autofill_release_date(settings_path, p)

    # 2. Assign Bing account (skip if already assigned)
    existing_code = load_project_bing_code(root)
    if existing_code and "<<<" not in existing_code:
        bing = {"email": "already assigned", "validation_code": existing_code, "api_key": ""}
        print(f"Bing account already assigned: {existing_code[:8]}...")
    else:
        bing = pick_bing_account(BING_ACCS_FILE)
        if not bing:
            print("WARNING: bing-accs.txt not found or empty — skipping Bing verification.")
            bing = {"email": "", "validation_code": "", "api_key": ""}
        else:
            print(f"Assigned Bing account: {bing['email']}")

    # 3. Ensure overrides/ dir exists and create main.html if missing
    overrides_dir = root / "overrides"
    overrides_dir.mkdir(exist_ok=True)
    main_html = overrides_dir / "main.html"
    if not main_html.exists():
        main_html.write_text(
            '{% extends "base.html" %}\n\n'
            '{% block extrahead %}\n'
            '{{ super() }}\n'
            '<meta name="msvalidate.01" content="<<<BING_VALIDATION_CODE>>>">\n'
            '{% endblock %}\n',
            encoding="utf-8"
        )

    # 4. Ensure docs/BingSiteAuth.xml exists
    xml_path = root / "docs" / "BingSiteAuth.xml"
    if not xml_path.exists():
        xml_path.write_text(
            '<?xml version="1.0"?>\n<users>\n  <user><<<BING_VALIDATION_CODE>>></user>\n</users>\n',
            encoding="utf-8"
        )

    # 5. Build replacements and validate
    theme = load_theme(root)
    replacements = build_replacements(p, release_date, bing["validation_code"], theme)
    empty = validate(replacements)
    if empty:
        print("WARNING: empty fields in settings.toml:")
        for k in empty:
            print(f"  {k}")
        print()

    # 6. Create additional page stubs
    docs_dir = root / "docs"
    if additional_pages:
        created = create_additional_pages(docs_dir, additional_pages, p["app_name"], p["main_keyword"])
        if created:
            print("Created stubs:")
            for f in created:
                print(f"  docs/{f}")

    # 7. Inject nav into mkdocs.yml
    if additional_pages and inject_nav(root / "mkdocs.yml", additional_pages):
        print("Updated mkdocs.yml nav.")

    # 8. Inject nav table into index.md
    if additional_pages and inject_nav_table(docs_dir / "index.md", additional_pages):
        print("Updated index.md Quick Navigation table.")

    # 9. Replace placeholders in all files
    target_files = BASE_FILES + [f"docs/{slug(kw)}.md" for kw in additional_pages]
    changed = []
    for rel in target_files:
        path = root / rel
        if not path.exists():
            print(f"SKIP (not found): {rel}")
            continue
        if replace_in_file(path, replacements):
            changed.append(rel)

    if changed:
        print("Placeholders replaced in:")
        for f in changed:
            print(f"  {f}")
    else:
        print("Nothing to replace — all placeholders already filled.")

    # 10. Write log entry (only if Bing was freshly assigned)
    repo_name = root.name
    github_email = load_github_email(root)
    if bing["email"] and bing["email"] != "already assigned":
        append_log(p, release_date, repo_name, github_email, bing)

    # 11. Check for remaining placeholders
    all_files = list(docs_dir.glob("*.md")) + [root / "mkdocs.yml", root / "overrides/main.html"]
    remaining = []
    for path in all_files:
        if path.exists():
            found = re.findall(r"<<<\w+>>>", path.read_text(encoding="utf-8"))
            if found:
                remaining.append((path.relative_to(root), sorted(set(found))))

    if remaining:
        print("\nRemaining placeholders — running generate.py...")
    else:
        print("\nAll structural placeholders filled — running generate.py...")

    # ── 12. Run generate.py ───────────────────────────────────────────────────
    venv_python  = READTHEDOCS_ROOT / ".venv" / "bin" / "python"
    generate_script = READTHEDOCS_ROOT / "generate.py"

    if not generate_script.exists():
        print(f"SKIP: generate.py not found at {generate_script}")
    elif not venv_python.exists():
        print(f"SKIP: venv not found at {venv_python}")
        print("      Create it: python -m venv .venv && .venv/bin/pip install openai")
    else:
        print()
        subprocess.run([str(venv_python), str(generate_script), str(root)], check=True)


if __name__ == "__main__":
    main()
