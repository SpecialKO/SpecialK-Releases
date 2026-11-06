#!/usr/bin/env python3
"""
Print the section of Special K's CHANGELOG.txt for one version.

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
    parts = [int(p) for p in name.split(".")]
    while parts and parts[-1] == 0:
        parts.pop()
    return parts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("changelog")
    ap.add_argument("version")
    ap.add_argument("--output", help="Write the section here (UTF-8, LF) instead of stdout")
    a = ap.parse_args()

    text = open(a.changelog, "rb").read().decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    want = version_key(a.version.strip())
    headings = list(HEADING.finditer(text))

    for i, h in enumerate(headings):
        if version_key(h.group(1)) == want:
            end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
            lines = text[h.end():end].split("\n")
            while lines and not lines[0].strip():
                lines.pop(0)
            while lines and not lines[-1].strip():
                lines.pop()
            section = "\n".join(l.rstrip() for l in lines)
            if not section:
                print(f"CHANGELOG.txt has an empty section for {a.version}", file=sys.stderr)
                sys.exit(2)
            if a.output:
                open(a.output, "w", encoding="utf-8", newline="\n").write(section + "\n")
            else:
                sys.stdout.write(section + "\n")
            return

    newest = headings[0].group(1) if headings else "(none)"
    print(f"CHANGELOG.txt has no section for {a.version} (newest section: {newest})", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
