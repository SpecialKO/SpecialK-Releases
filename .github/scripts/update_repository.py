#!/usr/bin/env python3
"""
Add a Special K version to SKIF's repository.json, or add update channels
("Branches") to a version that is already listed.

repository.json is maintained by hand, so it is edited as text rather than
re-serialised: a new entry is inserted at the top of "Main" -> "Versions" in
the file's own style (indentation, line endings, inline "Branches" array), and
a promotion only rewrites that one entry's "Branches" line. Everything else
stays byte-for-byte identical. The result is parsed again and compared with
the expected data before it is written, so a bad edit never reaches the CDN.

SKIF offers each user the top-most entry listed for their channel, so the
script refuses changes that would not take effect, or that would offer a
channel an older version than it already has.

Exit codes: 0 = written (or nothing to do, see --github-output), 1 = refused.
"""

import argparse
import copy
import difflib
import json
import re
import sys

CHANNEL_ORDER = ["Discord", "Website", "Ancient"]


def fail(msg):
    print(f"::error::{msg}", file=sys.stderr)
    sys.exit(1)


def version_key(name):
    """Compare like SKIF_Util_CompareVersionStrings: numeric, dot-separated."""
    parts = []
    for p in name.split("."):
        m = re.match(r"\d+", p)
        parts.append(int(m.group()) if m else 0)
    while parts and parts[-1] == 0:
        parts.pop()
    return parts


def order_channels(channels):
    known = [c for c in CHANNEL_ORDER if c in channels]
    return known + sorted(c for c in channels if c not in CHANNEL_ORDER)


def top_of(versions, channel, skip_index=None):
    for i, v in enumerate(versions):
        if i != skip_index and channel in v.get("Branches", []):
            return i, v
    return None, None


def jstr(s):
    # Match the file: raw UTF-8 (e.g. "™"), no escaped slashes
    return json.dumps(s, ensure_ascii=False)


