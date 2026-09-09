"""Stage 2: wikitext -> ordered episodes / sections / steps, with stable IDs.

Reads build/wikitext.json (or a fixture with --fixture) and writes build/parsed.json.

This stage does not interpret step text at all. It preserves [[...]] markup
verbatim for the annotate stage. Its only job is to get the *structure* right,
which is harder than it looks -- see docs/wikitext-traps.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# --- line classification -----------------------------------------------------

RE_CHECKLIST_OPEN = re.compile(r"^\{\{\s*Checklist\s*\|\s*title\s*=(?P<rest>.*)$", re.I)
RE_CLOSE = re.compile(r"^\}\}\s*$")
RE_STEP = re.compile(r"^(?P<bullet>\*+)\s?(?P<text>.*)$")
RE_EXTIMAGE = re.compile(r"^\{\{\s*Extimage\s*\|(?P<url>[^|}]+)", re.I)
RE_YOUTUBE = re.compile(r"^\{\{\s*Youtube\s*\|(?P<id>[^|}]+)", re.I)
RE_HEADING = re.compile(r"^(?P<level>=+)\s*(?P<title>.+?)\s*(?P=level)\s*$")
RE_COMMENT = re.compile(r"^<!--(?P<body>.*?)-->\s*$")
RE_BANK_COMMENT = re.compile(r"^\s*Bank\s*(?P<num>\d+)(?P<suffix>[A-Z]?)\s*$", re.I)
RE_EPISODE = re.compile(r"^Episode\s+(?P<num>\d+)\b", re.I)
RE_END_OF_EPISODE = re.compile(r"^End of (Episode\s*\d+|Series)\b", re.I)

# --- {{Var}} / {{#expr}} bank counter ---------------------------------------

RE_VAR_SET_LITERAL = re.compile(
    r"\{\{\s*Var\s*\|\s*(?P<name>\w+)\s*\|\s*(?P<value>\d+)\s*\}\}", re.I
)
RE_VAR_SET_INCREMENT = re.compile(
    r"\{\{\s*Var\s*\|\s*(?P<name>\w+)\s*\|\s*\{\{\s*#expr\s*:\s*\{\{\s*#var\s*:\s*(?P<src>\w+)\s*\}\}\s*(?P<op>[+-])\s*(?P<delta>\d+)\s*\}\}\s*\}\}",
    re.I,
)
# "Bank {{#expr:{{#var:bankNumber}}+1}}A"  ->  prefix, var, delta, suffix
RE_TITLE_EXPR = re.compile(
    r"\{\{\s*#expr\s*:\s*\{\{\s*#var\s*:\s*(?P<src>\w+)\s*\}\}\s*(?P<op>[+-])\s*(?P<delta>\d+)\s*\}\}",
    re.I,
)


def slugify(text: str) -> str:
    text = re.sub(r"\[\[([^\]|]*\|)?([^\]]*)\]\]", r"\2", text)
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text or "section"


def normalize_for_id(text: str) -> str:
    """Lowercase, strip wiki-link syntax, collapse whitespace.

    Used only for hashing. Deliberately lossy so that a link being added or
    removed around an unchanged name does not renumber a player's progress.
    """
    text = re.sub(r"\[\[([^\]|]*\|)?([^\]]*)\]\]", r"\2", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def step_id(section_slug: str, text: str, collision: int = 0) -> str:
    key = f"{section_slug}|{normalize_for_id(text)}"
    if collision:
        key = f"{key}#{collision}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


class Parser:
    def __init__(self, wikitext: str):
        # The page is CRLF. Normalise once, here, and nowhere else.
        self.lines = wikitext.replace("\r\n", "\n").split("\n")
        self.warnings: list[dict] = []
        self.variables: dict[str, int] = {}
        self.episodes: list[dict] = []
        self.sections: list[dict] = []
        self.preamble: list[str] = []
        # Buffers that attach forward to the next section.
        self.pending_images: list[str] = []
        self.pending_bank_comment: str | None = None
        self.current_episode: int | None = None
        self.seen_slugs: dict[str, int] = {}

    # -- warnings ------------------------------------------------------------

    def warn(self, code: str, line: int, detail: str) -> None:
        self.warnings.append({"code": code, "line": line, "detail": detail})

    # -- variable handling ---------------------------------------------------

    def apply_var_assignments(self, line: str) -> None:
        for m in RE_VAR_SET_INCREMENT.finditer(line):
            src = m.group("src")
            delta = int(m.group("delta")) * (1 if m.group("op") == "+" else -1)
            self.variables[m.group("name")] = self.variables.get(src, 0) + delta
        for m in RE_VAR_SET_LITERAL.finditer(line):
            self.variables[m.group("name")] = int(m.group("value"))

    def resolve_title(self, raw_title: str) -> str:
        def sub(m: re.Match) -> str:
            base = self.variables.get(m.group("src"), 0)
            delta = int(m.group("delta")) * (1 if m.group("op") == "+" else -1)
            return str(base + delta)

        return RE_TITLE_EXPR.sub(sub, raw_title).strip()

    # -- main walk -----------------------------------------------------------

    def parse(self) -> dict:
        i = 0
        n = len(self.lines)
        while i < n:
            line = self.lines[i]
            stripped = line.strip()

            m = RE_CHECKLIST_OPEN.match(stripped)
            if m:
                i = self.parse_checklist(i, m)
                continue

            m = RE_HEADING.match(stripped)
            if m:
                self.handle_heading(m, i)
                i += 1
                continue

            m = RE_EXTIMAGE.match(stripped)
            if m:
                # Every Extimage in this page sits immediately before the
                # checklist it illustrates, so it attaches forward.
                self.pending_images.append(m.group("url").strip())
                i += 1
                continue

            m = RE_YOUTUBE.match(stripped)
            if m:
                self.attach_video(m.group("id").strip(), i)
                i += 1
                continue

            m = RE_COMMENT.match(stripped)
            if m:
                body = m.group("body")
                if RE_BANK_COMMENT.match(body):
                    self.pending_bank_comment = body.strip()
                i += 1
                continue

            if "{{Var" in stripped:
                self.apply_var_assignments(stripped)
                i += 1
                continue

            if stripped and not stripped.startswith("{{"):
                self.handle_loose_line(stripped, i)

            i += 1

        self.finalise_episodes()
        return self.document()

    def handle_loose_line(self, stripped: str, line_no: int) -> None:
        """Prose and stray bullets that sit outside any {{Checklist}} block.

        Before the first section they are the guide's preamble. After it, a
        stray "* ..." line is a trailing note on the section that just closed --
        usually a safespot link, and usually followed by a {{Youtube}} that
        needs to anchor to it.
        """
        if RE_END_OF_EPISODE.match(stripped):
            if self.episodes:
                self.episodes[-1]["endMarkerLine"] = line_no + 1
            return

        if stripped.startswith("*") and self.sections:
            section = self.sections[-1]
            text = RE_STEP.match(stripped).group("text").strip()
            if not text:
                return
            section["steps"].append(
                {
                    "id": step_id(section["slug"], text),
                    "ordinal": len(section["steps"]),
                    "depth": 1,
                    "kind": "trailing-note",
                    "raw": text,
                    "videoIds": [],
                    "sourceLine": line_no + 1,
                }
            )
            self.warn("trailing_note", line_no + 1, f"bullet outside a block -> {section['title']}")
            return

        self.preamble.append(stripped)

    def handle_heading(self, m: re.Match, line_no: int) -> None:
        title = m.group("title").strip()
        ep = RE_EPISODE.match(re.sub(r"\[\[([^\]|]*\|)?([^\]]*)\]\]", r"\2", title))
        if ep:
            self.current_episode = int(ep.group("num"))
            self.episodes.append(
                {
                    "ordinal": self.current_episode,
                    "title": title,
                    "videoIds": [],
                    "sectionIds": [],
                    "sourceLine": line_no + 1,
                }
            )

    def attach_video(self, video_id: str, line_no: int) -> None:
        """Videos attach backwards: to the episode heading or the last step."""
        prev = self.previous_meaningful_line(line_no)
        if prev is not None and RE_HEADING.match(self.lines[prev].strip()):
            if self.episodes:
                self.episodes[-1]["videoIds"].append(video_id)
                return
        if self.sections and self.sections[-1]["steps"]:
            self.sections[-1]["steps"][-1]["videoIds"].append(video_id)
            return
        if self.episodes:
            self.episodes[-1]["videoIds"].append(video_id)
        else:
            self.warn("orphan_video", line_no + 1, f"video {video_id} has no anchor")

    def previous_meaningful_line(self, line_no: int) -> int | None:
        j = line_no - 1
        while j >= 0 and not self.lines[j].strip():
            j -= 1
        return j if j >= 0 else None

    # -- checklist blocks ----------------------------------------------------

    def parse_checklist(self, start: int, open_match: re.Match) -> int:
        """Consume one {{Checklist}} block. Returns the next line index.

        Two blocks on the live page are never closed. Recover by stopping at the
        next structural line rather than running to end of document.
        """
        rest = open_match.group("rest")
        raw_title, _, inline = rest.partition("|")
        resolved_title = self.resolve_title(raw_title)

        steps_raw: list[tuple[int, str]] = []
        if inline.strip().startswith("*"):
            steps_raw.append((start, inline.strip()))

        i = start + 1
        terminated = False
        n = len(self.lines)
        while i < n:
            line = self.lines[i]
            stripped = line.strip()

            if RE_CLOSE.match(stripped):
                terminated = True
                i += 1
                break

            # Recovery boundaries for the unterminated blocks.
            if (
                RE_CHECKLIST_OPEN.match(stripped)
                or RE_HEADING.match(stripped)
                or RE_EXTIMAGE.match(stripped)
                or RE_YOUTUBE.match(stripped)
                or RE_COMMENT.match(stripped)
                or "{{Var" in stripped
            ):
                break

            if stripped:
                # The block's closing braces are usually a line of their own,
                # but two of them sit on the end of the last step instead --
                # "...while watching a movie}}". Those braces travelled all the
                # way to the overlay as part of the step's own words.
                #
                # Only the text is cleaned. Treating this as the block's
                # terminator as well moved where the recovery boundary falls,
                # and with it which step a video anchors to -- a bigger change
                # than the one being made, on ten traps that each have a test.
                if stripped.endswith("}}") and not RE_CLOSE.match(stripped):
                    stripped = stripped[:-2].rstrip()
                steps_raw.append((i, stripped))
            i += 1

        if not terminated:
            self.warn(
                "unterminated_checklist",
                start + 1,
                f"missing closing }}}} for {resolved_title or '(untitled)'}; "
                f"recovered at line {i + 1}",
            )

        self.emit_section(start, resolved_title, steps_raw, terminated)
        return i

    def emit_section(
        self,
        line_no: int,
        title: str,
        steps_raw: list[tuple[int, str]],
        terminated: bool,
    ) -> None:
        continuation_of = None
        if not title:
            # Empty title= means "still the previous bank".
            if self.sections:
                parent = self.sections[-1]
                continuation_of = parent["id"]
                title = parent["title"]
                self.warn(
                    "continuation_section",
                    line_no + 1,
                    f"empty title=, treated as continuation of {parent['title']!r}",
                )
            else:
                self.warn("orphan_continuation", line_no + 1, "empty title= with no previous section")
                title = "Untitled"

        bank_number, bank_suffix = self.bank_from_title(title)
        self.cross_check_bank(bank_number, bank_suffix, line_no)

        base_slug = slugify(title)
        seen = self.seen_slugs.get(base_slug, 0)
        self.seen_slugs[base_slug] = seen + 1
        slug = base_slug if seen == 0 else f"{base_slug}-{seen + 1}"

        section = {
            "id": hashlib.sha1(slug.encode("utf-8")).hexdigest()[:10],
            "slug": slug,
            "ordinal": len(self.sections),
            "title": title,
            "bankNumber": bank_number,
            "bankSuffix": bank_suffix,
            "bankComment": self.pending_bank_comment,
            "episodeOrdinal": self.current_episode,
            "continuationOf": continuation_of,
            "imageUrls": list(self.pending_images),
            "videoIds": [],
            "terminated": terminated,
            "sourceLine": line_no + 1,
            "steps": [],
        }
        self.pending_images.clear()
        self.pending_bank_comment = None

        text_counts: dict[str, int] = {}
        for src_line, raw in steps_raw:
            m = RE_STEP.match(raw)
            if m:
                depth = len(m.group("bullet"))
                text = m.group("text").strip()
                kind = "step"
            else:
                # Bare prose inside a block, e.g. "IF 85 Crafting".
                depth = 1
                text = raw
                kind = "note"
                self.warn("bare_line_in_block", src_line + 1, raw[:80])

            if not text:
                continue

            key = normalize_for_id(text)
            collision = text_counts.get(key, 0)
            text_counts[key] = collision + 1

            section["steps"].append(
                {
                    "id": step_id(slug, text, collision),
                    "ordinal": len(section["steps"]),
                    "depth": depth,
                    "kind": kind,
                    "raw": text,
                    "videoIds": [],
                    "sourceLine": src_line + 1,
                }
            )

        self.sections.append(section)
        if self.episodes and self.current_episode is not None:
            self.episodes[-1]["sectionIds"].append(section["id"])

    # -- bank numbering ------------------------------------------------------

    @staticmethod
    def bank_from_title(title: str) -> tuple[int | None, str | None]:
        m = re.match(r"^Bank\s*(\d+)\s*([A-Z]?)\s*$", title.strip(), re.I)
        if not m:
            return None, None
        return int(m.group(1)), (m.group(2).upper() or None)

    def cross_check_bank(self, number: int | None, suffix: str | None, line_no: int) -> None:
        """The page carries <!-- Bank N --> comments. Use them as an oracle."""
        if not self.pending_bank_comment or number is None:
            return
        m = RE_BANK_COMMENT.match(self.pending_bank_comment)
        if not m:
            return
        expected = int(m.group("num"))
        expected_suffix = (m.group("suffix") or "").upper() or None
        if expected != number or expected_suffix != suffix:
            self.warn(
                "bank_number_mismatch",
                line_no + 1,
                f"counter says Bank {number}{suffix or ''}, "
                f"comment says Bank {expected}{expected_suffix or ''}",
            )

    def finalise_episodes(self) -> None:
        for ep in self.episodes:
            ep["sectionCount"] = len(ep["sectionIds"])

    # -- output --------------------------------------------------------------

    def document(self) -> dict:
        return {
            "episodes": self.episodes,
            "sections": self.sections,
            "preamble": self.preamble,
            "warnings": self.warnings,
        }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=REPO / "build" / "wikitext.json")
    ap.add_argument("--fixture", type=Path, default=None, help="parse a raw .txt fixture instead")
    ap.add_argument("--out", type=Path, default=REPO / "build" / "parsed.json")
    args = ap.parse_args()

    if args.fixture:
        wikitext = args.fixture.read_text(encoding="utf-8")
        meta = {"page": str(args.fixture), "revid": None, "fetchedAt": None,
                "revisionAt": None}
    else:
        doc = json.loads(args.input.read_text(encoding="utf-8"))
        wikitext = doc["wikitext"]
        meta = {k: doc.get(k) for k in ("page", "revid", "fetchedAt", "revisionAt")}

    parsed = Parser(wikitext).parse()
    parsed = {**meta, **parsed}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")

    steps = sum(len(s["steps"]) for s in parsed["sections"])
    notes = sum(1 for s in parsed["sections"] for st in s["steps"] if st["kind"] == "note")
    banks = sum(1 for s in parsed["sections"] if s["bankNumber"] is not None)
    images = sum(len(s["imageUrls"]) for s in parsed["sections"])
    videos = sum(len(e["videoIds"]) for e in parsed["episodes"]) + sum(
        len(st["videoIds"]) for s in parsed["sections"] for st in s["steps"]
    )

    print(f"episodes   {len(parsed['episodes'])}")
    print(f"sections   {len(parsed['sections'])}  ({banks} numbered banks)")
    print(f"steps      {steps}  ({notes} bare notes)")
    print(f"images     {images} attached to sections")
    print(f"videos     {videos} attached")
    print(f"preamble   {len(parsed['preamble'])} lines")
    print(f"warnings   {len(parsed['warnings'])}")

    by_code: dict[str, int] = {}
    for w in parsed["warnings"]:
        by_code[w["code"]] = by_code.get(w["code"], 0) + 1
    for code, count in sorted(by_code.items(), key=lambda kv: -kv[1]):
        print(f"  {count:4d}  {code}")

    print(f"wrote      {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
