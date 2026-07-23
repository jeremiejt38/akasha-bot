#!/usr/bin/env python3
"""Auto-update README.md version badge and changelog from pyproject.toml.

Usage:
    python scripts/update_readme.py [entry...]

Without arguments, it just syncs the badge and the "← *actuel*" marker.
With arguments, each argument becomes a changelog entry for the current version.

Examples:
    python scripts/update_readme.py
    python scripts/update_readme.py "feat: add /poll command" "feat: poll live results"
"""
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
README = ROOT / "README.md"


def read_version() -> str:
    with PYPROJECT.open("rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


def parse_version(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    return tuple(int(p) for p in parts[:3])


def make_badge(version: str) -> str:
    return f"![Version](https://img.shields.io/badge/version-{version}-blue)"


def update_badge(content: str, version: str) -> str:
    badge = make_badge(version)
    return re.sub(
        r"^!\[Version\]\(https://img\.shields\.io/badge/version-[\d.]+-blue\)",
        badge,
        content,
        count=1,
        flags=re.MULTILINE,
    )


def update_changelog(content: str, version: str, entries: list[str]) -> str:
    major, minor, patch = parse_version(version)
    section_header = f"### v{major}.{minor}.x"
    marker = " ← *actuel*"

    # Remove marker from all sections first
    content = re.sub(
        r"^(### v\d+\.\d+\.x) ← \*actuel\*",
        r"\1",
        content,
        flags=re.MULTILINE,
    )

    # If the current section exists, mark it as current
    if re.search(rf"^{re.escape(section_header)}$", content, flags=re.MULTILINE):
        content = re.sub(
            rf"^({re.escape(section_header)})$",
            rf"\1{marker}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        # Create the new current section just before the first ### vX.Y.x section
        new_section_lines = [f"{section_header}{marker}", ""]
        for entry in entries:
            new_section_lines.append(f"- **{entry}**")
        if not entries:
            new_section_lines.append("- (no entry)")
        new_section_lines.append("")
        new_section = "\n".join(new_section_lines)

        match = re.search(r"^(### v\d+\.\d+\.x)\b", content, flags=re.MULTILINE)
        if match:
            insert_pos = match.start()
            content = content[:insert_pos] + new_section + "\n" + content[insert_pos:]
        else:
            content += "\n" + new_section

    # Add entries to the current section if any provided
    if entries:
        # Find the current section and its bullet list
        pattern = rf"^({re.escape(section_header)}{re.escape(marker)})\n+((?:- .*\n)*)"

        def add_entries(match: re.Match) -> str:
            existing = match.group(2)
            existing_lines = [line for line in existing.splitlines() if line.startswith("-")]
            existing_texts = {line[2:].strip().strip("*") for line in existing_lines}
            new_lines = list(existing_lines)
            for entry in entries:
                bullet = f"- **{entry}**"
                if entry.strip() not in existing_texts:
                    new_lines.append(bullet)
            body = "\n".join(new_lines) + "\n"
            return f"{match.group(1)}\n\n{body}"

        content = re.sub(pattern, add_entries, content, count=1, flags=re.MULTILINE)

    return content


def main():
    version = read_version()
    entries = sys.argv[1:]

    content = README.read_text(encoding="utf-8")
    content = update_badge(content, version)
    content = update_changelog(content, version, entries)
    README.write_text(content, encoding="utf-8")

    print(f"Updated README for version {version}")
    if entries:
        print(f"Added {len(entries)} changelog entries")


if __name__ == "__main__":
    main()
