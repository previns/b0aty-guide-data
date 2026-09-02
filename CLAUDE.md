# CLAUDE.md

## What this repo is

The data half of a RuneLite plugin for the B0aty HCIM Guide V3. It turns the
OSRS Wiki page into `dist/guide.json`. The Java plugin lives in a separate repo
and does nothing but render this file.

- Source page: <https://oldschool.runescape.wiki/w/Guide:B0aty_HCIM_Guide_V3>
- API: `https://oldschool.runescape.wiki/api.php?action=parse&page=Guide:B0aty_HCIM_Guide_V3&prop=wikitext|revid&format=json&formatversion=2`

The page is edited constantly — it went from 8 episodes to 24 in a year. So
this is a re-runnable pipeline, not a one-time import: assume the source has
moved since the last build and that step text has been reworded under saved
progress. Refreshing it is a deliberate act, though, not a schedule — see
"Releasing an update".

## Pipeline

One script per stage, one JSON artifact between each. **Do not merge the
stages.** The boundaries are what make a failure attributable.

```
fetch → parse → annotate → resolve_wiki → merge_curated → emit → validate
        build/wikitext.json
                build/parsed.json
                        build/annotated.json + build/coverage.json
                                build/entities.json + build/unresolved.json
                                        build/merged.json
                                                dist/guide.json

side inputs to merge_curated, each its own stage:
  build_id_index    -> build/ids.json          RuneLite constants, via javap
  build_atlas       -> build/atlas.json        QH coords + item collections
  build_diary_tasks -> build/diary_tasks.json  QH diary VarPlayer bits
  build_quest_steps -> build/quest_steps.json  QH step lists, keyed by progress
  fetch_images      -> build/images.json       sha256 per screenshot
```

`fetch_images` runs against the *emitted* guide, so the order is
`emit -> fetch_images -> merge_curated -> emit` on a build whose screenshots
changed. It prints any URL whose bytes differ from the last run, which is the
one thing a person should glance at per build.

`pipeline/refresh.py` runs the whole chain in that order, so neither of the
two traps above has to be remembered:

```
python pipeline/refresh.py              # the full refresh, from the wiki
python pipeline/refresh.py --offline    # rebuild from build/, no network
python pipeline/refresh.py --dry-run    # print the plan and stop
```

It is a driver, not a stage: it only shells out to the scripts below in order,
each still writing its own artifact.

`validate.py` reads `dist/guide.json`, so it runs **after** emit. Running it
before reports the previous build's numbers and looks like a no-op change.

Run any stage against the frozen fixture instead of the network:

```
python pipeline/parse.py --fixture tests/fixtures/v3_15325328.txt
python pipeline/annotate.py --sample 25
python -m pytest tests -q
```

## The one architectural rule

**Resolve through an authority, never through similarity.**

Three authorities, tried in this order:

1. **The wiki itself** (`resolve_wiki.py`). A name resolves only via an exact
   page title, or a redirect the wiki already contains. The page's own infobox
   supplies the game IDs (`id`, `id1`..`idN`) and the `{{Map}}` coordinates. A
   title the wiki lacks comes back explicitly `missing` and stays unresolved.
2. **Quest Helper's source** (`build_atlas.py`, `build_diary_tasks.py`). It
   writes `new NpcStep(this, NpcID.FATHER_AERECK, new WorldPoint(...))`, and
   the wiki independently said Father Aereck is NPC 3211. The join is **number
   to number** — no name is compared, so this is a second authority keyed the
   same way as the first, not a similarity match. It only ever fills a gap: a
   wiki coordinate wins, and `curated/` overrides both.

   The same file's prose descriptions are a different matter entirely, and stay
   in `build_qh_hints.py` for human review. See below.

3. **The loaded scene** (the plugin). Whatever nothing could resolve is matched
   at runtime against `npc.getName()` and `ObjectComposition.getName()`.

None of the three can invent, and all fail silently. That is what licenses an
aggressive extraction grammar: a bad extraction finds no wiki page and matches
no NPC, so it **costs a missing highlight, never a wrong one**.

Redirects do the heavy lifting — 522 of 1,143 resolutions come through them,
including the guide's own typos (`Gertude` → Gertrude, `Ardounge` → Ardougne).
Those redirects were written by wiki editors, so following one is using curated
data, not guessing.

What is banned is resolution by *similarity*: edit distance, substring match,
"closest name". That is what produced an NPC called "the top floor" last time.
Fuzzy matching lives in exactly one place, `worklist.py`, whose output a person
approves before any of it reaches `curated/`.

