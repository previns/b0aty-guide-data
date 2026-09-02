"""Stage 1: pull the guide wikitext from the OSRS Wiki.

Writes build/wikitext.json — the raw wikitext plus the revid and fetch time.
Nothing else in the pipeline talks to the network.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://oldschool.runescape.wiki/api.php"
DEFAULT_PAGE = "Guide:B0aty HCIM Guide V3"

# The wiki asks automated clients to identify themselves.
USER_AGENT = "b0aty-guide-data/0.1 (https://github.com/previns/b0aty-guide-data)"

REPO = Path(__file__).resolve().parent.parent


def fetch_wikitext(page: str) -> dict:
    params = {
        "action": "parse",
        "page": page,
        "prop": "wikitext|revid",
        "format": "json",
        "formatversion": "2",
    }
    url = f"{API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    if "error" in payload:
        raise SystemExit(f"wiki API error: {payload['error']}")

    parse = payload["parse"]
    return {
        "page": page,
        "revid": parse["revid"],
        # When the page was last EDITED, which is what "how current is this
        # guide" actually asks. fetchedAt only says when we looked: if nobody
        # has touched the page in three months, it reads as today while the
        # content is three months old.
        "revisionAt": revision_timestamp(page, parse["revid"]),
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "wikitext": parse["wikitext"],
    }


def revision_timestamp(page: str, revid: int) -> str | None:
    """When the wiki last edited this page. None if the API will not say."""
    params = {
        "action": "query",
        "prop": "revisions",
        "titles": page,
        "rvprop": "timestamp|ids",
        "rvlimit": "1",
        "format": "json",
        "formatversion": "2",
    }
    url = f"{API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        for entry in payload["query"]["pages"]:
            for revision in entry.get("revisions", []):
                return revision.get("timestamp")
    except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
        # Not worth failing a build over: the guide is still correct, it just
        # cannot say how old it is.
        print(f"  could not read the revision timestamp: {e}", file=sys.stderr)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--page", default=DEFAULT_PAGE)
    ap.add_argument("--out", type=Path, default=REPO / "build" / "wikitext.json")
    ap.add_argument(
        "--if-changed-from",
        type=Path,
        default=None,
        help="exit 3 without writing when the live revid matches this file's revid",
    )
    args = ap.parse_args()

    doc = fetch_wikitext(args.page)

    if args.if_changed_from and args.if_changed_from.exists():
        previous = json.loads(args.if_changed_from.read_text(encoding="utf-8"))
        if previous.get("revid") == doc["revid"]:
            print(f"revid {doc['revid']} unchanged; nothing to do")
            return 3

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"page      {doc['page']}")
    print(f"revid     {doc['revid']}")
    print(f"fetched   {doc['fetchedAt']}")
    print(f"wikitext  {len(doc['wikitext'])} chars")
    print(f"wrote     {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