def branches_inline(channels):
    return "[ " + ", ".join(jstr(c) for c in channels) + " ]"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--channels", required=True, help="Comma-separated, e.g. Discord,Website")
    ap.add_argument("--installer-url", required=True)
    ap.add_argument("--sha256", required=True)
    ap.add_argument("--description", required=True)
    ap.add_argument("--notes-file", help="Release notes (required when adding a new version)")
    ap.add_argument("--summary", help="Write a Markdown summary of the change here")
    ap.add_argument("--github-output", help="Append changed=true|false here")
    a = ap.parse_args()

    version = a.version.strip()
    if not re.fullmatch(r"\d+(\.\d+)+", version):
        fail(f"'{version}' does not look like a Special K version number")
    sha = a.sha256.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        fail("SHA256 must be 64 hex characters")
    channels = order_channels({c.strip() for c in a.channels.split(",") if c.strip()})
    if not channels:
        fail("No update channel selected")

    raw = open(a.input, "rb").read()
    if raw.startswith(b"\xef\xbb\xbf"):
        fail("repository.json starts with a UTF-8 BOM, which SKIF's parser may reject; fix the file first")
    try:
        text = raw.decode("utf-8")
        data = json.loads(text)
        versions = data["Main"]["Versions"]
        known_channels = [b["Name"] for b in data["Main"]["Branches"]]
    except (UnicodeDecodeError, ValueError, KeyError, TypeError) as e:
        fail(f"Current repository.json is not in the expected format: {e}")
    nl = "\r\n" if "\r\n" in text else "\n"

    unknown = [c for c in channels if c not in known_channels]
    if unknown:
        fail(f"Unknown channel(s) {unknown}; repository.json defines {known_channels}")

    expected = copy.deepcopy(data)
    matches = [i for i, v in enumerate(versions) if v.get("Name") == version]
    if len(matches) > 1:
        fail(f"{version} is listed {len(matches)} times in repository.json; fix that by hand first")

    changes = []

    if not matches:
        # ---- New version: insert at the top of "Versions" -------------------
        if not a.notes_file:
            fail(f"No release notes for {version}: the release has no ReleaseNotes.txt because SpecialK's "
                 f"CHANGELOG.txt had no section for {version} when it was built. Add the section and rebuild.")
        notes = open(a.notes_file, "rb").read().decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").rstrip()
        if not notes.strip():
            fail("The release notes file is empty")

        for c in channels:
            i, top = top_of(versions, c)
            if top and version_key(version) <= version_key(top["Name"]):
                fail(f"{c} currently offers {top['Name']}; publishing {version} there would offer users an older or equal version")
            changes.append(f"{c}: {top['Name'] if top else '(none)'} → **{version}**")

        entry = {
            "Name": version,
            "Description": a.description,
            "Branches": channels,
            "ReleaseNotes": notes,
            "Installer": a.installer_url,
            "SHA256": sha,
        }
        expected["Main"]["Versions"].insert(0, entry)

        m = re.search(r'"Versions"\s*:\s*\[(\r?\n)([ \t]*)\{(\r?\n)([ \t]*)"', text)
        if not m:
            fail('Could not find the start of the "Versions" list')
        outer, inner = m.group(2), m.group(4)
        lines = [f'{inner}{jstr(k)}: {branches_inline(v) if k == "Branches" else jstr(v)}' for k, v in entry.items()]
        block = f"{outer}{{{nl}" + f",{nl}".join(lines) + f"{nl}{outer}}},{nl}"
        pos = m.start(2)
        new_text = text[:pos] + block + text[pos:]
        action = f"Added **{version}** to {', '.join(channels)}"

    else:
        # ---- Existing version: add channels to it ---------------------------
        idx = matches[0]
        cur = versions[idx]
        if cur.get("Installer") != a.installer_url:
            fail(f"{version} is already listed with a different installer URL ({cur.get('Installer')})")
        if cur.get("SHA256") and cur["SHA256"].lower() != sha:
            fail(f"{version} is already listed with a different SHA256; refusing to swap the installer of a published version")

        add = [c for c in channels if c not in cur.get("Branches", [])]
        if not add:
            print(f"{version} is already published to {', '.join(channels)}; nothing to do.")
            if a.summary:
                open(a.summary, "w", encoding="utf-8").write(
                    f"### repository.json\n\n{version} is already published to {', '.join(channels)}. Nothing changed.\n")
            if a.github_output:
                open(a.github_output, "a").write("changed=false\n")
            return

        for c in add:
            i, top = top_of(versions, c, skip_index=idx)
            if top is not None and i < idx:
                fail(f"{c} would keep offering {top['Name']}, which is listed above {version}; SKIF uses the top-most entry of a channel")
            if top and version_key(version) <= version_key(top["Name"]):
                fail(f"{c} currently offers {top['Name']}; adding {version} would offer users an older or equal version")
            changes.append(f"{c}: {top['Name'] if top else '(none)'} → **{version}**")

        new_channels = order_channels(set(cur.get("Branches", [])) | set(add))
        expected["Main"]["Versions"][idx]["Branches"] = new_channels

        # Locate this entry's text: its "Name" line, then its own "Branches" array
        name_re = re.compile(r'"Name"\s*:\s*' + re.escape(jstr(version)) + r'\s*[,}]')
        found = list(name_re.finditer(text))
        vstart = text.find('"Versions"')
        found = [f for f in found if f.start() > vstart]
        if len(found) != 1:
            fail(f"Could not uniquely locate {version} in the file text")
        start = found[0].start()
        nxt = re.compile(r'"Name"\s*:').search(text, found[0].end())
        end = nxt.start() if nxt else len(text)
        br = re.compile(r'"Branches"\s*:\s*\[[^\]]*\]').search(text, start, end)
        if not br:
            fail(f'Could not find the "Branches" list of {version}')
        new_text = text[:br.start()] + '"Branches": ' + branches_inline(new_channels) + text[br.end():]
        action = f"Added {', '.join(add)} to existing version **{version}**"

        if a.notes_file:
            notes = open(a.notes_file, "rb").read().decode("utf-8-sig").replace("\r\n", "\n").rstrip()
            if notes != cur.get("ReleaseNotes", "").rstrip():
                print(f"::warning::Release notes differ from those already listed for {version}; the listed notes are kept.")

    # ---- Verify, then write ------------------------------------------------
    try:
        result = json.loads(new_text)
    except ValueError as e:
        fail(f"Internal error: the edited file is not valid JSON ({e})")
    if result != expected:
        fail("Internal error: the edited file does not match the intended change")

    open(a.output, "wb").write(new_text.encode("utf-8"))

    diff = "".join(difflib.unified_diff(
        text.replace("\r\n", "\n").splitlines(True), new_text.replace("\r\n", "\n").splitlines(True),
        "repository.json (current)", "repository.json (new)", n=2))
    if a.summary:
        with open(a.summary, "w", encoding="utf-8") as f:
            f.write(f"### repository.json\n\n{action}.\n\n")
            f.write("\n".join(f"- {c}" for c in changes) + "\n\n")
            f.write("```diff\n" + diff + "\n```\n")
    if a.github_output:
        open(a.github_output, "a").write("changed=true\n")
    print(action.replace("**", ""))
    print(diff)


if __name__ == "__main__":
    main()
