#!/usr/bin/env python3
"""
Find the previous installer release built from the same branch, and the
component versions it shipped.

Every release made by "Build Special K installer" carries a build-info.json
asset recording the branch it was built from and its component versions.
Releases made before that asset existed are recognised by their notes: the
branch is taken from the pre-release flag (pre-release = "pre-release",
otherwise "release") and the versions from the component table.

The newest non-draft release with a matching branch wins; the release being
built (--exclude-tag) is skipped so a rebuild never compares with itself.

Writes JSON: {"tag": ..., "branch": ..., "versions": {"SpecialK": ..., ...}},
or {} when there is no previous release for the branch.

Needs GITHUB_TOKEN (or GH_TOKEN) in the environment for API rate limits.
"""

import argparse
import json
import os
import re
import sys
import urllib.request

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")

# Component table rows in the release notes -> keys used in build-info.json
TABLE_NAMES = {
    "Special K": "SpecialK",
    "SKIF": "SKIF",
    "SKIFsvc": "SKIFsvc",
    "SKIV": "SKIV",
    "XInput_HID": "XInput_HID",
}
TABLE_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$", re.M)


def request(url, accept="application/vnd.github+json", auth=True):
    headers = {"Accept": accept, "User-Agent": "specialk-releases-workflow"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token and auth:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
        return r.read()


def list_releases(repo):
    releases, page = [], 1
    while True:
        batch = json.loads(request(f"{API}/repos/{repo}/releases?per_page=100&page={page}"))
        releases += batch
        if len(batch) < 100:
            return releases
        page += 1


def versions_from_body(body):
    versions = {}
    for name, value in TABLE_ROW.findall(body or ""):
        key = TABLE_NAMES.get(name)
        if key and value not in ("unknown", "Version"):
            versions[key] = value
    return versions


def describe(release):
    """(branch, versions) for a release, from build-info.json or its notes."""
    for asset in release.get("assets", []):
        if asset.get("name") == "build-info.json":
            # Public download URL: it redirects to storage that rejects a
            # forwarded API token, so it is fetched without one
            info = json.loads(request(asset["browser_download_url"], accept="application/octet-stream", auth=False))
            return info.get("branch"), info.get("versions", {})
    branch = "pre-release" if release.get("prerelease") else "release"
    return branch, versions_from_body(release.get("body"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--branch", required=True, help="Branch being built, e.g. release or pre-release")
    ap.add_argument("--exclude-tag", required=True, help="Tag of the release being built")
    ap.add_argument("--output", required=True)
    a = ap.parse_args()

    releases = [r for r in list_releases(a.repo) if not r.get("draft") and r.get("tag_name") != a.exclude_tag]
    releases.sort(key=lambda r: r.get("created_at") or "", reverse=True)

    result = {}
    for r in releases:
        branch, versions = describe(r)
        if branch == a.branch:
            result = {"tag": r["tag_name"], "branch": branch, "versions": versions}
            break

    if result:
        print(f"Previous release built from '{a.branch}': {result['tag']}")
        for k, v in result["versions"].items():
            print(f"  {k:<11} {v}")
    else:
        print(f"No previous release built from '{a.branch}'.")
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 - report and let the workflow decide
        print(f"::error::Could not look up the previous release: {e}", file=sys.stderr)
        sys.exit(1)
