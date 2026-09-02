# Wikitext traps

Places where the obvious parser silently drops content instead of failing.
Every row has a named test in `tests/test_parse.py` pinned to
`tests/fixtures/v3_15325328.txt` (revid 15325328, 2026-08-30).

Line numbers refer to that fixture. Do not re-point the tests at the live page —
the whole purpose of the fixture is that these cases stop moving.

| # | Trap | Count | What the naive parser does | Test |
|---|---|---|---|---|
| 1 | Unterminated `{{Checklist}}` | 2 | The author never wrote the closing `}}` (Bank 30 at L650, Bank 39A at L836). Scanning forward to a bare `}}` line swallows the block and everything after it until the next one. Recovery stops at the next structural line instead. | `test_unterminated_blocks_recover_and_warn` |
| 2 | Empty `title=` | 6 | A continuation of the bank above it. Keying sections by title collides; skipping empty titles drops the steps. Inherits the parent title and bank number, gets its own slug. | `test_continuation_sections_inherit_the_previous_title` |
| 3 | First step inline with the title | 5 | `{{Checklist|title=Bank 28|* Withdraw: ...}}` puts step 1 on the opening line. A `startswith("*")` line filter never sees it. One case (`|*Starting Out`) has no space after the bullet; one (Bank 138) combines this with trap 2. | `test_inline_first_step_is_not_lost` |
| 4 | `{{Var|bankNumber}}` counter | 212 assignments / 236 blocks | Titles are `Bank {{#expr:{{#var:bankNumber}}+1}}`, so the number only exists if you walk the document in order and simulate the counter. Bank 132 is additionally hard-coded as a literal, and must still agree. | `test_bank_numbers_agree_with_the_html_comment_oracle`, `test_hardcoded_bank_title_still_agrees_with_the_counter` |
| 5 | Letter-suffixed banks | 6 | `39A`, `39B`, `105A`, `105B`, `164A`, `164B`. Banks 39, 105 and 164 have **no** plain form, so "bank numbers are contiguous" is false over unsuffixed sections and true only over base numbers. | `test_letter_suffixed_banks_are_preserved`, `test_banks_are_contiguous_from_one` |
| 6 | Nested sub-steps | 25 × `**`, 11 × `***` | Flattening loses hierarchy the player needs. Depth is stored per step. | `test_nesting_depth_is_preserved` |
| 7 | Stray bullets outside a block | 10 | `* Khazard Warlord Safespot: <url>` sits after a closed block, usually followed by a `{{Youtube}}` that must anchor to *it*. Appended to the preceding section as a `trailing-note`. The 6 "early GP" bullets before the first section stay in the preamble. | `test_stray_bullets_after_a_section_become_trailing_notes`, `test_intro_bullets_stay_in_the_preamble` |
| 8 | Bare prose inside a block | 3 | `IF 85 Crafting`, `Once you have your Bow of Faerdhinen`, `Video Guide: <url>`. Not bulleted, but ordered content. Kept as `kind: "note"`. | `test_no_step_text_is_empty_or_whitespace` |
| 9 | Links inside bracket tags | — | Running `\[([^\[\]]+)\]` over raw text matches the inner half of `[[Aggie]]`, turning 207 real quest tags into 666 phantoms. Strip `[[...]]` **before** reading `[...]`. | covered in `tests/test_annotate.py` |
| 10 | Line endings and curly quotes | 45 steps | The **API returns LF only** — the CRLF in the old hand-saved `v3.txt` came from a Windows editor, not the wiki. The parser still normalises `\r\n` defensively so a manually-saved fixture behaves identically. 45 steps contain U+2018/U+2019; force UTF-8 on every read and write, and note the Windows console renders them as `?` even when the bytes are correct — check the file, not the terminal. | `test_no_step_text_is_empty_or_whitespace` |

## Cross-checks that are not traps but catch drift

- **The `<!-- Bank N -->` oracle.** 214 of 236 sections are preceded by an HTML
  comment naming the bank. The simulated counter is validated against every one
  of them and warns on mismatch. If a future edit breaks the counter, this fires
  before anything downstream sees a wrong number.
- **Episode end markers.** 23 `End of Episode N` lines sit outside the blocks.
  Recorded on the episode, not treated as prose.

## Current fixture shape

```
episodes   23
sections   236   (220 numbered banks, max bank 211)
steps      2925  (3 bare notes, 10 trailing notes)
images     173   all attached to the section that follows them
videos     29    (23 episode-level, 6 step-level)
preamble   19    lines of intro prose
warnings   21    (10 trailing_note, 6 continuation, 3 bare_line, 2 unterminated)
```
