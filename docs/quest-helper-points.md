# Quest Helper coordinates joined by game id

`build_atlas.py` gives a target a coordinate when the wiki gave it none, by
matching the entity's game id against a `new WorldPoint(...)` in quest-helper's
source. 77 targets in the shipped guide get their only coordinate this way.

For a unique NPC or a fixed object that is exact. For a monster that spawns all
over the world it is whichever spawn some quest happened to use, and the guide
may mean a different one.

## What was measured

Of those 77, the step text names a place the pipeline can locate in 20 cases.
Comparing the coordinate against that place:

| distance from the named place | steps |
|---|---|
| within 60 tiles | 2 |
| further | 18 |

So a distance test looks promising until you read the 18. Ten are **underground**
— Draynor Sewers, the Shayzien Crypts, the Karamja dungeon — where the
coordinate is correct and the surface place name is just the region it is under.
The remaining eight are surface-to-surface, and they split:

**Wrong, and worth dropping**

| target | text names | coordinate is |
|---|---|---|
| Black Bear | Falador | the Varrock spawn, 357 tiles away |
| Estate agent | Pollnivneach | 2,182 tiles away |
| Foreman | Grand Tree | 986 tiles away |

**Correct, and a distance test would throw them away**

| target | text names | why it is far |
|---|---|---|
| Mogre | Falador (the diary) | mogres live at Mudskipper Point, 293 tiles south |
| Gem Rocks | Karamja (the diary) | the rocks are in Shilo Village, 272 tiles away |
| Teak | Karamja (the diary) | the trees are on the south of the island |

A diary tag names the *diary*, not the place, and half this route's steps are
diary tasks. There is no threshold that keeps Mudskipper Point and drops the
Varrock bear: 293 is further than 357 is wrong.

## The decision

No rule. The coordinate stays unless a person says otherwise, and
`curated/overrides.yaml` is where they say it — dropping the coordinate, never
replacing it, because no source here knows which spawn the guide means and
typing one in from memory is what rule 1 forbids.

Dropping a coordinate costs the waypoint and the world-map marker. It keeps the
outline: `SceneTracker` still matches the id, so the bear lights up the moment
one walks into the scene, which is the part that mattered.

Currently overridden: Black Bear (Bank 10).
