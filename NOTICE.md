# Notices

## Guide content

The step text, section structure and screenshots originate from
[Guide:B0aty HCIM Guide V3](https://oldschool.runescape.wiki/w/Guide:B0aty_HCIM_Guide_V3)
on the Old School RuneScape Wiki, © B0aty and the wiki's contributors, licensed
under [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/).

Step text is reproduced verbatim and never rewritten. Screenshots are loaded
from their original host (i.ibb.co) and are not re-hosted.

## Coordinate data

`curated/locations.generated.yaml` is derived from world map enums in
[RuneLite](https://github.com/runelite/runelite), © 2016-2026 the RuneLite
authors, BSD 2-Clause. Regenerate with `pipeline/build_locations.py`.

## Quest Helper data

[Quest Helper](https://github.com/Zoinkwiz/quest-helper), (c) 2020 Zoinkwiz,
BSD 2-Clause. Used in two different ways, with different rules.

**Merged into `dist/guide.json`** — game IDs, coordinates and item-collection
membership, all read as literals from the source:

| Artifact | Built by | What is taken |
|---|---|---|
| `build/atlas.json` | `pipeline/build_atlas.py` | `NpcID`/`ObjectID` constants paired with `WorldPoint`s; `ItemCollections` membership |
| `build/diary_tasks.json` | `pipeline/build_diary_tasks.py` | achievement-diary `VarPlayer` ids and task bit indices, with their panel titles |
| `build/quest_objects.json` | `pipeline/build_quest_objects.py` | per-quest `ObjectStep` ids and coordinates |
| `build/quest_steps.json` | `pipeline/build_quest_steps.py` | per-quest step lists keyed by quest progress -- **including Quest Helper's step descriptions** |

All but the last are joined to our data **by numeric game ID**, never by
matching text. `quest_steps.json` is the exception and is the only place Quest
Helper's *prose* is redistributed: the guide advances quests a step at a time,
so it carries their instruction for the player's current progress value, shown
in the plugin as "Quest step". Facts about the game — that an
NPC stands at a coordinate, that a diary task is bit 5 — are not themselves
copyrightable, but the extraction is derived from a BSD 2-Clause work and the
notice is reproduced here and in the plugin repo accordingly.

**Human review only, never merged** — `build/qh_hints.json`, built by
`pipeline/build_qh_hints.py`, keys the same coordinates by Quest Helper's step
descriptions. That is free-text matching, which this pipeline forbids, so its
output goes to `docs/curation-worklist.md` for a person to approve.

## RuneLite ID constants

`build/ids.json` holds numeric values of `ItemID`, `NpcID`, `ObjectID` and
`VarPlayerID` constants, read from a compiled `runelite-api` jar by
`pipeline/build_id_index.py`. [RuneLite](https://github.com/runelite/runelite),
(c) 2016-2026 the RuneLite authors, BSD 2-Clause.

## Code

Everything under `pipeline/` and `tests/` is BSD 2-Clause. See LICENSE.
