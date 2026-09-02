"""Stage 3g: record a content hash for every guide screenshot.

Writes build/images.json: url -> {sha256, bytes}. The plugin refuses to display
an image whose bytes do not match, which closes the gap the host allowlist
leaves open.

What this actually protects against
-----------------------------------
The screenshots are hotlinked from i.ibb.co, a public image host, and their
links come from a wiki page anyone can edit. Checking the host stops a link
being pointed at some other server, but not at different content on the same
one.

Two ways that could go wrong, and what closes each:

  * The wiki link is edited to a different image. The plugin only ever requests
    URLs that were in guide.json when it was built, so this cannot reach a
    player until a build picks it up -- and this stage makes the change visible
    in the build report rather than silent.
  * The bytes behind an unchanged URL are replaced. Nothing at build time can
    see that later, so the hash travels with the guide and the plugin checks it
    when the image arrives.

Neither is a large risk. The failure is an unpleasant picture in a sidebar, not
code execution. But it is somebody else's server showing images to every player
who installs this, and that is worth a hash.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

USER_AGENT = "b0aty-guide-data/0.1 (https://github.com/previns/b0aty-guide-data)"
ALLOWED_HOST = "i.ibb.co"
MAX_BYTES = 4 * 1024 * 1024


def image_urls(guide: dict) -> list[str]:
    seen: list[str] = []
    for section in guide.get("sections", []):
        for url in section.get("imageUrls", []) or []:
            if url not in seen:
                seen.append(url)
    return seen


def fetch(url: str, timeout: int = 45) -> bytes | None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(MAX_BYTES + 1)
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"  could not fetch {url}: {e}", file=sys.stderr)
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--guide", type=Path, default=REPO / "dist" / "guide.json")
    ap.add_argument("--out", type=Path, default=REPO / "build" / "images.json")
    ap.add_argument("--delay", type=float, default=0.2)
    args = ap.parse_args()

    guide = json.loads(args.guide.read_text(encoding="utf-8"))
    urls = image_urls(guide)

    previous: dict = {}
    if args.out.exists():
        previous = json.loads(args.out.read_text(encoding="utf-8")).get("images", {})

    images: dict[str, dict] = {}
    failed: list[str] = []
    rejected: list[str] = []
    changed: list[str] = []

    for index, url in enumerate(urls, start=1):
        # Belt and braces: the plugin checks this too, but a rejected host
        # should never reach the shipped file in the first place.
        if not url.startswith(f"https://{ALLOWED_HOST}/"):
            rejected.append(url)
            continue

        body = fetch(url)
        if body is None or len(body) > MAX_BYTES:
            failed.append(url)
            continue

        digest = hashlib.sha256(body).hexdigest()
        if url in previous and previous[url]["sha256"] != digest:
            changed.append(url)
        images[url] = {"sha256": digest, "bytes": len(body)}

        if index % 25 == 0:
            print(f"  hashed {index}/{len(urls)}", flush=True)
        time.sleep(args.delay)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"images": images}, indent=1), encoding="utf-8")

    total = sum(v["bytes"] for v in images.values())
    print(f"\nimages         {len(urls):5}")
    print(f"  hashed       {len(images):5}  ({total / 1024 / 1024:.1f} MiB fetched)")
    if failed:
        print(f"  unreachable  {len(failed):5}")
    if rejected:
        print(f"  WRONG HOST   {len(rejected):5}")
        for url in rejected:
            print(f"     {url}")
    if changed:
        # Not an error: the guide's author re-uploads screenshots. It is worth
        # a person's glance, which is the whole point of printing it.
        print(f"\n  CONTENT CHANGED at {len(changed)} url(s) since the last run:")
        for url in changed:
            print(f"     {url}")

    print(f"\nwrote {args.out}")
    return 1 if rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
