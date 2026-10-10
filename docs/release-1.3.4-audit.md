# 1.3.4 data audit

Regenerated from the same frozen Wiki revision as 1.3.3. Every one of the 2,925 step IDs and verbatim texts is unchanged. Human curated files were backed up and not edited; their previously unpublished changes are included in the data commit.

## Counts and coverage

- Guide: 236 source sections, 24 episodes, 2,925 emitted steps; runtime filtering/absorption gives 2,912 guide steps.
- Quest guidance: 158 shipped helpers, 14,816 instructions, 217 runtime diary task helpers.
- Routes: 158 source setLinePoints calls, 142 literal calls extracted, 16 unresolved calls. Conditional duplication gives 158 shipped literal route instructions; 4 shipped instructions require dynamic routes. The latter suppress generic pathfinding rather than invent a route.
- Whole diary completion: 5 guide steps, all joined to Quest Helper reward-claimed varbits, exactly value 1. Individual diary task bits are unchanged.
- Shop: Scavvo's list resolves Rune sword 1289, green d'hide chaps 1099, green d'hide vambraces 1065 and coif 1169 via exact Wiki pages/redirects.
- Exact entity resolution: 2,535 candidate names; 1,836 resolved (798 items, 795 NPCs, 187 places, 56 objects), 1,648 with IDs and 909 with coordinates. 340 missing pages and 282 unusable infoboxes remain unresolved.
- Validation and guide-wide retention audits clean. 497 Python tests pass. No live client playthrough claimed.

Coverage artifact:

```json
{
  "totalSteps": 2925,
  "sections": 236,
  "episodes": 24,
  "stepsWithTarget": 1537,
  "stepsWithTargetIds": 886,
  "stepsWithTargetPoints": 969,
  "stepsWithDestination": 421,
  "stepsWithQuestTag": 421,
  "itemMentions": 2313,
  "itemsResolved": 2000,
  "pct": {
    "target": 52.55,
    "targetIds": 30.29,
    "targetPoints": 33.13,
    "destination": 14.39,
    "questTag": 14.39,
    "items": 86.47
  }
}
```

Top unresolved item names by guide frequency:

- Combat Gear: 9
- Potions: 5
- Crystal Armour: 4
- Shantay Pass: 3
- Boots: 3
- 100 Soda Ash: 3
- 100 Soda Sand: 3
- Chaps: 3
- Steel: 3
- Monk Robes: 3

## Seeded extraction sample beside raw Wiki text

- `57da65e3df`
  - Raw: Teleport to Ardougne
  - Emitted: Teleport to Ardougne
  - Target: `{"name": "Ardougne", "names": ["Ardougne"], "kind": "place", "ids": [], "points": [[2570, 3300, 0]], "wikiPage": "Ardougne", "confidence": "wiki-exact", "pointSource": "wiki", "scattered": false}`
- `2896e4d60f`
  - Raw: Talk to [[Merlin]] (1)
  - Emitted: Talk to Merlin (1)
  - Target: `{"name": "Merlin", "names": ["Merlin"], "kind": "npc", "ids": [3529, 4059], "points": [[2767, 3501, 1]], "wikiPage": "Merlin", "confidence": "linked", "pointSource": "wiki", "scattered": false}`
- `7c43bff238`
  - Raw: Exit by entering the portal and teleport with [[Istoria]]
  - Emitted: Exit by entering the portal and teleport with Istoria
  - Target: `{"name": "Istoria", "names": ["Istoria"], "kind": "npc", "ids": [11112, 11113], "points": [[1552, 10224, 0]], "wikiPage": "Istoria", "confidence": "linked", "pointSource": "wiki", "scattered": false}`
- `b4f57b89b3`
  - Raw: Use Harralanders, Avantoe(some Kwuarm) & Irits in Mastering Mixology (Don't grind them all incase the ratios aren't correct. 10k+ is good then top up). Don’t use all your Kwuarms as you will need them
  - Emitted: Use Harralanders, Avantoe(some Kwuarm) & Irits in Mastering Mixology (Don't grind them all incase the ratios aren't correct. 10k+ is good then top up). Don’t use all your Kwuarms as you will need them
  - Target: `{"name": "Harralanders", "names": ["Harralanders"], "kind": "item", "ids": [255], "points": [], "wikiPage": "Harralander", "confidence": "wiki-redirect", "scattered": false}`
- `7b273e0687`
  - Raw: Go upstairs in Blue Moon inn and continue Pirate's Treasure
  - Emitted: Go upstairs in Blue Moon inn and continue Pirate's Treasure
  - Target: `null`

## Remaining manual work

Ambiguous RFD objectives remain unresolved, and compound diary/quest midpoints without a source-verified game state remain manual. Dynamic route instructions require the installed Quest Helper solver. No estimated ID or coordinate was introduced to increase coverage.