Navigation is the remaining gap. Nothing can turn "Falador" into a coordinate
from prose alone, so destinations resolve against `curated/` — closed,
hand-written sets only.

**A destination with several coordinates draws no marker**, because picking one
would be a guess. Where a RuneLite *teleport* entry exists it wins, since "go to
X" means where the teleport lands; a wiki town page marking four buildings does
not answer the question. That rule takes ambiguous destinations from 46 to 18.

## Non-negotiable rules

1. **Never invent data.** No substring matching, no fuzzy fallback, no "closest
   name". Unresolvable means the field is absent and the step appears in the
   coverage report.
2. **Ambiguity is unresolved**, not first-match.
3. **Step text is verbatim.** Never rewrite, clarify, expand or summarise a
   step. If it reads badly, the fix is a wiki edit, not a pipeline edit.
4. **`curated/` is human-only.** Scripts read it, merge it last, never write to
   it.
5. **Coverage is reported, not optimised.** Print the honest number. Do not
   loosen a rule to make it look better.
6. **Don't hand-review 2,925 steps.** Ask for aggregate counts plus a random
   sample. That is how you catch a systematic error without reading everything.

## Stable step IDs

`sha1(section_slug + "|" + normalize(text))[:10]`, where normalize lowercases,
strips wiki-link syntax and collapses whitespace. Ordinal is a separate field so
reordering does not renumber. Duplicate text within a section gets a collision
suffix.

Stripping link syntax is deliberate: an editor wrapping an existing name in
`[[...]]` must not wipe a player's progress. Changing the words must.

`emit.py` diffs against the previous `dist/guide.json` and writes a `migrations`
map (old id → new id). The plugin applies it to saved progress on load, and uses
it to tell players which already-completed banks changed underneath them.

Matching a reworded step is the only fuzzy comparison in the repo, and it is not
a similarity threshold. Measured on the real guide, two *different* steps in the
same section exceed 0.80 similarity in 0.85% of pairs (sometimes reaching 1.00,
where the guide repeats a line), while a genuine edit appending a clarification
can fall to 0.44. The distributions overlap, so any single cutoff either loses
real edits or silently ticks steps the player never did. `match_quality()` uses
two structural signals instead — prefix containment, and ordinal proximity.

Fuzzy comparison is acceptable here and nowhere else because of what a mistake
costs: one checkbox restored to the wrong step, visible and undoable, rather
than false game data the plugin presents as fact.

## Wikitext structure

Read `docs/wikitext-traps.md` before touching `parse.py`. Ten documented traps,
each with a named regression test against a frozen fixture. Do not re-point
those tests at the live page.

Shape as of revid 15326606: 24 episodes, 236 sections, 2,925 steps, 173 images,
29 videos.

## Releasing an update

Updates are manual and deliberately so. The wiki edit reaches nobody until a
release: `guide.json` is baked into the jar.

```
python pipeline/fetch.py --if-changed-from build/wikitext.json   # exits 3 if unchanged
... run the pipeline, read the gates and the coverage diff ...
cp dist/guide.json ../b0aty-guide-plugin/src/main/resources/com/b0atyguide/
PR to plugin-hub bumping the commit hash
```

**What emit diffs against is `dist/guide.json` on disk**, so that file has to
be the last *released* build. Rebuild from an older fixture and you get a
migration map against the wrong baseline, which is the one way to lose a
player's progress silently.

Running emit more than once is fine, and the pipeline does it on purpose --
`fetch_images` reads the emitted guide, so a screenshot change needs
`emit -> fetch_images -> merge_curated -> emit`. The second run reports `0 new
this build` and carries the existing map forward untouched; chained renames
are collapsed so an id that moved twice still resolves in one hop. Verified by
emitting twice over the shipped file and confirming the map survives.

A reworded step gets a new id and is carried by `migrations`; a deleted step is
pruned. A step that moves to a different section also gets a new id and will
*not* migrate -- the section slug is part of the hash.

Coverage as of 2026-09-01, revid 15326606: target 55.28%, targetIds 28.62%,
targetPoints 29.30%, destination 10.19%, questTag 13.68%, items 88.40%.
`validate.py` prints these and fails on a regression worse than 2 points.

## Annotation grammar

`annotate.py` only. Rules, in order:

