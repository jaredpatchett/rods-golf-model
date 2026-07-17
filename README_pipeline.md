# Rod's Golf Model — Data Pipeline (Path A + sim engine)

Wraps DataGolf's live feeds, runs your own simulation for matchup model%, and
pushes both into the model page.

## What's here
- `rods_golf_model.html` — the page. Reads `rods_data.json` if present, otherwise shows built-in placeholder data.
- `rods_pipeline.py` — pulls DataGolf, runs the sim, writes `rods_data.json`. Run on **your** machine.
- `sim_engine.py` — **new.** Monte Carlo module (module 2 from the handoff docs). Turns each
  player's projected score + this event's course variance/blowup rate into 2-ball matchup
  win probabilities. This is what generates the "model%" column now — see "Model vs Market" below.
- `course_fit_engine.py` — **new.** Implements the Tier 2 formulas from `course_fit_spec.docx`
  (shrinkage, scoring_sd_adj, empirical fit weights via ridge regression, dist_premium,
  recovery_penalty). This is a **Path B tool** — it needs DataGolf's raw round-level history,
  which the pipeline doesn't pull yet. Run it standalone (`python3 course_fit_engine.py` runs
  a synthetic self-test) once you've exported round-level data for the links cluster.
- `load_course_fit_xlsx.py` — **new.** Reads your filled-in `course_fit_template.xlsx` and
  writes `course_fit_table.json`, which `rods_pipeline.py` now loads automatically. Requires
  `pip install openpyxl` (the one non-stdlib dependency in this project, only for this
  offline conversion step). If you haven't filled in the spreadsheet yet, the pipeline falls
  back to the hardcoded Birkdale/Bay Hill reference rows, same as before.
- `test_pipeline_mock.py` — **new.** Runs the full pipeline against mock DataGolf responses
  (no network needed) to sanity-check the plumbing. `python3 test_pipeline_mock.py`.

## Model vs Market (important change this session)
Previously, "model%" and "market%" both traced back to DataGolf — model% was DataGolf's own
matchup probability, market% was DataGolf's book-implied number. Comparing DG to DG couldn't
show real edge no matter what the numbers said. Now:
- **model%** comes from `sim_engine.py`, seeded by your projected scores and this event's
  course-fit variance/blowup rate — independent of DataGolf's internal model.
- **market%** still comes from the real book odds DataGolf reports (or is derived from the
  American price if DataGolf doesn't hand back a probability directly).

The sim defaults to summing 4 simulated rounds per player, matching the `tournament_matchups`
market pulled by default. If you switch to `round_matchups`, pass `--matchup-rounds 1`.
Known simplification: the 4-round sim doesn't model cuts/withdrawals — a real 72-hole matchup
settles on made-cut rounds only. Fine for a first pass; revisit if you're pricing matchups
near the cut line.

## One-time setup
You need Python 3 and your DataGolf API key. The live pipeline itself uses only the standard
library. `openpyxl` is only needed if you use `load_course_fit_xlsx.py`.

```bash
export DG_KEY="your_datagolf_key_here"     # never commit this / never paste it anywhere shared
```

## Run it
```bash
# put all the .py files in the same folder as rods_golf_model.html, then:
python rods_pipeline.py                        # pulls PGA feed, sims matchups, writes rods_data.json
python rods_pipeline.py --tour euro            # if The Open shows up under the euro feed instead
python rods_pipeline.py --watch 300            # refresh every 5 min during the round
python rods_pipeline.py --matchup-rounds 1     # if pulling round_matchups instead of tournament_matchups

# optional: connect your filled-in spreadsheet before running the pipeline
pip install openpyxl --break-system-packages
python3 load_course_fit_xlsx.py course_fit_template.xlsx   # writes course_fit_table.json
```

Then serve the folder and open the page (fetch() won't read a file:// path, so use a tiny server):
```bash
python -m http.server 8000
# open http://localhost:8000/rods_golf_model.html
```
The page will say `Loaded rods_data.json` in the browser console when it picks up real data.

## What maps to what
| Page array | DataGolf endpoint | Notes |
|---|---|---|
| `P` (projections) | `preds/player-decompositions` + `preds/pre-tournament` | SG components + course-fit come from decompositions; projected score merged from pre-tournament |
| `M` (matchups) | `betting-tools/matchups` | model prob vs book odds; edge computed on the page |
| wave / draw strip | `field-updates` | AM/PM from R1 tee time |
| `F` (course fit) | — (placeholder) | Left as your links row in Path A; you compute this yourself in Path B |

## If something breaks
- **HTTP 401 / bad key** → check `DG_KEY`.
- **Empty players / wrong event** → try `--tour euro`; The Open can sit on either feed.
- **Field names don't line up** → DataGolf occasionally renames JSON keys. The `pick(...)` helpers in each `build_*` function already try several likely names; add the new key to the relevant `pick()` call.
- **Matchups empty** → the matchup market may not be posted yet, or the `market=` param needs adjusting. The script continues without them.

## Migrating to Path B (your own model)
Everything DataGolf-specific is isolated in the `build_*` functions and the `EP` dict.
To use your own Birkdale fit weights and projections:
1. Pull DataGolf's raw round-level history for the links cluster (Birkdale, Troon, Portrush,
   Liverpool, St Andrews, Carnoustie).
2. Feed it to `course_fit_engine.py`'s functions (`scoring_sd_adj`, `fit_weights`, `dist_premium`,
   `recovery_penalty`, all built with the shrinkage backbone from §1 of the spec) to get your
   own computed row instead of the template's placeholder numbers.
3. Fill that row into `course_fit_template.xlsx`, then re-run `load_course_fit_xlsx.py` —
   `rods_pipeline.py` picks it up automatically from there, both for the page's F table and
   as the sim's course-level variance/blowup input.
4. In `build_projections`, swap DataGolf's `fit` field for `course_fit_engine.emit_player_outputs()`'s
   `mean_fit` output if you want fit-adjusted projections too, not just fit-adjusted course rows.
5. The `rods_data.json` shape never changes, so the page needs no edits.
