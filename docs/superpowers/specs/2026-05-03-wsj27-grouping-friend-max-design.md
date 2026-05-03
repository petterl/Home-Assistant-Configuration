# WSJ 2027 — Maximize Friend Connections in Group Assignment

**Date:** 2026-05-03
**Scope:** `wsj27_utils.py:assign_groups()`, `wsj_gruppindelning_rundresa.ipynb`, `wsj_gruppindelning_direktresa.ipynb`
**Out of scope:** `wsj_gruppindelning_ledare.ipynb` and its grouping algorithm; geocoding; map rendering; export logic; other WSJ27 notebooks.

## Goal

Maximize friend connections (people with at least one friend wish satisfied in their assigned group) for the rundresa and direktresa group assignments, while preserving today's hard constraints. Refactor the two notebooks so they share the same flow byte-for-byte except for one config line.

## Constraints (unchanged from today)

- **Group size:** exactly 36 per group, with one remainder group allowed.
- **Max kår per group:** 8 (hard).
- **Geographic proximity:** participants in a group should live close to each other.
- **Diversity:** age (14–17) and sex spread reasonably across groups.

Friend wishes are a soft goal: the algorithm tries to maximize them, never break a hard constraint to satisfy one.

## Optimization metric

Maximize `count_friend_satisfied`: number of people who have at least one friend wish AND that friend is in their assigned group. This matches what `print_group_metrics` already reports, so before/after comparisons are direct.

## Quality tiers

The notebook chooses runtime/quality with a single constant.

| Tier | Runtime (≈1500 people) | Approach |
|------|------------------------|----------|
| `medium` (default) | 1–3 min | Single run of full pipeline |
| `slow` | 10–30 min | 8 independent restarts with different seeds; keep highest-friend result |

## Algorithm changes (`assign_groups`)

Same five-phase shape as today. Each change is independent and can be implemented/measured separately.

### 1. Friend-cluster-aware initial cut

Today: Hilbert-sort all participants, cut into chunks of 36. Friend clusters straddling a cut boundary are split.

New: build connected components in the friend-wish graph. For each cluster (typically 2–6 people), compute its geographic centroid and use that as the cluster's Hilbert-anchor. Walk Hilbert order placing clusters as units; if a cluster doesn't fit in the current group (would exceed 36 or kår=8), spill into the next group as a unit when possible, otherwise spill minimally. Singletons fill remaining seats by their own Hilbert order.

Expected to produce most of the friend-rate gain because Phase 2 starts from a much better baseline.

### 2. Phase 2 — iterate friend-swap pass until convergence

Today: one pass over participants. Phase 2b is a literal copy-paste run after the kår-fix phase.

New: a single helper `_friend_swap_pass(...)` returns the count of improving swaps it made. Phase 2 calls it in a `while improved:` loop, capped at 10 iterations to bound runtime. Phase 2b becomes the same helper, called once after Phase 3.

### 3. Phase 2.5 — three-way rotations

After Phase 2 converges, attempt 3-way rotations for any still-unsatisfied friend wish. For unsatisfied participant A in group G_A: pick a member of friend's group G_B and a member of any third group G_C, rotate `A→G_B`, `member_B→G_C`, `member_C→G_A`. Accept only if all sizes/kår limits hold AND the friend count strictly increases.

Bounded cost: ~O(n × k²) where k ≈ group size. Cheap relative to Phases 2 and 4.

### 4. Phase 4 — SA gains friends, not just preserves

Today: SA accepts swaps that improve diversity, **rejects any swap that loses a friend**, never tries to gain friends.

New scoring: `score = α · friends_satisfied + β · diversity − γ · geo_spread`. Same SA acceptance rule on the combined score. α tuned high enough that friend-positive swaps are nearly always accepted; this turns Phase 4 into a continuation of Phase 2 with diversity as a tiebreaker.

### 5. Friend-wish criticality ordering

Today: Phase 2 iterates `range(n)`. New: process unsatisfied wishes in criticality order — people whose only friend lives in a *distant* group go first (cheaper to move them while destination groups still have slack on size/kår).

### 6. Slow tier — multi-restart wrapper

`quality='slow'` runs the full Phase 1–4 pipeline N=8 times with different seeds, returns the assignment with the highest friend count. Implemented as a wrapper around the existing pipeline — no restart-awareness inside the phases.

## API change to `assign_groups`

```python
def assign_groups(df_sorted, group_size, friend_wishes, max_kar=8,
                  quality='medium',         # NEW: 'medium' | 'slow'
                  diversity_iterations=None, geo_weight=None, seed=None):
    ...
```

Presets:
- `medium`: `n_restarts=1`, SA `iterations=15000`, `geo_weight=2.0`
- `slow`: `n_restarts=8`, SA `iterations=15000`, return highest-friend result

Legacy kwargs (`diversity_iterations`, `geo_weight`, `seed`) still accepted: when set explicitly, they override the corresponding preset value, leaving the rest of the preset intact. This keeps any external caller working without the new `quality` arg.

## Performance — keep medium tier in 1–3 min

