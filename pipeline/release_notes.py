"""Write the pull-request body for a wiki sync.

Compares the freshly built dist/guide.json against the committed one and
describes what actually changed, so the PR can be reviewed in a couple of
minutes instead of by reading a 1.2 MB diff.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WIKI = "https://oldschool.runescape.wiki"
MAX_LISTED = 40


def committed_guide(path: Path, ref: str) -> dict | None:
    rel = path.relative_to(REPO).as_posix()
    result = subprocess.run(
        ["git", "show", f"{ref}:{rel}"],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return json.loads(result.stdout)


def steps_by_id(guide: dict) -> dict[str, tuple[str, str]]:
    return {
        step["id"]: (section["title"], step["text"])
        for section in guide["sections"]
        for step in section["steps"]
    }


def bullet_list(rows: list[str]) -> list[str]:
    out = [f"- {row}" for row in rows[:MAX_LISTED]]
    if len(rows) > MAX_LISTED:
        out.append(f"- …and {len(rows) - MAX_LISTED} more")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--guide", type=Path, default=REPO / "dist" / "guide.json")
    ap.add_argument("--coverage", type=Path, default=REPO / "dist" / "coverage.json")
    ap.add_argument("--baseline", type=Path, default=REPO / "data" / "coverage-baseline.json")
    ap.add_argument("--merged", type=Path, default=REPO / "build" / "merged.json")
    ap.add_argument("--ref", default="HEAD")
    ap.add_argument("--out", type=Path, default=REPO / "build" / "pr-body.md")
    args = ap.parse_args()

    new = json.loads(args.guide.read_text(encoding="utf-8"))
    old = committed_guide(args.guide, args.ref)
    report = json.loads(args.coverage.read_text(encoding="utf-8"))
    baseline = (
        json.loads(args.baseline.read_text(encoding="utf-8"))
        if args.baseline.exists()
        else None
    )

    lines: list[str] = []
    old_revid = old.get("sourceRevid") if old else None
    new_revid = new.get("sourceRevid")

    lines.append(f"Wiki revision **{old_revid or '—'} → {new_revid}**.")
    if old_revid and new_revid:
        lines.append("")
        lines.append(
            f"[View the wiki diff]({WIKI}/w/index.php?type=revision"
            f"&diff={new_revid}&oldid={old_revid})"
        )

    lines += ["", "## Totals", "", "| | before | after |", "|---|---:|---:|"]
    for label, key in (("Sections", "sections"), ("Episodes", "episodes"), ("Steps", "totalSteps")):
        before = "—"
        if old:
            before = {
                "sections": len(old["sections"]),
                "episodes": len(old["episodes"]),
                "totalSteps": sum(len(s["steps"]) for s in old["sections"]),
            }[key]
        lines.append(f"| {label} | {before} | {report[key]} |")

    lines += ["", "## Coverage", "", "| metric | baseline | this build | delta |", "|---|---:|---:|---:|"]
    for key, value in report["pct"].items():
        before = baseline["pct"].get(key) if baseline else None
        if before is None:
            lines.append(f"| {key} | — | {value:.2f}% | — |")
        else:
            delta = value - before
            warn = " ⚠️" if delta < -2 else ""
            lines.append(f"| {key} | {before:.2f}% | {value:.2f}% | {delta:+.2f}{warn} |")

    if old:
        before_steps = steps_by_id(old)
        after_steps = steps_by_id(new)
        migrations = new.get("migrations", {})
        fresh = {o: n for o, n in migrations.items() if o in before_steps and o not in after_steps}

        added = [i for i in after_steps if i not in before_steps and i not in fresh.values()]
        removed = [i for i in before_steps if i not in after_steps and i not in fresh]

        lines += ["", "## Step changes", ""]
        lines.append(
            f"{len(added)} added · {len(removed)} removed · {len(fresh)} reworded"
        )

        if fresh:
            lines += ["", "### Reworded (progress migrates automatically)", ""]
            lines += bullet_list(
                [
                    f"**{before_steps[o][0]}** — `{before_steps[o][1][:90]}` → "
                    f"`{after_steps[n][1][:90]}`"
                    for o, n in fresh.items()
                    if n in after_steps
                ]
            )
        if added:
            lines += ["", "### Added", ""]
            lines += bullet_list(
                [f"**{after_steps[i][0]}** — {after_steps[i][1][:110]}" for i in added]
            )
        if removed:
            lines += ["", "### Removed", ""]
            lines += bullet_list(
                [f"**{before_steps[i][0]}** — {before_steps[i][1][:110]}" for i in removed]
            )

    if args.merged.exists():
        stale = json.loads(args.merged.read_text(encoding="utf-8")).get("staleOverrides", [])
        if stale:
            lines += [
                "",
                "## ⚠️ Overrides that no longer match a step",
                "",
                "The wiki text moved under these. Review `curated/overrides.yaml`:",
                "",
            ]
            lines += bullet_list([f"`{key}`" for key in stale])

    lines += [
        "",
        "---",
        "",
        "Generated by `.github/workflows/sync.yml`. Guide content © B0aty and OSRS "
        "Wiki contributors, CC BY-NC-SA.",
    ]

    body = "\n".join(lines) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(body, encoding="utf-8")

    # The body is UTF-8 and contains arrows and warning signs. A Windows console
    # defaults to cp1252 and would raise on them, so echo through a stream that
    # is explicitly UTF-8 rather than degrading the file to ASCII.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
