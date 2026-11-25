#!/usr/bin/env python3
"""
Build the installer's release notes from the CHANGELOG.txt of Special K and of
each bundled component (SKIF, SKIV).

  * Special K: only the section for the version being built. Its author writes
    that section as a summary of everything since the previous release.
  * Components: every section newer than the version the previous release of
    the same branch shipped, up to and including the version being built,
    newest first. A component whose version has not changed gets no section (it is still
    bundled in the installer as always; this only concerns the notes).
    Without a previous release, only the current version's section is used.

When only Special K has changes, the output is that section as-is. Otherwise
each part gets its own heading, underlined with "-" so it stands apart from
the "=" line SKIF draws under each version's description:

    Special K 26.11.5
    -----------------
     + ...

    SKIF 1.4.2
    ----------
     + ...

Exit codes: 0 = written, 2 = Special K's CHANGELOG.txt has no (or an empty)
section for its version, so no release notes were written.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from changelog_section import find_section, parse_sections, read_text, version_key  # noqa: E402

DISPLAY = {"SpecialK": "Special K"}


def warn(msg):
    print(f"::warning::{msg}", file=sys.stderr)


def heading(title):
    return f"{title}\n{'-' * len(title)}"


def component_sections(name, changelog, current, previous):
    """([(version, body)], reason) for one component; reason explains an empty list."""
    if not current or current == "unknown":
        return [], "version unknown"
    if previous and version_key(current) == version_key(previous):
        return [], f"unchanged ({current})"
    if previous and version_key(current) < version_key(previous):
        warn(f"{name} {current} is older than {previous} in the previous release; no changelog sections are added for it.")
        return [], f"older than the previous release ({previous})"
    if not changelog or not os.path.isfile(changelog):
        warn(f"{name} has no CHANGELOG.txt; no changelog sections are added for it ({previous or '?'} -> {current}).")
        return [], "no CHANGELOG.txt"

    sections = parse_sections(read_text(changelog))
    cur = version_key(current)
    if previous:
        prev = version_key(previous)
        picked = [(v, b) for v, b in sections if prev < version_key(v) <= cur]
    else:
        body = find_section(sections, current)
        picked = [(current, body)] if body is not None else []

    # Only the top-most section of each version, and only non-empty ones
    seen, result = set(), []
    for v, b in picked:
        k = tuple(version_key(v))
        if k not in seen and b:
            seen.add(k)
            result.append((v, b))

    if not any(version_key(v) == cur for v, _ in result):
        warn(f"{name}'s CHANGELOG.txt has no section for {current}.")
    if not result:
        return [], f"no CHANGELOG.txt sections for {previous + ' -> ' if previous else ''}{current}"
    return result, None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--specialk", nargs=2, metavar=("CHANGELOG", "VERSION"), required=True)
    ap.add_argument("--component", nargs=3, action="append", default=[],
                    metavar=("NAME", "CHANGELOG", "VERSION"),
                    help="A component whose CHANGELOG.txt sections since the previous release are included")
    ap.add_argument("--previous", help="JSON from previous_release.py")
    ap.add_argument("--output", required=True)
    ap.add_argument("--summary", help="Write a Markdown list of which changelog sections went into the notes")
    a = ap.parse_args()

    previous = {}
    if a.previous and os.path.isfile(a.previous):
        previous = json.load(open(a.previous, encoding="utf-8")) or {}
    prev_versions = previous.get("versions", {})
    baseline = previous.get("tag")

    sk_changelog, sk_version = a.specialk
    sk_body = None
    if os.path.isfile(sk_changelog):
        sk_body = find_section(parse_sections(read_text(sk_changelog)), sk_version)
    if not sk_body:
        print(f"Special K's CHANGELOG.txt has no section for {sk_version}", file=sys.stderr)
        sys.exit(2)

    parts = []    # (title, body)
    summary = [f"- **Special K {sk_version}**: changelog included"]
    for name, changelog, current in a.component:
        title = DISPLAY.get(name, name)
        sections, reason = component_sections(title, changelog, current, prev_versions.get(name))
        if sections:
            for v, body in sections:
                parts.append((f"{title} {v}", body))
            summary.append(f"- **{title}**: {', '.join(v for v, _ in sections)}")
        else:
            summary.append(f"- **{title}**: no changelog entries, {reason}")

    if parts:
        text = "\n\n".join(f"{heading(t)}\n{b}" for t, b in [(f"Special K {sk_version}", sk_body)] + parts)
    else:
        text = sk_body
    open(a.output, "w", encoding="utf-8", newline="\n").write(text + "\n")

    base = f"compared with {baseline}" if baseline else "no previous release of this branch"
    print(f"Release notes ({base}):")
    print("\n".join(summary))
    if a.summary:
        open(a.summary, "w", encoding="utf-8").write(f"_Release notes {base}:_\n\n" + "\n".join(summary) + "\n")


if __name__ == "__main__":
    main()