- `[[Foo]]` / `[[Foo|Bar]]` → candidate name `Foo`
- trailing `(3,1)` → dialogue option sequence
- trailing `[Something]` → quest or diary tag — **strip `[[...]]` first**, or
  `[[Aggie]]` yields a phantom tag and 207 real tags become 666
- verb prefix → intent, boundary is space **or colon** (`Withdraw:` is the
  second most common step opener)
- after the verb, skip articles and quantities, then take the leading run of
  capitalised words, stopping at a bracket, paren, punctuation or a stop word
- `Use X on Y` → item X, object Y
- `X -> Y` → teleport shorthand: method X, destination Y
- `Withdraw: a, b & c (N Inventory Slots)` → item list plus slot count

Confidence is recorded per step: `linked` (backed by a wiki link), `inferred`
(from the grammar), `none`. The plugin may treat them differently; the pipeline
does not.

## Curated data

`curated/` holds only closed sets — lists that are finite and stop growing:

| File | What | Why it is safe to hand-write |
|---|---|---|
| `banks.yaml` | Bank locations | ~40 banks in the game |
| `teleports.yaml` | Teleport and fairy-ring destinations | fixed published tables |
| `quest_aliases.yaml` | Guide shorthand → `Quest` enum name | ~25 rows lift tag resolution from 70% to ~93% |
| `item_collections.yaml` | Category word → `ItemCollections` constant | 159 closed sets; "Pickaxe" is not an item and never resolves on the wiki |
| `diary_tasks.yaml` | Step id → diary `VarPlayer` + bit | 453 task bits exist; which step means which is prose |
| `skill_targets.yaml` | Step id → skill + level | the guide names levels for several reasons; only one means "done" |
| `spells.yaml` | Destination → `MagicSpellbook` constant | the standard spellbook has one answer per town |
| `entity_aliases.yaml` | Guide phrase → the NPCs it means | "a man/woman" is lowercase, plural and slashed; no grammar reaches it |
| `places.yaml` | Guide destination spelling → a name that resolves | holds names, never coordinates |
| `overrides.yaml` | Per-step fixes keyed by step id | merged last, always wins |

Each has a build gate that fails on a bad row rather than dropping it:
`--check-aliases`, `--check-collections`, `--check-diary`,
`--check-entity-aliases`, `--check-places`, `--check-skills`, `--check-spells`.

**Quote step ids in YAML.** A step id can be all digits, and an unquoted
`4655341384` is read as a number that then matches no step -- silently.
`step_keyed()` coerces on load so forgetting is harmless rather than invisible. That is not
ceremony — all three bugs found on 2026-08-31 were **silent under-reporting**,
and the pipeline's existing guards only catch fabrication.

`diary_tasks.yaml` is the highest-stakes file in the repo. A wrong row
auto-ticks a step the player never did, and they find out much later having
skipped the work. String similarity is not just insufficient for deciding those
rows, it is misleading: it ranked "Travel to Entrana" against "Fill Water
Bucket" above the correct "To the Holy Land!". Decide every row against the
tier's full task list, and leave a step out when unsure.

Warn loudly when an override key no longer matches a step — that means the wiki
text moved.

Never add an open-ended entity list here. NPC and object names are unbounded and
belong to runtime matching.

## Testing

`pytest tests -q`. Golden assertions against the frozen fixture: section count,
episode count, every trap in `docs/wikitext-traps.md`, ID stability across runs,
ID uniqueness.

Anything needing a game client is tested by hand in the dev client. Say so
plainly rather than mocking the client.

## Reporting

When a stage finishes, report counts in, counts out, coverage by category, top
unresolved names by frequency, and a random sample of extracted steps next to
their raw text. "Done" without numbers is not a report.

## Screenshots

The guide's 173 bank setup images are hotlinked from `i.ibb.co` and never
re-hosted. Bundling them was measured at ~10 MiB and rejected on both size and
licensing.

Their links come from a wiki page anyone can edit, so:

- the plugin requests **only** URLs that were in `guide.json` at build time, so
  vandalism cannot reach a player until a build picks it up;
- `fetch_images.py` records a **sha256** per image and the plugin refuses bytes
  that do not match, which covers the picture behind an unchanged link being
  swapped afterwards;
- `validate.py` fails the build on an image from another host, with no
  recorded hash, or with a malformed one. An unhashed image is refused at
  runtime, so without this gate the failure mode is a silently blank panel.

## Attribution

Guide content is © B0aty and OSRS Wiki contributors under CC BY-NC-SA. Code is
BSD 2-Clause. Keep them separate and keep `NOTICE.md` accurate.
