#!/usr/bin/env python3
"""
Print the section of a CHANGELOG.txt (Special K, SKIF, SKIV) for one version.

CHANGELOG.txt lists versions newest first, each as a heading underlined
with "=" and followed by its entries:

    26.11.4.1
    =========
     + Validate the correct memory address ...

The section is the text between that heading and the next one, with blank
lines trimmed from both ends. Versions are matched numerically, so 26.11.4
and 26.11.4.0 are the same version. A heading may carry text after the
version, e.g. "24.10.22 (HOTFIX)". If a version appears more than once, the
top-most (newest) section is used.

Exit codes: 0 = section written, 2 = version not found or section empty.
"""

import argparse
import re
import sys

HEADING = re.compile(r"^(\d+(?:\.\d+)+)(?:[^\S\n][^\n]*)?\n=+[^\S\n]*$", re.M)


def version_key(name):
    parts = []
    for p in name.strip().split("."):
        m = re.match(r"\d+", p)
        parts.append(int(m.group()) if m else 0)
    while parts and parts[-1] == 0:
        parts.pop()
    return parts


def read_text(path):
    return open(path, "rb").read().decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")


def parse_sections(text):
    """[(version, body)] in file order (newest first); body has blank edge lines trimmed."""
    headings = list(HEADING.finditer(text))
    sections = []
    for i, h in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        lines = text[h.end():end].split("\n")
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        sections.append((h.group(1), "\n".join(l.rstrip() for l in lines)))
    return sections


def find_section(sections, version):
    """Body of the top-most section for version, or None if there is none."""
    want = version_key(version)
    for name, body in sections:
        if version_key(name) == want:
            return body
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("changelog")
    ap.add_argument("version")
    ap.add_argument("--output", help="Write the section here (UTF-8, LF) instead of stdout")
    a = ap.parse_args()

    sections = parse_sections(read_text(a.changelog))
    section = find_section(sections, a.version)
    if section is None:
        newest = sections[0][0] if sections else "(none)"
        print(f"CHANGELOG.txt has no section for {a.version} (newest section: {newest})", file=sys.stderr)
        sys.exit(2)
    if not section:
        print(f"CHANGELOG.txt has an empty section for {a.version}", file=sys.stderr)
        sys.exit(2)
    if a.output:
        open(a.output, "w", encoding="utf-8", newline="\n").write(section + "\n")
    else:
        sys.stdout.write(section + "\n")


if __name__ == "__main__":
    main()