`friend_satisfied(idx)` is called millions of times by Phase 4 SA. Today it rebuilds a set of group members on each call. New: maintain `group_members[g]` as a dict-of-sets, kept current inside `do_swap()` which already centralizes all mutations. `friend_satisfied` becomes one or two `in`-checks. Algorithm semantics unchanged; runtime cost of the new phases mostly absorbed.

## Notebook structure (rundresa + direktresa)

Both notebooks become 5 cells. Cells 2–4 are byte-identical between them — only Cell 1 differs.

**Cell 0 — Markdown header** (rules, unchanged)

**Cell 1 — Config**
```python
TRAVEL = 'rundresa'        # only line that differs between notebooks
QUALITY = 'medium'         # 'medium' (~1-3 min) or 'slow' (~10-30 min, +5-10% friends)
GROUP_SIZE = 36
OUTPUT_DIR = '/config/notebooks/wsj27/output'
```

**Cell 2 — Load + prepare**
```python
import sys; sys.path.insert(0, '/config/notebooks/wsj27')
import wsj27_utils as u

raw = u.fetch_participants()
df_all, _ = u.build_participant_dataframe(raw)
df = df_all[df_all['travel'] == TRAVEL].copy().reset_index(drop=True)
u.assign_coordinates(df)
df = u.add_hilbert_index(df)
u.resolve_friend_wishes(df, df_all)
friend_wishes = u.build_friend_graph(df)
u.print_intake_summary(df, GROUP_SIZE)
```

**Cell 3 — Assign**
```python
df = u.assign_groups(df, GROUP_SIZE, friend_wishes, quality=QUALITY)
group_of = df['group'].values
total_groups = df['group'].nunique()
```

**Cell 4 — Metrics + export + map**
```python
u.print_group_metrics(df, group_of, total_groups)
csv_path, json_path = u.export_results(df, group_of, total_groups, OUTPUT_DIR, prefix=f'wsj27_{TRAVEL}')
map_path = f'{OUTPUT_DIR}/wsj_{TRAVEL}_karta.html'
u.generate_group_map_html(df, total_groups, map_path,
                          title=f'WSJ 2027 {TRAVEL.title()}',
                          friend_wishes=friend_wishes, show_group_arcs=True)
print(f'CSV:  {csv_path}\nJSON: {json_path}\nMap:  {map_path}')
```

### Why this shape
- Switching tier is a one-line edit (`QUALITY = 'slow'`).
- Cells 2–4 byte-identical between notebooks → accidental drift impossible.
- Flow stays cell-by-cell — each step inspectable, errors recoverable per cell.
- One small new util (`print_intake_summary`) absorbs the inline prints from today's cell 2.

### Explicitly NOT doing
- No collapsing into a single `run_full_grouping()` super-function (would hide the cell flow).
- No parameterized notebook runner (papermill etc.) — overkill for two notebooks.
- No changes to `wsj_deltagare_adresser.ipynb`, `scoutnet_analysis.ipynb`, or any ledare file.

## `wsj27_utils.py` refactor

Changes are confined to `assign_groups()` plus one small new helper.

### Extract shared friend-swap helper

```python
def _friend_swap_pass(idx_iter, *, group_of, member_arr, member_to_idx,
                      f1_arr, f2_arr, friend_of, kars_arr, group_size, max_kar):
    """One pass of friend-fixing swaps. Returns (n_swaps, n_now_satisfied).
    idx_iter controls order — caller may pass a criticality-sorted iterable."""
```

Phase 2 calls it in `while improved:` loop with criticality-sorted indices. Phase 2b calls it once after Phase 3. Phase 2.5 is a sibling helper `_friend_rotate_pass(...)`.

### New `print_intake_summary` helper

Lifts the participants count + region/age/sex distribution + group-count projection prints from rundresa cell 2 into utils. ~25 lines.

### Out of scope for this refactor
- No type hints retrofit, no dataclass conversion, no module split.
- No vectorization beyond `friend_satisfied`.
- `print_group_metrics`, `export_results`, `generate_group_map_html` — untouched.

### Estimated diff size
- `wsj27_utils.py`: ~+150 / −90 lines (net +60). Still one file.
- Each notebook: ~+5 / −60 lines (heavy net reduction).

## Verification plan

1. Run the existing rundresa notebook on current data, capture friend-satisfied count, group geo-spread, kår-violation count, runtime. Same for direktresa.
2. Implement changes incrementally; after each algorithm change measure friend-satisfaction delta vs baseline.
3. Final acceptance criteria:
   - Medium tier: friend-satisfied count ≥ baseline + 10% on rundresa AND direktresa.
   - Slow tier: friend-satisfied count ≥ medium-tier result on both.
   - Zero kår-violations in both tiers (unchanged from today).
   - Geographic spread within 1.5× of baseline (some loss acceptable in exchange for friends).
   - Notebook cells 2–4 produce a byte-identical diff between rundresa.ipynb and direktresa.ipynb (only Cell 1 differs).

## Open questions

None — all decisions resolved during brainstorming:
- Hard constraints stay hard.
- Optimization metric: `count_friend_satisfied` (people with ≥1 friend present).
- Quality tiers: medium default, slow opt-in via `QUALITY = 'slow'` constant.
- Ledare notebook untouched.
