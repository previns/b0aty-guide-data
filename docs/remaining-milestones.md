# Four stopping points still need proof

Current build: `feb16088b1fb2ac1`. These remain manual; no unrelated quest-state
change or finished-quest sweep can tick them. Guidance may continue until the
player checks the guide step manually. They are not fully fixed automatic goals.

| Guide step | Why not mapped yet |
|---|---|
| Tai Bwo Wannai Trio: head to Cairn Isle (`d19c49ef79`) | The main quest value stays at 3 through independently ordered errands. QH uses remembered dialogue/journal state; a later value 5 is not the travel handoff. |
| Watchtower: blue-dragon cutscene (`2958f3ab85`) | QH has `seenShamans` / `WATCHTOWER_NIGHTSHADE_USED`, but the source examined does not prove this means the author's specified cutscene has finished. |
| Perilous Moons: unlock Sulphur Naguas (`2d909c6747`) | QH distinguishes the initial quest Nagua from entering Neypotzli. The precise access flag for repeatable Nagua training is not established. |
| Defender of Varrock: unlock Armoured Zombies (`78e673faa3`) | QH describes multiple dungeon/cutscene stages. The exact training-access unlock is not established; value 54 was the final quest conversation. |

Resolved since this list was written: **Prince Ali Rescue** (`f769b86e2b`,
"until you need to return to Osman"). Current Quest Helper has no return-to-Osman
step -- it makes the key at a furnace -- and varplayer 273 reports the same value
across the whole middle of the quest, so no value could express it. The author
chose the Key print (2423), which Osman historically made the key from, and the
pipeline resolves "1x Key print" to exactly that item in the quest's own helper.

Authorised mappings belong in `curated/overrides.yaml`, with source evidence.
Use `questStopItems`, `questStopValue`, or a supported `questStopCondition`.
Do not restore an inferred later-visit boundary simply to make a checkbox move.

The historical `stopping-points-to-review.md` predates this audit. The current
machine-readable list is `build/quest-milestones-unresolved.json`, generated
after final author overrides, not before them.
