# The daily wiki sync

`.github/workflows/sync.yml` runs at 05:20 UTC. If the guide's wikitext revision
has changed it rebuilds `dist/guide.json` and opens a pull request; if not it
does nothing and exits green. There is deliberately no auto-merge — a person
reads the step diff before a changed route reaches players.

## Why some stages are pinned instead of run

Six stages cannot run on a GitHub runner:

| Stage | Needs |
|---|---|
| `build_id_index` | `javap` against a `runelite-api` jar |
| `build_atlas` | the vendored Quest Helper source |
| `build_quest_steps` | the vendored Quest Helper source |
| `build_qh_hints` | the vendored Quest Helper source |
| `build_quest_objects` | the vendored Quest Helper source |
| `build_diary_tasks` | the vendored Quest Helper source |

Quest Helper is checked out *beside* this repository, at
`../B0aty Guide/quest-helper-master`, not inside it. That is on purpose:
refreshing it rewrites guidance across the whole guide, so it is a reviewed act
rather than a dependency that moves on its own, and `tests/test_vendored_source.py`
fails when it goes stale.

The runner could clone it and install a JDK. It should not. A wiki sync must
change only what the wiki changed; if the runner re-derived this data from
upstream, a routine "Wiki sync" pull request would quietly carry a Quest Helper
upgrade inside it — the one thing its review exists to catch. `pinned/` is
therefore excluded from the pull request's `add-paths` as well.

So the outputs are committed, gzipped, under `pinned/`: 22.5 MB of JSON in
2.0 MB, `quest_steps.json` alone 17.5 MB in 1.0 MB.

## After refreshing Quest Helper

```
python pipeline/refresh.py          # the full rebuild, locally
python pipeline/pin_reference.py --pack
git add pinned/ && git commit
```

Without the re-pack the sync keeps building against the *previous* Quest Helper.
That is not a silent failure — the guide it produces is simply the old one — so
re-pack in the same commit as the refresh.

## When the sync fails

It failed every night from 2026-09-03 to 2026-09-08 on a missing
`build/runelite/Quest.java`: an input to `merge_curated`, living under a
gitignored directory, downloaded by nothing. `build_locations.py` fetches the
seven worldmap `*Location.java` files and not that one.

`tests/test_sync_workflow.py` now fails when the workflow reads a `build/` file
that neither a stage it runs nor `pinned/` provides, so the next one is caught
when it is written rather than at 05:20 the following morning.

To reproduce a runner locally, clone this repository into a scratch directory —
a clone has no `build/`, which is the whole difference — then:

```
python pipeline/pin_reference.py --unpack
```

and run the workflow's Build commands in order. Tests that read the vendored
Quest Helper skip themselves there, via `tests/conftest.py`, because they are
inapplicable rather than broken.
