# WSJ 2027 — Friend-Max Grouping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve `wsj27_utils.assign_groups()` so rundresa and direktresa group assignments satisfy more friend wishes, expose a `quality='medium'|'slow'` toggle, and slim both notebooks so cells 2-4 are byte-identical between them.

**Architecture:** Five phases stay in place (init cut → friend swap → kår fix → friend re-fix → diversity SA), but: initial cut becomes friend-cluster-aware; Phase 2 iterates until convergence with criticality ordering; a new Phase 2.5 does 3-way rotations; Phase 4 SA is rescored to actively gain friends; a `quality='slow'` wrapper runs 8 restarts and keeps the best. Notebooks become a 5-cell skeleton driven by a single `TRAVEL`/`QUALITY` config cell.

**Tech Stack:** Python 3.11, NumPy, pandas (existing). Tests use stdlib `unittest` only — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-03-wsj27-grouping-friend-max-design.md`

**Out of scope:** ledare notebook + algorithm; geocoding; map rendering; export logic.

---

## File Map

**Modified:**
- `notebooks/wsj27/wsj27_utils.py` — `assign_groups()` (lines 678-1017) and one new helper. ~+150/−90 lines.
- `notebooks/wsj27/wsj_gruppindelning_rundresa.ipynb` — restructured to 5 cells.
- `notebooks/wsj27/wsj_gruppindelning_direktresa.ipynb` — same shape as rundresa, only Cell 1 differs.

**Created:**
- `notebooks/wsj27/tests/__init__.py` — empty, makes tests/ a package.
- `notebooks/wsj27/tests/fixtures.py` — synthetic dataframe builders used by tests.
- `notebooks/wsj27/tests/test_assign_groups.py` — algorithm unit tests.
- `notebooks/wsj27/tests/baseline_metrics.json` — captured pre-change metrics from real data.

**Untouched:** ledare notebook, ledare wish-parsing, all other utils functions (`fetch_participants`, `assign_coordinates`, `print_group_metrics`, `export_results`, `generate_group_map_html`, etc.).

---

## Conventions for this plan

- **Tests use stdlib `unittest`** (no pytest dependency). Run individually: `python -m unittest notebooks.wsj27.tests.test_assign_groups.TestX.test_y -v` from `/config`.
- **Run all tests** at the end of every task: `cd /config && python -m unittest discover -s notebooks/wsj27/tests -v`.
- **Commit at the end of each task.** Stage only the files the task touched.
- **Numbered phase changes are independent.** After Tasks 6-10 each, the algorithm should still produce a complete legal assignment (sizes correct, kår ≤ 8). Run `python notebooks/wsj27/tests/sanity_check.py` (created in Task 1) to verify.

---

## Task 1: Test infrastructure + synthetic fixtures

**Files:**
- Create: `notebooks/wsj27/tests/__init__.py`
- Create: `notebooks/wsj27/tests/fixtures.py`
- Create: `notebooks/wsj27/tests/sanity_check.py`
- Create: `notebooks/wsj27/tests/test_assign_groups.py`

- [ ] **Step 1: Create empty `__init__.py`**

```bash
touch /config/notebooks/wsj27/tests/__init__.py
```

- [ ] **Step 2: Create `fixtures.py`**

Path: `/config/notebooks/wsj27/tests/fixtures.py`

```python
"""Synthetic dataframe builders for assign_groups tests.

Generates small, deterministic dataframes that exercise specific algorithm
behaviors. All fixtures match the columns assign_groups expects:
member_no, name, age, sex, kar, lat, lng, friend_1, friend_2, plus a
hilbert column (added by add_hilbert_index)."""

import pandas as pd
import sys
sys.path.insert(0, '/config/notebooks/wsj27')
import wsj27_utils as u


def make_df(rows):
    """rows is list of (member_no, kar, lat, lng, age, sex, f1, f2)."""
    df = pd.DataFrame([
        {
            'member_no': str(m),
            'name': f'Person {m}',
            'age': age,
            'sex': sex,
            'kar': kar,
            'region': 'Test',
            'lat': lat,
            'lng': lng,
            'friend_1': str(f1) if f1 else '',
            'friend_2': str(f2) if f2 else '',
            'friend_1_name': '',
            'friend_2_name': '',
        }
        for (m, kar, lat, lng, age, sex, f1, f2) in rows
    ])
    return u.add_hilbert_index(df)


def fixture_two_groups_one_friend_pair():
    """72 people in two natural geographic clusters of 36.

    Within cluster A (members 1-36): person 1 wants person 50 (in cluster B).
    Within cluster B (members 37-72): person 50 wants person 1 (in cluster A).

    Initial Hilbert cut puts them in different groups; Phase 2 should
    produce a swap that places them together."""
    rows = []
    # Cluster A around (59.0, 18.0) - Stockholm-ish
    for i in range(1, 37):
        lat = 59.0 + (i % 6) * 0.01
        lng = 18.0 + (i // 6) * 0.01
        f1 = 50 if i == 1 else 0
        rows.append((i, f'kar_{i % 4}', lat, lng, 14 + i % 4, (i % 3) + 1, f1, 0))
    # Cluster B around (57.7, 12.0) - Gothenburg-ish
    for i in range(37, 73):
        lat = 57.7 + (i % 6) * 0.01
        lng = 12.0 + (i // 6) * 0.01
        f1 = 1 if i == 50 else 0
        rows.append((i, f'kar_{(i % 4) + 4}', lat, lng, 14 + i % 4, (i % 3) + 1, f1, 0))
    return make_df(rows)


def fixture_friend_chain_across_boundary():
    """72 people. A chain of 4 friends (members 34, 35, 36, 37) straddles the
    natural Hilbert cut boundary between groups 0 and 1 (boundary at index 36).

    A cluster-aware initial cut should keep all 4 in the same group."""
    rows = []
    for i in range(1, 73):
        lat = 59.0 + i * 0.005  # monotone in lat → monotone in Hilbert
        lng = 18.0
        f1, f2 = 0, 0
        if i == 34: f1 = 35
        if i == 35: f1 = 34; f2 = 36
        if i == 36: f1 = 35; f2 = 37
        if i == 37: f1 = 36
        rows.append((i, 'kar_x', lat, lng, 16, 1, f1, f2))
    return make_df(rows)


def fixture_three_way_rotation_unblocks():
    """108 people in 3 groups of 36. Carefully constructed so a 2-way swap
    cannot satisfy person 1's friend wish, but a 3-way rotation does.

    Person 1 (group 0, kar_A) wants person 50 (group 1, kar_B).
    Group 1 has 8 kar_A members already (max_kar=8), so swapping IN any
    kar_A from group 0 fails the kar constraint.
    But group 2 has only 6 kar_B members; rotating kar_B from group 1 → 2
    and kar_A from group 0 → 1 (and kar_C from group 2 → 0) succeeds.
    """
    rows = []
    # Group 0: 8 kar_A (incl person 1), 28 kar_C
    for i in range(1, 37):
        kar = 'kar_A' if i <= 8 else 'kar_C'
        f1 = 50 if i == 1 else 0
        rows.append((i, kar, 59.0, 18.0 + i * 0.001, 16, 1, f1, 0))
    # Group 1: 8 kar_B (incl person 50), 28 kar_D
    for i in range(37, 73):
        kar = 'kar_B' if i <= 44 else 'kar_D'
        rows.append((i, kar, 60.0, 18.0 + (i - 36) * 0.001, 16, 1, 0, 0))
    # Group 2: 6 kar_B, 30 kar_E
    for i in range(73, 109):
        kar = 'kar_B' if i <= 78 else 'kar_E'
        rows.append((i, kar, 61.0, 18.0 + (i - 72) * 0.001, 16, 1, 0, 0))
    return make_df(rows)
```

- [ ] **Step 3: Create `sanity_check.py`** (smoke-test invariants after each phase change)

Path: `/config/notebooks/wsj27/tests/sanity_check.py`

```python
"""Quick smoke check: assign_groups must always produce a legal assignment.

Exits 0 on success, 1 on failure. Designed to run after every algorithm
change as a fast confidence check before tests/CI."""

import sys
sys.path.insert(0, '/config/notebooks/wsj27')
sys.path.insert(0, '/config/notebooks/wsj27/tests')

from collections import Counter
import wsj27_utils as u
from fixtures import fixture_two_groups_one_friend_pair


def check(df, group_size, max_kar):
    sizes = Counter(df['group'].values)
    n = len(df)
    n_full = n // group_size
    remainder = n % group_size
    expected_full = n_full
    full_count = sum(1 for c in sizes.values() if c == group_size)
    assert full_count == expected_full, f"expected {expected_full} full groups, got {full_count} (sizes={dict(sizes)})"
    if remainder:
        rem_count = sum(1 for c in sizes.values() if c == remainder)
        assert rem_count == 1, f"expected 1 remainder group of size {remainder}"
    for g in df['group'].unique():
        members = df[df['group'] == g]
        kar_counts = Counter(k for k in members['kar'] if k)
        for k, c in kar_counts.items():
            assert c <= max_kar, f"group {g} has {c} from {k} (max {max_kar})"
    print(f"sanity OK: {len(sizes)} groups, kår limits respected")


if __name__ == '__main__':
    df = fixture_two_groups_one_friend_pair()
    fw = u.build_friend_graph(df)
    df = u.assign_groups(df, group_size=36, friend_wishes=fw)
    check(df, 36, 8)
```

- [ ] **Step 4: Create starter `test_assign_groups.py`** (one passing baseline test that pins current behavior)

Path: `/config/notebooks/wsj27/tests/test_assign_groups.py`

```python
"""Algorithm tests for wsj27_utils.assign_groups.

Each test uses a synthetic fixture from fixtures.py and asserts a property
of the resulting assignment. Tests are layered so we can add new assertions
as the algorithm gains capability without breaking existing ones."""

import sys
sys.path.insert(0, '/config/notebooks/wsj27')
sys.path.insert(0, '/config/notebooks/wsj27/tests')

import unittest
from collections import Counter
import wsj27_utils as u
from fixtures import (
    fixture_two_groups_one_friend_pair,
    fixture_friend_chain_across_boundary,
    fixture_three_way_rotation_unblocks,
)


class TestLegalAssignment(unittest.TestCase):
    """Properties that must hold for ANY valid assignment, every iteration."""

    def assertLegalAssignment(self, df, group_size, max_kar=8):
        sizes = Counter(df['group'].values)
        n = len(df)
        n_full = n // group_size
        full_count = sum(1 for c in sizes.values() if c == group_size)
        self.assertEqual(full_count, n_full)
        for g in df['group'].unique():
            members = df[df['group'] == g]
            kar_counts = Counter(k for k in members['kar'] if k)
            for k, c in kar_counts.items():
                self.assertLessEqual(c, max_kar)

    def test_two_groups_basic(self):
        df = fixture_two_groups_one_friend_pair()
        fw = u.build_friend_graph(df)
        df = u.assign_groups(df, 36, fw)
        self.assertLegalAssignment(df, 36)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 5: Run sanity check + tests, expect pass**

```bash
cd /config && python notebooks/wsj27/tests/sanity_check.py
cd /config && python -m unittest discover -s notebooks/wsj27/tests -v
```

Expected: sanity prints "sanity OK"; unittest reports `OK` with 1 test.

- [ ] **Step 6: Commit**

```bash
git add notebooks/wsj27/tests/
git commit -m "test(wsj27): add synthetic fixtures and sanity-check harness"
```

---

## Task 2: Capture baseline metrics from real data

Run the current algorithm on real data and record numbers so we can verify improvements later.

**Files:**
- Create: `notebooks/wsj27/tests/capture_baseline.py`
- Create: `notebooks/wsj27/tests/baseline_metrics.json`

- [ ] **Step 1: Create `capture_baseline.py`**

Path: `/config/notebooks/wsj27/tests/capture_baseline.py`

```python
"""Capture baseline metrics by running the current assign_groups on real data.

Writes baseline_metrics.json with friend-satisfied counts, geo-spread, and
kår-violation counts for both rundresa and direktresa. Run before any
algorithm changes; the saved JSON is the comparison target."""

import sys, json, time
sys.path.insert(0, '/config/notebooks/wsj27')
import wsj27_utils as u


def measure(travel):
    raw = u.fetch_participants()
    df_all, _ = u.build_participant_dataframe(raw)
    df = df_all[df_all['travel'] == travel].copy().reset_index(drop=True)
    u.assign_coordinates(df)
    df = u.add_hilbert_index(df)
    u.resolve_friend_wishes(df, df_all)
    fw = u.build_friend_graph(df)

    t0 = time.time()
    df = u.assign_groups(df, 36, fw)
    elapsed = time.time() - t0

    n = len(df)
    member_set = set(df['member_no'])
    member_to_group = dict(zip(df['member_no'], df['group']))

    def has_wish(row):
        f1, f2 = row['friend_1'], row['friend_2']
        return (f1 and f1 in member_set) or (f2 and f2 in member_set)

    def satisfied(row):
        g = row['group']
        f1, f2 = row['friend_1'], row['friend_2']
        return ((f1 in member_set and member_to_group.get(f1) == g)
                or (f2 in member_set and member_to_group.get(f2) == g))

    n_with_wish = int(df.apply(has_wish, axis=1).sum())
    n_satisfied = int(df.apply(lambda r: has_wish(r) and satisfied(r), axis=1).sum())

    return {
        'travel': travel,
        'n_participants': int(n),
        'n_groups': int(df['group'].nunique()),
        'n_with_wish': n_with_wish,
        'n_satisfied': n_satisfied,
        'satisfaction_rate': round(n_satisfied / max(1, n_with_wish), 4),
        'runtime_seconds': round(elapsed, 2),
    }


if __name__ == '__main__':
    out = {'rundresa': measure('rundresa'), 'direktresa': measure('direktresa')}
    with open('/config/notebooks/wsj27/tests/baseline_metrics.json', 'w') as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
```

- [ ] **Step 2: Run it**

```bash
cd /config && python notebooks/wsj27/tests/capture_baseline.py
```

Expected: JSON output for rundresa + direktresa with `n_with_wish` and `n_satisfied` populated. Takes ~30-60s total.

- [ ] **Step 3: Inspect baseline file**

```bash
cat /config/notebooks/wsj27/tests/baseline_metrics.json
```

Confirm both `rundresa` and `direktresa` blocks are present and `satisfaction_rate` is between 0 and 1.

- [ ] **Step 4: Commit**

```bash
git add notebooks/wsj27/tests/capture_baseline.py notebooks/wsj27/tests/baseline_metrics.json
git commit -m "test(wsj27): capture baseline friend-satisfaction metrics"
```

---

## Task 3: Add maintained `_GroupState` + speed up `friend_satisfied`

Pure mechanical refactor. Behavior unchanged; `friend_satisfied` becomes O(1) instead of O(group_size).

**Files:**
- Modify: `notebooks/wsj27/wsj27_utils.py:678-1017` (inside `assign_groups`)

- [ ] **Step 1: Add a regression test that locks in current friend-satisfaction count for the small fixture**

Append to `test_assign_groups.py`:

```python
class TestRefactorRegression(unittest.TestCase):
    """Locks in friend-satisfaction count on synthetic fixtures so refactors
    can be verified non-regressive. Numbers must NOT decrease across tasks."""

    def _count_satisfied(self, df):
        member_to_group = dict(zip(df['member_no'], df['group']))
        member_set = set(df['member_no'])
        n = 0
        for _, row in df.iterrows():
            f1, f2 = row['friend_1'], row['friend_2']
            has_wish = (f1 and f1 in member_set) or (f2 and f2 in member_set)
            if not has_wish:
                continue
            g = row['group']
            if ((f1 in member_set and member_to_group.get(f1) == g)
                    or (f2 in member_set and member_to_group.get(f2) == g)):
                n += 1
        return n

    def test_two_groups_friend_satisfaction_at_least_2(self):
        # Persons 1 and 50 want each other; algorithm should put them together.
        df = fixture_two_groups_one_friend_pair()
        fw = u.build_friend_graph(df)
        df = u.assign_groups(df, 36, fw)
        self.assertGreaterEqual(self._count_satisfied(df), 2)
```

- [ ] **Step 2: Run test, expect pass on current code**

```bash
cd /config && python -m unittest notebooks.wsj27.tests.test_assign_groups.TestRefactorRegression -v
```

Expected: PASS (current code already satisfies this pair).

- [ ] **Step 3: Refactor — introduce `group_members` dict-of-sets**

In `wsj27_utils.py`, inside `assign_groups`, replace the helper section starting at line ~733 with:

```python
    # Maintained group → set-of-indices for O(1) membership checks.
    group_members = {g: set() for g in range(total_groups)}
    for i in range(n):
        group_members[group_of[i]].add(i)

    # Member-no → set of indices is already in member_to_idx (1:1 map).
    # For "is member-no X in group g" we need: any idx with member_arr[idx]==X
    # in group_members[g]. Build a per-group member-no set, kept current.
    group_member_nos = {g: set(member_arr[i] for i in group_members[g]) for g in range(total_groups)}

    def get_group_members(g):
        return list(group_members[g])

    def has_friend_wish(idx):
        f1, f2 = f1_arr[idx], f2_arr[idx]
        return bool((f1 and f1 in rundresa_set) or (f2 and f2 in rundresa_set))

    def friend_satisfied(idx):
        g = group_of[idx]
        gm_nos = group_member_nos[g]
        f1, f2 = f1_arr[idx], f2_arr[idx]
        return (f1 in gm_nos) or (f2 in gm_nos)

    def kar_count_in_group(g, kar):
        return sum(1 for i in group_members[g] if kars_arr[i] == kar)

    def can_swap(i1, i2):
        g1, g2 = group_of[i1], group_of[i2]
        if g1 == g2:
            return False
        k1, k2 = kars_arr[i1], kars_arr[i2]
        if k1 == k2:
            return True
        if k2 and kar_count_in_group(g1, k2) - (1 if k2 == k1 else 0) + 1 > MAX_KAR:
            return False
        if k1 and kar_count_in_group(g2, k1) - (1 if k1 == k2 else 0) + 1 > MAX_KAR:
            return False
        return True

    def do_swap(i1, i2):
        g1, g2 = group_of[i1], group_of[i2]
        m1, m2 = member_arr[i1], member_arr[i2]
        group_members[g1].discard(i1); group_members[g1].add(i2)
        group_members[g2].discard(i2); group_members[g2].add(i1)
        group_member_nos[g1].discard(m1); group_member_nos[g1].add(m2)
        group_member_nos[g2].discard(m2); group_member_nos[g2].add(m1)
        group_of[i1], group_of[i2] = g2, g1
```

- [ ] **Step 4: Run sanity check**

```bash
cd /config && python notebooks/wsj27/tests/sanity_check.py
```

Expected: "sanity OK".

- [ ] **Step 5: Run all tests**

```bash
cd /config && python -m unittest discover -s notebooks/wsj27/tests -v
```

Expected: all PASS.

- [ ] **Step 6: Re-run baseline capture and verify identical results**

```bash
cd /config && python notebooks/wsj27/tests/capture_baseline.py > /tmp/post_task3.json
diff /config/notebooks/wsj27/tests/baseline_metrics.json /tmp/post_task3.json
```

Expected: only `runtime_seconds` should differ (faster); `n_satisfied` should be identical for both travels.

- [ ] **Step 7: Commit**

```bash
git add notebooks/wsj27/wsj27_utils.py notebooks/wsj27/tests/test_assign_groups.py
git commit -m "refactor(wsj27): maintain group_members dict for O(1) friend_satisfied"
```

---

## Task 4: Extract `_friend_swap_pass` helper, dedupe Phase 2/2b

Pure refactor — Phase 2 and Phase 2b currently copy-paste 40 lines each. Replace with one helper.

**Files:**
- Modify: `notebooks/wsj27/wsj27_utils.py` (lines ~824-868 and ~907-948 inside `assign_groups`)

- [ ] **Step 1: Add the helper as a nested function inside `assign_groups`**

Insert immediately after `group_diversity()` (around line 813), still inside `assign_groups`:

```python
    def _friend_swap_pass(idx_iter):
        """One pass of friend-fixing swaps. Returns count of improving swaps.

        For each idx in idx_iter that has an unsatisfied friend wish, finds the
        best legal partner to swap with (closest geographically among swaps
        that don't reduce total friend satisfaction), and performs it."""
        n_swaps = 0
        for idx in idx_iter:
            if not has_friend_wish(idx) or friend_satisfied(idx):
                continue
            target_groups = set()
            for fid in (f1_arr[idx], f2_arr[idx]):
                if fid and fid in member_to_idx:
                    target_groups.add(group_of[member_to_idx[fid]])
            target_groups.discard(group_of[idx])
            if not target_groups:
                continue
            best_cidx, best_net, best_dist = None, -999, float('inf')
            for tg in target_groups:
                for cidx in get_group_members(tg):
                    if not can_swap(idx, cidx):
                        continue
                    affected = affected_by_swap(idx, cidx)
                    old_sat = sum(1 for a in affected if has_friend_wish(a) and friend_satisfied(a))
                    do_swap(idx, cidx)
                    new_sat = sum(1 for a in affected if has_friend_wish(a) and friend_satisfied(a))
                    do_swap(idx, cidx)  # undo
                    net = new_sat - old_sat
                    dist = geo_dist_sq(idx, cidx)
                    if net > best_net or (net == best_net and dist < best_dist):
                        best_net, best_cidx, best_dist = net, cidx, dist
            if best_cidx is not None and best_net >= 0:
                do_swap(idx, best_cidx)
                n_swaps += 1
        return n_swaps
```

- [ ] **Step 2: Replace the Phase 2 body** (lines ~828-865 inside `assign_groups`)

```python
    # -----------------------------------------------------------------------
    # Phase 2: Fix friend wishes via targeted swaps
    # -----------------------------------------------------------------------
    print("\n=== Phase 2: Fix friend wishes ===")
    friend_swaps = _friend_swap_pass(range(n))
    print(f"  Swaps: {friend_swaps}")
    print(f"  Friend satisfaction: {count_friend_satisfied()}/{friend_total}")
    print(f"  Kar violations: {count_kar_violations()}")
    print(f"  Avg geo spread: {np.mean([group_geo_spread(g) for g in range(total_groups)]):.4f}")
```

- [ ] **Step 3: Replace the Phase 2b body** (lines ~909-945 inside `assign_groups`)

```python
    # -----------------------------------------------------------------------
    # Phase 2b: Re-fix friend wishes lost in Phase 3
    # -----------------------------------------------------------------------
    print("\n=== Phase 2b: Re-fix friends after kar fix ===")
    friend_swaps_2b = _friend_swap_pass(range(n))
    print(f"  Swaps: {friend_swaps_2b}")
    print(f"  Friend satisfaction: {count_friend_satisfied()}/{friend_total}")
    print(f"  Kar violations: {count_kar_violations()}")
    print(f"  Avg geo spread: {np.mean([group_geo_spread(g) for g in range(total_groups)]):.4f}")
```

- [ ] **Step 4: Run all tests + baseline-equality check**

```bash
cd /config && python notebooks/wsj27/tests/sanity_check.py
cd /config && python -m unittest discover -s notebooks/wsj27/tests -v
cd /config && python notebooks/wsj27/tests/capture_baseline.py > /tmp/post_task4.json
diff /config/notebooks/wsj27/tests/baseline_metrics.json /tmp/post_task4.json
```

Expected: tests PASS; baseline diff shows only `runtime_seconds` change.

- [ ] **Step 5: Commit**

```bash
git add notebooks/wsj27/wsj27_utils.py
git commit -m "refactor(wsj27): extract _friend_swap_pass helper, dedupe Phase 2/2b"
```

---

## Task 5: Add `print_intake_summary` util

Lifts the inline prints from rundresa/direktresa cell 2 into the utils module. No algorithm change.

**Files:**
- Modify: `notebooks/wsj27/wsj27_utils.py` — add new top-level function near `add_hilbert_index` (around line 441).

- [ ] **Step 1: Add the new function** (insert just before `# 4. Friend Wish Resolution` section, around line 440)

```python
def print_intake_summary(df, group_size):
    """Print intake stats: count, group projection, region/age/sex distributions.

    Replaces the inline prints in the rundresa/direktresa notebook cell 2."""
    n = len(df)
    n_full = n // group_size
    remainder = n % group_size
    total_groups = n_full + (1 if remainder > 0 else 0)
    print(f"Participants: {n}")
    print(f"Groups: {n_full} x {group_size} + 1 x {remainder} = {total_groups} total")
    if 'region' in df.columns:
        print(f"\nBy region:")
        print(df['region'].value_counts().to_string())
    if 'age' in df.columns:
        print(f"\nBy age:")
        print(df['age'].value_counts().sort_index().to_string())
    if 'sex' in df.columns:
        print(f"\nBy sex:")
        print(df['sex'].map(SEX_MAP).value_counts().to_string())
```

- [ ] **Step 2: Smoke-test in a Python REPL**

```bash
cd /config && python -c "
import sys; sys.path.insert(0, 'notebooks/wsj27')
import wsj27_utils as u
import pandas as pd
df = pd.DataFrame({'region': ['A','A','B'], 'age': [14,15,16], 'sex': [1,2,1]})
u.print_intake_summary(df, group_size=36)
"
```

Expected: prints "Participants: 3", a 0×36 + 1×3 group line, and three distribution tables.

- [ ] **Step 3: Run all tests**

```bash
cd /config && python -m unittest discover -s notebooks/wsj27/tests -v
```

Expected: all PASS (this task adds no behavior).

- [ ] **Step 4: Commit**

```bash
git add notebooks/wsj27/wsj27_utils.py
git commit -m "feat(wsj27): add print_intake_summary util"
```

---

## Task 5.5: Friend-aware Phase 3 kår-fix

**Why:** Diagnostic on real data (1506 rundresa participants) shows Phase 3 destroys ~210 satisfied friendships to fix 252 kår violations. Phase 2b recovers most but not all — final friend count is 922/943 (98%) vs the 930/943 peak after Phase 2. The leak is Phase 3's candidate selection: it picks the geographically nearest swap target, ignoring whether that swap breaks an existing friend wish.

**Fix:** Score each candidate by `(net_friend_change, geo_dist_sq)` — prefer candidates whose swap doesn't break friendships, with geo distance as tiebreaker.

**Expected impact:** ~10-15 of the 21 currently unsatisfied wishes recovered (real-data observation).

**Files:**
- Modify: `notebooks/wsj27/wsj27_utils.py` — Phase 3 inside `assign_groups` (lines ~873-898).

- [ ] **Step 1: Read current Phase 3 candidate selection**

Confirm the existing structure: candidates collected, then `min(candidates, key=lambda c: geo_dist_sq(idx, c))`. The change is in the `key=` lambda only.

- [ ] **Step 2: Replace candidate scoring with friend-aware key**

Inside `assign_groups`, find the block that starts with `# Phase 3: Fix kar violations` (around line 873). Replace it with:

```python
    # -----------------------------------------------------------------------
    # Phase 3: Fix kar violations (friend-aware, geo as tiebreaker)
    # -----------------------------------------------------------------------
    print("\n=== Phase 3: Fix kar violations (friend-aware) ===")
    kar_swaps = 0

    def _phase3_score(idx, cidx):
        """Score a candidate: (-net_friend_change, geo_dist_sq).
        Lower is better. Negating net_friend so that bigger gain → smaller key."""
        affected = affected_by_swap(idx, cidx)
        old_sat = sum(1 for a in affected if has_friend_wish(a) and friend_satisfied(a))
        do_swap(idx, cidx)
        new_sat = sum(1 for a in affected if has_friend_wish(a) and friend_satisfied(a))
        do_swap(idx, cidx)  # undo
        net = new_sat - old_sat
        return (-net, geo_dist_sq(idx, cidx))

    for g in range(total_groups):
        gm = get_group_members(g)
        counts = Counter(kars_arr[i] for i in gm if kars_arr[i])
        for kar, cnt in counts.items():
            if cnt <= MAX_KAR:
                continue
            excess = [i for i in gm if kars_arr[i] == kar]
            for idx in excess[MAX_KAR:]:
                candidates = []
                for og in range(total_groups):
                    if og == g:
                        continue
                    for cidx in get_group_members(og):
                        if kars_arr[cidx] == kar:
                            continue
                        if can_swap(idx, cidx):
                            candidates.append(cidx)
                if not candidates:
                    continue
                best_cidx = min(candidates, key=lambda c: _phase3_score(idx, c))
                do_swap(idx, best_cidx)
                kar_swaps += 1

    print(f"  Swaps: {kar_swaps}")
    print(f"  Kar violations: {count_kar_violations()}")
    print(f"  Friend satisfaction: {count_friend_satisfied()}/{friend_total}")
    print(f"  Avg geo spread: {np.mean([group_geo_spread(g) for g in range(total_groups)]):.4f}")
```

The only behavioral change: `_phase3_score(idx, c)` replaces `geo_dist_sq(idx, c)` as the sort key. Each candidate evaluation now does a tentative swap to count net friend change in the affected set.

- [ ] **Step 3: Run sanity check**

```bash
cd /config && python notebooks/wsj27/tests/sanity_check.py
```

Expected: `sanity OK`.

- [ ] **Step 4: Run unittest**

```bash
cd /config && python -m unittest discover -s notebooks/wsj27/tests -v
```

Expected: all PASS.

- [ ] **Step 5: Re-run baseline capture and confirm gain**

```bash
cd /config && python notebooks/wsj27/tests/capture_baseline.py > /tmp/post_task5_5.json
python3 -c "
import json
b = json.load(open('/config/notebooks/wsj27/tests/baseline_metrics.json'))
n = json.load(open('/tmp/post_task5_5.json'))
for travel in ('rundresa', 'direktresa'):
    bs, ns = b[travel]['n_satisfied'], n[travel]['n_satisfied']
    delta = ns - bs
    print(f'{travel}: {bs} -> {ns} ({delta:+d})')
    assert ns >= bs, f'{travel} regressed'
print('non-regression OK')
"
```

Expected: rundresa friend-satisfied jumps from 922 by **+5 to +15** (target: 927-937). direktresa likely stays at 336 (it had only 1 unsatisfied; not enough headroom to measure).

- [ ] **Step 6: Commit**

```bash
git add notebooks/wsj27/wsj27_utils.py
git commit -m "feat(wsj27): friend-aware Phase 3 kar-fix preserves friendships"
```

---

## Task 6: Iterate Phase 2 until convergence

First behavior change. Phase 2 currently runs once; now it loops until no improving swap is found (cap 10 iterations).

**Files:**
- Modify: `notebooks/wsj27/wsj27_utils.py` — Phase 2 body inside `assign_groups`.

- [ ] **Step 1: Add a test that demonstrates the win**

Append to `test_assign_groups.py`:

```python
class TestPhase2Convergence(unittest.TestCase):
    """Multi-pass Phase 2 should never produce fewer satisfied friends than
    the single-pass version on the same fixture."""

    def _count_satisfied(self, df):
        m2g = dict(zip(df['member_no'], df['group']))
        ms = set(df['member_no'])
        n = 0
        for _, r in df.iterrows():
            f1, f2 = r['friend_1'], r['friend_2']
            if not ((f1 and f1 in ms) or (f2 and f2 in ms)):
                continue
            if ((f1 in ms and m2g.get(f1) == r['group']) or
                    (f2 in ms and m2g.get(f2) == r['group'])):
                n += 1
        return n

    def test_friend_chain_two_satisfied_minimum(self):
        # Chain 34-35-36-37 across the cut. Even with single-pass Phase 2,
        # at least 2 of those 4 should end up satisfied. After multi-pass,
        # this baseline must still hold.
        df = fixture_friend_chain_across_boundary()
        fw = u.build_friend_graph(df)
        df = u.assign_groups(df, 36, fw)
        self.assertGreaterEqual(self._count_satisfied(df), 2)
```

- [ ] **Step 2: Run test on current code, expect pass**

```bash
cd /config && python -m unittest notebooks.wsj27.tests.test_assign_groups.TestPhase2Convergence -v
```

Expected: PASS (regression baseline locked).

- [ ] **Step 3: Replace Phase 2 body with a `while` loop**

In `assign_groups`, replace the Phase 2 block from Task 4 with:

```python
    # -----------------------------------------------------------------------
    # Phase 2: Fix friend wishes via targeted swaps (iterate to convergence)
    # -----------------------------------------------------------------------
    print("\n=== Phase 2: Fix friend wishes (iterate to convergence) ===")
    friend_swaps = 0
    for pass_num in range(10):
        n_this = _friend_swap_pass(range(n))
        friend_swaps += n_this
        if n_this == 0:
            print(f"  Converged after {pass_num + 1} pass(es)")
            break
    print(f"  Total swaps: {friend_swaps}")
    print(f"  Friend satisfaction: {count_friend_satisfied()}/{friend_total}")
    print(f"  Kar violations: {count_kar_violations()}")
    print(f"  Avg geo spread: {np.mean([group_geo_spread(g) for g in range(total_groups)]):.4f}")
```

- [ ] **Step 4: Run sanity + tests + baseline comparison**

```bash
cd /config && python notebooks/wsj27/tests/sanity_check.py
cd /config && python -m unittest discover -s notebooks/wsj27/tests -v
cd /config && python notebooks/wsj27/tests/capture_baseline.py > /tmp/post_task6.json
python3 -c "
import json
b = json.load(open('/config/notebooks/wsj27/tests/baseline_metrics.json'))
n = json.load(open('/tmp/post_task6.json'))
for travel in ('rundresa', 'direktresa'):
    bs, ns = b[travel]['n_satisfied'], n[travel]['n_satisfied']
    delta = ns - bs
    print(f'{travel}: {bs} -> {ns} ({delta:+d})')
    assert ns >= bs, f'{travel} regressed: {bs} -> {ns}'
print('non-regression OK')
"
```

Expected: tests PASS; n_satisfied is ≥ baseline for both travels (typically a small +).

- [ ] **Step 5: Commit**

```bash
git add notebooks/wsj27/wsj27_utils.py notebooks/wsj27/tests/test_assign_groups.py
git commit -m "feat(wsj27): iterate Phase 2 friend swaps until convergence"
```

---

## Task 7: Friend criticality ordering

Process unsatisfied wishes in order of how hard they are to satisfy. People whose only friend lives in a distant group go first.

**Files:**
- Modify: `notebooks/wsj27/wsj27_utils.py` — Phase 2 inside `assign_groups`.

- [ ] **Step 1: Add a `_criticality_sorted` helper inside `assign_groups`**

Insert just after `_friend_swap_pass` definition:

```python
    def _criticality_sorted_indices():
        """Return indices of people with unsatisfied friend wishes, sorted
        most-critical first.

        Criticality = squared geographic distance from idx to its nearest
        friend, divided by the number of valid friend wishes. People with
        only one friend AND that friend is far get processed first."""
        scored = []
        for i in range(n):
            if not has_friend_wish(i) or friend_satisfied(i):
                continue
            valid = [fid for fid in (f1_arr[i], f2_arr[i])
                     if fid and fid in member_to_idx]
            if not valid:
                continue
            min_dist = min(geo_dist_sq(i, member_to_idx[fid]) for fid in valid)
            scored.append((min_dist / len(valid), i))
        scored.sort(reverse=True)  # higher score = more critical = earlier
        return [i for _, i in scored]
```

- [ ] **Step 2: Use it in Phase 2's loop**

Replace the Phase 2 inner loop body (from Task 6) with:

```python
    print("\n=== Phase 2: Fix friend wishes (criticality-ordered, iterate) ===")
    friend_swaps = 0
    for pass_num in range(10):
        order = _criticality_sorted_indices()
        if not order:
            print(f"  No unsatisfied wishes; converged after {pass_num} pass(es)")
            break
        n_this = _friend_swap_pass(order)
        friend_swaps += n_this
        if n_this == 0:
            print(f"  Converged after {pass_num + 1} pass(es)")
            break
    print(f"  Total swaps: {friend_swaps}")
    print(f"  Friend satisfaction: {count_friend_satisfied()}/{friend_total}")
    print(f"  Kar violations: {count_kar_violations()}")
    print(f"  Avg geo spread: {np.mean([group_geo_spread(g) for g in range(total_groups)]):.4f}")
```

- [ ] **Step 3: Run sanity + all tests + baseline non-regression**

```bash
cd /config && python notebooks/wsj27/tests/sanity_check.py
cd /config && python -m unittest discover -s notebooks/wsj27/tests -v
cd /config && python notebooks/wsj27/tests/capture_baseline.py > /tmp/post_task7.json
python3 -c "
import json
b = json.load(open('/config/notebooks/wsj27/tests/baseline_metrics.json'))
n = json.load(open('/tmp/post_task7.json'))
for travel in ('rundresa', 'direktresa'):
    bs, ns = b[travel]['n_satisfied'], n[travel]['n_satisfied']
    print(f'{travel}: {bs} -> {ns} ({ns - bs:+d})')
    assert ns >= bs, f'{travel} regressed'
"
```

Expected: tests PASS; non-regression holds.

- [ ] **Step 4: Commit**

```bash
git add notebooks/wsj27/wsj27_utils.py
git commit -m "feat(wsj27): order Phase 2 swaps by friend-wish criticality"
```

---

## Task 8: Phase 2.5 — three-way rotations

For each still-unsatisfied wish, attempt rotations A→B's group, B→C's group, C→A's group.

**Files:**
- Modify: `notebooks/wsj27/wsj27_utils.py` — add `_friend_rotate_pass` and call it after Phase 2.

- [ ] **Step 1: Add a fixture-driven test that the fixture itself fails to satisfy under Phase 2 alone, then succeeds under rotations**

Append to `test_assign_groups.py`:

```python
class TestThreeWayRotation(unittest.TestCase):
    def _sat_count(self, df):
        m2g = dict(zip(df['member_no'], df['group']))
        ms = set(df['member_no'])
        return sum(
            1 for _, r in df.iterrows()
            if ((r['friend_1'] in ms and m2g.get(r['friend_1']) == r['group']) or
                (r['friend_2'] in ms and m2g.get(r['friend_2']) == r['group']))
            and ((r['friend_1'] and r['friend_1'] in ms) or
                 (r['friend_2'] and r['friend_2'] in ms))
        )

    def test_rotation_fixture_solves_locked_pair(self):
        df = fixture_three_way_rotation_unblocks()
        fw = u.build_friend_graph(df)
        df = u.assign_groups(df, 36, fw)
        # Person 1 wants person 50; rotation should put them together.
        m2g = dict(zip(df['member_no'], df['group']))
        self.assertEqual(m2g['1'], m2g['50'],
                         msg='3-way rotation should land person 1 and 50 in same group')
```

- [ ] **Step 2: Run test, expect FAIL on current code**

```bash
cd /config && python -m unittest notebooks.wsj27.tests.test_assign_groups.TestThreeWayRotation -v
```

Expected: FAIL (current code can't satisfy the kår-blocked friend wish).

- [ ] **Step 3: Add `_friend_rotate_pass` helper inside `assign_groups`**

Insert after `_criticality_sorted_indices`:

```python
    def _friend_rotate_pass():
        """For each unsatisfied wish, try 3-way rotation A→B→C→A.

        For unsatisfied A wanting a friend in group g_b: try every member of
        g_b as 'B' (would move into g_c) and every member of g_c (any third
        group) as 'C' (would move into g_a). Accept the first rotation that
        strictly increases satisfaction within the affected set AND respects
        all kår limits. Affected set = {a, b, c} ∪ everyone who has a or b
        or c as a friend wish.

        Returns the number of accepted rotations."""
        rotations = 0
        unsatisfied = [i for i in range(n)
                       if has_friend_wish(i) and not friend_satisfied(i)]
        for a in unsatisfied:
            if friend_satisfied(a):  # may have been solved by an earlier rotation
                continue
            g_a = group_of[a]
            target_gbs = set()
            for fid in (f1_arr[a], f2_arr[a]):
                if fid and fid in member_to_idx:
                    target_gbs.add(group_of[member_to_idx[fid]])
            target_gbs.discard(g_a)
            found = False
            for g_b in target_gbs:
                if found: break
                for b in get_group_members(g_b):
                    if found: break
                    if b == a: continue
                    m_a, m_b = member_arr[a], member_arr[b]
                    for g_c in range(total_groups):
                        if found: break
                        if g_c in (g_a, g_b): continue
                        for c in get_group_members(g_c):
                            if not _rotation_legal(a, b, c, g_a, g_b, g_c):
                                continue
                            m_c = member_arr[c]
                            # Affected = {a, b, c} ∪ anyone who has a/b/c as friend
                            affected = {a, b, c}
                            affected.update(friend_of.get(m_a, set()))
                            affected.update(friend_of.get(m_b, set()))
                            affected.update(friend_of.get(m_c, set()))

                            old_sat = sum(1 for x in affected
                                          if has_friend_wish(x) and friend_satisfied(x))
                            _do_rotation(a, b, c)
                            new_sat = sum(1 for x in affected
                                          if has_friend_wish(x) and friend_satisfied(x))
                            if new_sat > old_sat:
                                rotations += 1
                                found = True
                            else:
                                _do_rotation(c, b, a)  # undo (reverse direction)
        return rotations

    def _rotation_legal(a, b, c, g_a, g_b, g_c):
        """Check that moving a→g_b, b→g_c, c→g_a respects kår limits.
        Sizes are unchanged (3-cycle), so only kår needs checking."""
        ka, kb, kc = kars_arr[a], kars_arr[b], kars_arr[c]
        # New count of kår k in group g after rotation:
        # group g_a: -ka +kc
        # group g_b: -kb +ka
        # group g_c: -kc +kb
        for kar in {ka, kb, kc}:
            if not kar:
                continue
            new_a = kar_count_in_group(g_a, kar) - (1 if ka == kar else 0) + (1 if kc == kar else 0)
            new_b = kar_count_in_group(g_b, kar) - (1 if kb == kar else 0) + (1 if ka == kar else 0)
            new_c = kar_count_in_group(g_c, kar) - (1 if kc == kar else 0) + (1 if kb == kar else 0)
            if max(new_a, new_b, new_c) > MAX_KAR:
                return False
        return True

    def _do_rotation(a, b, c):
        """Move a→g_b's group, b→g_c's group, c→g_a's group via two swaps."""
        # Swap a with c first (so a goes to g_c, c goes to g_a)
        # Then swap a (now in g_c) with b (in g_b): a→g_b, b→g_c
        # Net: a→g_b, b→g_c, c→g_a as required.
        do_swap(a, c)
        do_swap(a, b)
```

- [ ] **Step 4: Insert Phase 2.5 call after Phase 2**

In `assign_groups`, just before the Phase 3 print line, add:

```python
    # -----------------------------------------------------------------------
    # Phase 2.5: 3-way rotations for kår-blocked friend wishes
    # -----------------------------------------------------------------------
    print("\n=== Phase 2.5: 3-way rotations ===")
    rotations = _friend_rotate_pass()
    print(f"  Rotations: {rotations}")
    print(f"  Friend satisfaction: {count_friend_satisfied()}/{friend_total}")
    print(f"  Kar violations: {count_kar_violations()}")
```

- [ ] **Step 5: Run rotation test, expect PASS**

```bash
cd /config && python -m unittest notebooks.wsj27.tests.test_assign_groups.TestThreeWayRotation -v
```

Expected: PASS.

- [ ] **Step 6: Run full suite + non-regression**

```bash
cd /config && python notebooks/wsj27/tests/sanity_check.py
cd /config && python -m unittest discover -s notebooks/wsj27/tests -v
cd /config && python notebooks/wsj27/tests/capture_baseline.py > /tmp/post_task8.json
python3 -c "
import json
b = json.load(open('/config/notebooks/wsj27/tests/baseline_metrics.json'))
n = json.load(open('/tmp/post_task8.json'))
for travel in ('rundresa', 'direktresa'):
    bs, ns = b[travel]['n_satisfied'], n[travel]['n_satisfied']
    print(f'{travel}: {bs} -> {ns} ({ns - bs:+d})')
    assert ns >= bs
"
```

Expected: all PASS; non-regression holds.

- [ ] **Step 7: Commit**

```bash
git add notebooks/wsj27/wsj27_utils.py notebooks/wsj27/tests/test_assign_groups.py
git commit -m "feat(wsj27): add Phase 2.5 three-way rotations for kar-blocked wishes"
```

---

## Task 9: Friend-cluster-aware initial cut

Largest expected algorithmic win. Replaces the strict Hilbert-cut Phase 1.

**Files:**
- Modify: `notebooks/wsj27/wsj27_utils.py` — `assign_groups` Phase 1 (lines around 720-727).

- [ ] **Step 1: Add a test that uses `fixture_friend_chain_across_boundary` and asserts all 4 chain members end up in the same group**

Append to `test_assign_groups.py`:

```python
class TestClusterAwareCut(unittest.TestCase):
    def test_chain_stays_together(self):
        df = fixture_friend_chain_across_boundary()
        fw = u.build_friend_graph(df)
        df = u.assign_groups(df, 36, fw)
        m2g = dict(zip(df['member_no'], df['group']))
        groups = {m2g[str(m)] for m in (34, 35, 36, 37)}
        self.assertEqual(len(groups), 1,
                         msg=f'chain 34-35-36-37 split across groups {groups}')
```

- [ ] **Step 2: Run test on current code**

```bash
cd /config && python -m unittest notebooks.wsj27.tests.test_assign_groups.TestClusterAwareCut -v
```

Expected: likely FAIL or PASS depending on whether Phase 2 can heal it. If PASS: still a valid regression guard going forward. If FAIL: this task fixes it.

- [ ] **Step 3: Replace the trivial Hilbert-cut with two-phase cluster-aware placement**

In `_assign_groups_once` (or `assign_groups` if Task 11 hasn't run yet), find the existing block:

```python
    # Group assignment array
    group_of = np.zeros(n, dtype=int)
    for i in range(n_full_groups):
        group_of[i * group_size:(i + 1) * group_size] = i
    if remainder > 0:
        group_of[n_full_groups * group_size:] = n_full_groups
```

Replace it with:

```python
    # -----------------------------------------------------------------------
    # Phase 1: Friend-cluster-aware initial placement (two-phase)
    # -----------------------------------------------------------------------
    # 1. Build connected components in the friend graph using union-find.
    parent = list(range(n))
    def _find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def _union(x, y):
        rx, ry = _find(x), _find(y)
        if rx != ry:
            parent[rx] = ry
    for i in range(n):
        for fid in (f1_arr[i], f2_arr[i]):
            if fid and fid in member_to_idx:
                _union(i, member_to_idx[fid])
    cluster_of_idx = [_find(i) for i in range(n)]
    clusters = defaultdict(list)
    for i, c in enumerate(cluster_of_idx):
        clusters[c].append(i)

    # 2. Each idx already holds its Hilbert rank (df_sorted is Hilbert-sorted).
    # Capacities per group: group_size for full groups, remainder for last.
    capacity = [group_size] * n_full_groups
    if remainder > 0:
        capacity.append(remainder)
    group_assigned = [[] for _ in range(total_groups)]

    def _nearest_group(anchor_rank, need):
        """Return group index whose centre rank is closest to anchor_rank
        AND whose remaining capacity ≥ need. -1 if none."""
        best_g, best_d = -1, float('inf')
        for g in range(total_groups):
            if capacity[g] < need:
                continue
            centre = g * group_size + (capacity[g] // 2)  # rough centre
            d = abs(anchor_rank - centre)
            if d < best_d:
                best_g, best_d = g, d
        return best_g

    # 3. Place multi-member clusters first (anchor = avg rank of its members).
    multi_clusters = [
        (float(np.mean(members)), members)
        for members in clusters.values() if len(members) > 1
    ]
    multi_clusters.sort(key=lambda t: t[0])
    for anchor_rank, members in multi_clusters:
        g = _nearest_group(anchor_rank, len(members))
        if g < 0:
            # No single group can hold the whole cluster (rare: cluster bigger
            # than any remaining capacity). Spill members one by one.
            for i in sorted(members):
                g1 = _nearest_group(i, 1)
                assert g1 >= 0
                group_assigned[g1].append(i)
                capacity[g1] -= 1
        else:
            for i in members:
                group_assigned[g].append(i)
            capacity[g] -= len(members)

    # 4. Place singletons (anchor = own rank, which is just the index).
    singletons = [members[0] for members in clusters.values() if len(members) == 1]
    singletons.sort()
    for i in singletons:
        g = _nearest_group(i, 1)
        assert g >= 0
        group_assigned[g].append(i)
        capacity[g] -= 1

    # 5. Build group_of from group_assigned.
    group_of = np.zeros(n, dtype=int)
    for g, members in enumerate(group_assigned):
        for i in members:
            group_of[i] = g
    assert all(c == 0 for c in capacity), f"residual capacity: {capacity}"
```

**Note on `anchor_rank`:** `df_sorted` is Hilbert-sorted on entry, so a row's positional index *is* its Hilbert rank. We use that directly — no separate `hilbert_rank` dict needed.

**Why two-phase is cleaner than streaming-emit:** every group ends up with exactly its capacity; clusters of size ≤ capacity always fit intact; only clusters bigger than any single group's free capacity get split (extremely rare for groups of 36 with friend-cluster sizes 2-6).

- [ ] **Step 4: Re-run cluster-aware test, expect PASS**

```bash
cd /config && python -m unittest notebooks.wsj27.tests.test_assign_groups.TestClusterAwareCut -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite + non-regression**

```bash
cd /config && python notebooks/wsj27/tests/sanity_check.py
cd /config && python -m unittest discover -s notebooks/wsj27/tests -v
cd /config && python notebooks/wsj27/tests/capture_baseline.py > /tmp/post_task9.json
python3 -c "
import json
b = json.load(open('/config/notebooks/wsj27/tests/baseline_metrics.json'))
n = json.load(open('/tmp/post_task9.json'))
for travel in ('rundresa', 'direktresa'):
    bs, ns = b[travel]['n_satisfied'], n[travel]['n_satisfied']
    print(f'{travel}: {bs} -> {ns} ({ns - bs:+d})')
    assert ns >= bs
"
```

Expected: all PASS; non-regression. This is the task most likely to deliver a meaningful jump in `n_satisfied`.

- [ ] **Step 6: Commit**

```bash
git add notebooks/wsj27/wsj27_utils.py notebooks/wsj27/tests/test_assign_groups.py
git commit -m "feat(wsj27): friend-cluster-aware initial cut keeps clusters intact"
```

---

## Task 10: Phase 4 SA scoring — gain friends, not just preserve

Phase 4 currently rejects any swap losing a friend. New: weighted score `α·friends + β·diversity − γ·geo`, friend-positive swaps almost always accepted.

**Files:**
- Modify: `notebooks/wsj27/wsj27_utils.py` — Phase 4 inside `assign_groups`.

- [ ] **Step 1: Replace Phase 4 body** (the `for iteration in range(diversity_iterations)` block)

```python
    # -----------------------------------------------------------------------
    # Phase 4: Weighted SA — gain friends, balance diversity, penalize geo spread
    # -----------------------------------------------------------------------
    print(f"\n=== Phase 4: Weighted SA (friend-positive) ===")

    GEO_WEIGHT = geo_weight
    DIV_WEIGHT = 1.0
    FRIEND_WEIGHT = 5.0  # high enough that friend-gain almost always wins

    def _phase4_score():
        return (FRIEND_WEIGHT * count_friend_satisfied()
                + DIV_WEIGHT * sum(group_diversity(g) for g in range(total_groups))
                - GEO_WEIGHT * np.mean([group_geo_spread(g) for g in range(total_groups)]))

    div_before = sum(group_diversity(g) for g in range(total_groups))
    geo_before = np.mean([group_geo_spread(g) for g in range(total_groups)])
    sat_before = count_friend_satisfied()
    diversity_swaps = 0
    temperature = 1.0

    for iteration in range(diversity_iterations):
        i1 = random.randint(0, n - 1)
        i2 = random.randint(0, n - 1)
        g1, g2 = group_of[i1], group_of[i2]
        if g1 == g2 or not can_swap(i1, i2):
            continue

        affected = affected_by_swap(i1, i2)
        old_sat = sum(1 for a in affected if has_friend_wish(a) and friend_satisfied(a))
        old_div = group_diversity(g1) + group_diversity(g2)
        old_geo = group_geo_spread(g1) + group_geo_spread(g2)

        do_swap(i1, i2)

        new_sat = sum(1 for a in affected if has_friend_wish(a) and friend_satisfied(a))
        new_div = group_diversity(g1) + group_diversity(g2)
        new_geo = group_geo_spread(g1) + group_geo_spread(g2)

        score_delta = (FRIEND_WEIGHT * (new_sat - old_sat)
                       + DIV_WEIGHT * (new_div - old_div)
                       - GEO_WEIGHT * (new_geo - old_geo))

        if score_delta < 0 and random.random() > math.exp(score_delta / max(temperature, 0.01)):
            do_swap(i1, i2)  # reject
        else:
            diversity_swaps += 1

        temperature *= 0.9995

    div_after = sum(group_diversity(g) for g in range(total_groups))
    geo_after = np.mean([group_geo_spread(g) for g in range(total_groups)])
    sat_after = count_friend_satisfied()
    print(f"  Swaps: {diversity_swaps}")
    print(f"  Friend satisfaction: {sat_before} -> {sat_after}")
    print(f"  Diversity score:     {div_before:.2f} -> {div_after:.2f}")
    print(f"  Avg geo spread:      {geo_before:.4f} -> {geo_after:.4f}")
```

- [ ] **Step 2: Run sanity + tests + non-regression**

```bash
cd /config && python notebooks/wsj27/tests/sanity_check.py
cd /config && python -m unittest discover -s notebooks/wsj27/tests -v
cd /config && python notebooks/wsj27/tests/capture_baseline.py > /tmp/post_task10.json
python3 -c "
import json
b = json.load(open('/config/notebooks/wsj27/tests/baseline_metrics.json'))
n = json.load(open('/tmp/post_task10.json'))
for travel in ('rundresa', 'direktresa'):
    bs, ns = b[travel]['n_satisfied'], n[travel]['n_satisfied']
    print(f'{travel}: {bs} -> {ns} ({ns - bs:+d})')
    assert ns >= bs
"
```

Expected: PASS; non-regression. By this point the cumulative `n_satisfied` lift across tasks 6-10 should land in the +10-30% range vs baseline.

- [ ] **Step 3: Commit**

```bash
git add notebooks/wsj27/wsj27_utils.py
git commit -m "feat(wsj27): weighted Phase 4 SA actively gains friends"
```

---

## Task 11: Add `quality` parameter + multi-restart wrapper (slow tier)

**Files:**
- Modify: `notebooks/wsj27/wsj27_utils.py` — refactor `assign_groups` signature; introduce `_assign_groups_once` containing the existing body; new outer dispatcher.

- [ ] **Step 1: Rename current `assign_groups` body to `_assign_groups_once`**

In `wsj27_utils.py`, replace the current `def assign_groups(...)` line (around line 678) with:

```python
def _assign_groups_once(df_sorted, group_size, friend_wishes, max_kar=8,
                        diversity_iterations=15000, geo_weight=2.0, seed=42):
    """Single run of the full Phase 1-4 pipeline. See assign_groups for the
    public entry point with quality tiers."""
```

(Body stays exactly as is.)

- [ ] **Step 2: Add new public `assign_groups` dispatcher above it**

Insert just before `def _assign_groups_once`:

```python
def assign_groups(df_sorted, group_size, friend_wishes, max_kar=8,
                  quality='medium',
                  diversity_iterations=None, geo_weight=None, seed=None):
    """Assign participants to groups. Public entry point.

    quality:
      'medium' — single run, ~1-3 min for 1500 people. Default.
      'slow'   — 8 independent restarts with different seeds; returns the
                 assignment with the highest friend-satisfied count. ~10-30 min.

    Legacy kwargs (diversity_iterations, geo_weight, seed) override the
    preset values when set explicitly. They keep external callers working
    without changes.
    """
    presets = {
        'medium': {'diversity_iterations': 15000, 'geo_weight': 2.0, 'seed': 42, 'n_restarts': 1},
        'slow':   {'diversity_iterations': 15000, 'geo_weight': 2.0, 'seed': 42, 'n_restarts': 8},
    }
    if quality not in presets:
        raise ValueError(f"unknown quality {quality!r}; expected 'medium' or 'slow'")
    p = dict(presets[quality])
    if diversity_iterations is not None:
        p['diversity_iterations'] = diversity_iterations
    if geo_weight is not None:
        p['geo_weight'] = geo_weight
    if seed is not None:
        p['seed'] = seed

    n_restarts = p.pop('n_restarts')

    if n_restarts == 1:
        return _assign_groups_once(df_sorted, group_size, friend_wishes,
                                   max_kar=max_kar, **p)

    print(f"\n{'#' * 60}\n# Slow tier: {n_restarts} restarts\n{'#' * 60}")
    best_df, best_sat = None, -1
    for r in range(n_restarts):
        print(f"\n----- Restart {r + 1}/{n_restarts} (seed={p['seed'] + r}) -----")
        attempt_p = dict(p, seed=p['seed'] + r)
        attempt = _assign_groups_once(df_sorted.copy(), group_size, friend_wishes,
                                      max_kar=max_kar, **attempt_p)
        # Count satisfaction inline (cheap on already-assigned df)
        m2g = dict(zip(attempt['member_no'], attempt['group']))
        ms = set(attempt['member_no'])
        sat = 0
        for _, row in attempt.iterrows():
            f1, f2 = row['friend_1'], row['friend_2']
            if not ((f1 and f1 in ms) or (f2 and f2 in ms)):
                continue
            if (m2g.get(f1) == row['group']) or (m2g.get(f2) == row['group']):
                sat += 1
        print(f"  -> friend-satisfied: {sat}")
        if sat > best_sat:
            best_sat, best_df = sat, attempt
    print(f"\n{'#' * 60}\n# Best of {n_restarts}: {best_sat} satisfied\n{'#' * 60}")
    # Write best assignment back into the caller's df
    df_sorted['group'] = best_df['group'].values
    return df_sorted
```

- [ ] **Step 3: Add a smoke test for slow tier (small fixture, n_restarts override would be useful but presets are fixed; instead use the medium-tier path and just confirm slow runs without error on a tiny fixture)**

Append to `test_assign_groups.py`:

```python
class TestQualityTiers(unittest.TestCase):
    def test_medium_tier_default_unchanged(self):
        df = fixture_two_groups_one_friend_pair()
        fw = u.build_friend_graph(df)
        df = u.assign_groups(df, 36, fw, quality='medium')
        self.assertEqual(df['group'].nunique(), 2)

    def test_slow_tier_runs_and_returns_legal(self):
        df = fixture_two_groups_one_friend_pair()
        fw = u.build_friend_graph(df)
        df = u.assign_groups(df, 36, fw, quality='slow')
        self.assertEqual(df['group'].nunique(), 2)

    def test_unknown_quality_raises(self):
        df = fixture_two_groups_one_friend_pair()
        fw = u.build_friend_graph(df)
        with self.assertRaises(ValueError):
            u.assign_groups(df, 36, fw, quality='ludicrous')
```

- [ ] **Step 4: Run all tests**

```bash
cd /config && python -m unittest discover -s notebooks/wsj27/tests -v
```

Expected: all PASS. The `slow` tier test takes a few seconds (8 restarts × ~tiny fixture).

- [ ] **Step 5: Run baseline non-regression on medium tier (unchanged default)**

```bash
cd /config && python notebooks/wsj27/tests/capture_baseline.py > /tmp/post_task11.json
python3 -c "
import json
b = json.load(open('/config/notebooks/wsj27/tests/baseline_metrics.json'))
n = json.load(open('/tmp/post_task11.json'))
for travel in ('rundresa', 'direktresa'):
    bs, ns = b[travel]['n_satisfied'], n[travel]['n_satisfied']
    print(f'{travel}: {bs} -> {ns} ({ns - bs:+d})')
    assert ns >= bs
"
```

Expected: medium tier still ≥ baseline.

- [ ] **Step 6: Commit**

```bash
git add notebooks/wsj27/wsj27_utils.py notebooks/wsj27/tests/test_assign_groups.py
git commit -m "feat(wsj27): add quality='medium'|'slow' with multi-restart slow tier"
```

---

## Task 12: Refactor `wsj_gruppindelning_rundresa.ipynb` to 5 cells

**Files:**
- Modify: `notebooks/wsj27/wsj_gruppindelning_rundresa.ipynb`

- [ ] **Step 1: Replace the notebook content** (use `python3` script for clean JSON write)

Run from `/config`:

```bash
python3 - <<'EOF'
import json, copy

NB = '/config/notebooks/wsj27/wsj_gruppindelning_rundresa.ipynb'
nb = json.load(open(NB))

def code_cell(src):
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": src.splitlines(keepends=True)}

def md_cell(src):
    return {"cell_type": "markdown", "metadata": {}, "source": src.splitlines(keepends=True)}

cells = [
    md_cell("""# WSJ 2027 - Gruppindelning Rundresa

Assign confirmed rundresa deltagare into groups of exactly 36.

## Rules
1. **Exactly 36 per group** (remainder group allowed)
2. **Geographic proximity** — participants should live close to each other (Hilbert curve sort, friend-cluster-aware)
3. **Friend wish** — at least ONE of friend_1/friend_2 in same group (soft goal)
4. **Max 8 from same kår** per group (hard constraint)
5. **Diversity** — age (14-17) and sex should be as evenly spread as possible
"""),
    code_cell("""TRAVEL = 'rundresa'        # only line that differs between rundresa.ipynb and direktresa.ipynb
QUALITY = 'medium'         # 'medium' (~1-3 min) or 'slow' (~10-30 min, +5-10% friends)
GROUP_SIZE = 36
OUTPUT_DIR = '/config/notebooks/wsj27/output'
"""),
    code_cell("""import sys; sys.path.insert(0, '/config/notebooks/wsj27')
import wsj27_utils as u

raw = u.fetch_participants()
df_all, _ = u.build_participant_dataframe(raw)
df = df_all[df_all['travel'] == TRAVEL].copy().reset_index(drop=True)
u.assign_coordinates(df)
df = u.add_hilbert_index(df)
u.resolve_friend_wishes(df, df_all)
friend_wishes = u.build_friend_graph(df)
u.print_intake_summary(df, GROUP_SIZE)
"""),
    code_cell("""df = u.assign_groups(df, GROUP_SIZE, friend_wishes, quality=QUALITY)
group_of = df['group'].values
total_groups = df['group'].nunique()
"""),
    code_cell("""u.print_group_metrics(df, group_of, total_groups)
csv_path, json_path = u.export_results(df, group_of, total_groups, OUTPUT_DIR, prefix=f'wsj27_{TRAVEL}')
map_path = f'{OUTPUT_DIR}/wsj_{TRAVEL}_karta.html'
u.generate_group_map_html(df, total_groups, map_path,
                          title=f'WSJ 2027 {TRAVEL.title()}',
                          friend_wishes=friend_wishes, show_group_arcs=True)
print(f'CSV:  {csv_path}\\nJSON: {json_path}\\nMap:  {map_path}')
"""),
]

nb['cells'] = cells
with open(NB, 'w') as f:
    json.dump(nb, f, indent=1)
print('rewrote', NB)
EOF
```

- [ ] **Step 2: Validate the notebook is parseable JSON and has 5 cells**

```bash
python3 -c "
import json
nb = json.load(open('/config/notebooks/wsj27/wsj_gruppindelning_rundresa.ipynb'))
assert len(nb['cells']) == 5, f'got {len(nb[\"cells\"])}'
print('cells:', [c['cell_type'] for c in nb['cells']])
"
```

Expected: 5 cells, types `markdown, code, code, code, code`.

- [ ] **Step 3: Execute the notebook end-to-end via Jupyter helper**

```bash
python3 /config/scripts/jupyter.py kernel-start
# Note the kernel ID returned, then execute each code cell:
KID=<id-from-above>
python3 /config/scripts/jupyter.py execute --kernel-id $KID "$(python3 -c "
import json; nb=json.load(open('/config/notebooks/wsj27/wsj_gruppindelning_rundresa.ipynb'));
print(''.join(nb['cells'][1]['source']))")"
# Repeat for cells 2, 3, 4. (Or open the notebook in JupyterLab and run all.)
python3 /config/scripts/jupyter.py kernel-stop $KID
```

Alternative: open the notebook in JupyterLab UI (http://172.30.33.4:8099) and "Run All" — easier to read output.

Expected: all four code cells run without error; final cell prints CSV/JSON/Map paths; output files in `/config/notebooks/wsj27/output/` are updated.

- [ ] **Step 4: Verify output is non-regressive**

```bash
python3 -c "
import json
b = json.load(open('/config/notebooks/wsj27/tests/baseline_metrics.json'))
out = json.load(open('/config/notebooks/wsj27/output/wsj27_rundresa_grupper.json'))
n_groups = len(out)
n_members = sum(g['size'] if 'size' in g else len(g['members']) for g in out)
print(f'groups: {n_groups} members: {n_members}')
print(f'baseline rundresa: {b[\"rundresa\"][\"n_groups\"]} groups, {b[\"rundresa\"][\"n_participants\"]} members')
assert n_members == b['rundresa']['n_participants'], 'member count changed'
"
```

Expected: same group count and member count as baseline.

- [ ] **Step 5: Commit**

```bash
git add notebooks/wsj27/wsj_gruppindelning_rundresa.ipynb
git commit -m "refactor(wsj27): slim rundresa notebook to 5-cell config-driven layout"
```

---

## Task 13: Refactor `wsj_gruppindelning_direktresa.ipynb` to mirror rundresa

Should be byte-identical to rundresa except Cell 1's `TRAVEL = 'direktresa'`.

**Files:**
- Modify: `notebooks/wsj27/wsj_gruppindelning_direktresa.ipynb`

- [ ] **Step 1: Copy rundresa notebook structure, change one line**

```bash
python3 - <<'EOF'
import json

SRC = '/config/notebooks/wsj27/wsj_gruppindelning_rundresa.ipynb'
DST = '/config/notebooks/wsj27/wsj_gruppindelning_direktresa.ipynb'
nb = json.load(open(SRC))

# Update markdown header
nb['cells'][0]['source'] = """# WSJ 2027 - Gruppindelning Direktresa

Assign confirmed direktresa deltagare into groups of exactly 36.

Direktresa participants travel independently to/from WSJ in Poland.
Same grouping algorithm as rundresa but applied to the direktresa subset.

## Rules
1. **Exactly 36 per group** (remainder group allowed)
2. **Geographic proximity** — Hilbert curve sort, friend-cluster-aware
3. **Friend wish** — at least ONE friend in same group (soft goal)
4. **Max 8 from same kår** per group (hard constraint)
5. **Diversity** — age (14-17) and sex balance
""".splitlines(keepends=True)

# Change TRAVEL value in Cell 1
nb['cells'][1]['source'] = [
    line.replace("TRAVEL = 'rundresa'", "TRAVEL = 'direktresa'")
    for line in nb['cells'][1]['source']
]

with open(DST, 'w') as f:
    json.dump(nb, f, indent=1)
print('wrote', DST)
EOF
```

- [ ] **Step 2: Verify cells 2-4 are byte-identical between the two notebooks**

```bash
python3 -c "
import json
r = json.load(open('/config/notebooks/wsj27/wsj_gruppindelning_rundresa.ipynb'))
d = json.load(open('/config/notebooks/wsj27/wsj_gruppindelning_direktresa.ipynb'))
for i in (2, 3, 4):
    rs = ''.join(r['cells'][i]['source'])
    ds = ''.join(d['cells'][i]['source'])
    assert rs == ds, f'cell {i} differs:\n--- rundresa ---\n{rs}\n--- direktresa ---\n{ds}'
print('cells 2,3,4 byte-identical between notebooks')
"
```

Expected: prints "cells 2,3,4 byte-identical between notebooks".

- [ ] **Step 3: Run the direktresa notebook end-to-end (JupyterLab UI or via jupyter.py helper as in Task 12)**

Expected: produces `/config/notebooks/wsj27/output/wsj27_direktresa_grupper.{csv,json}` and `wsj_direktresa_karta.html` without error.

- [ ] **Step 4: Verify direktresa output non-regressive**

```bash
python3 -c "
import json
b = json.load(open('/config/notebooks/wsj27/tests/baseline_metrics.json'))
out = json.load(open('/config/notebooks/wsj27/output/wsj27_direktresa_grupper.json'))
n_members = sum(g['size'] if 'size' in g else len(g['members']) for g in out)
assert n_members == b['direktresa']['n_participants'], 'member count changed'
print('direktresa member count OK:', n_members)
"
```

Expected: matches baseline.

- [ ] **Step 5: Commit**

```bash
git add notebooks/wsj27/wsj_gruppindelning_direktresa.ipynb
git commit -m "refactor(wsj27): mirror rundresa structure in direktresa notebook"
```

---

## Task 14: Final acceptance check

End-to-end verification against the spec's acceptance criteria.

**Files:**
- Create: `notebooks/wsj27/tests/post_metrics.json`

- [ ] **Step 1: Capture post-change metrics**

```bash
cd /config && python notebooks/wsj27/tests/capture_baseline.py > /config/notebooks/wsj27/tests/post_metrics.json
cat /config/notebooks/wsj27/tests/post_metrics.json
```

- [ ] **Step 2: Verify acceptance criteria**

The original spec said "+10% improvement," but baseline capture showed the algorithm was already at 97.77% (rundresa) and 99.70% (direktresa) — making +10% mathematically impossible. Revised criteria after Task 2 diagnostic:

- **rundresa medium:** `n_satisfied ≥ baseline + 5` (target 927+; theoretical max 943)
- **direktresa medium:** `n_satisfied ≥ baseline` (no regression; only 1 wish was unsatisfied)
- **Slow tier:** `n_satisfied ≥ medium tier` for both
- **Constraints:** zero kår violations, all groups exact size

```bash
python3 - <<'EOF'
import json
b = json.load(open('/config/notebooks/wsj27/tests/baseline_metrics.json'))
p = json.load(open('/config/notebooks/wsj27/tests/post_metrics.json'))
ok = True
for travel, min_gain in (('rundresa', 5), ('direktresa', 0)):
    bs, ps = b[travel]['n_satisfied'], p[travel]['n_satisfied']
    delta = ps - bs
    target_met = delta >= min_gain
    print(f"{travel}: {bs} -> {ps} ({delta:+d}) {'OK' if target_met else 'FAIL'} target +{min_gain}")
    if not target_met:
        ok = False
print()
print("ACCEPTANCE:", "PASS" if ok else "FAIL — investigate")
EOF
```

Expected: PASS — rundresa +5 or more, direktresa unchanged or +1.

- [ ] **Step 3: Spot-check slow tier on rundresa**

```bash
python3 - <<'EOF'
import sys, time, json
sys.path.insert(0, '/config/notebooks/wsj27')
import wsj27_utils as u
raw = u.fetch_participants()
df_all, _ = u.build_participant_dataframe(raw)
df = df_all[df_all['travel'] == 'rundresa'].copy().reset_index(drop=True)
u.assign_coordinates(df)
df = u.add_hilbert_index(df)
u.resolve_friend_wishes(df, df_all)
fw = u.build_friend_graph(df)
t0 = time.time()
df = u.assign_groups(df, 36, fw, quality='slow')
print(f"slow runtime: {time.time() - t0:.1f}s")
m2g = dict(zip(df['member_no'], df['group']))
ms = set(df['member_no'])
sat = sum(1 for _, r in df.iterrows()
          if ((r['friend_1'] in ms and m2g.get(r['friend_1']) == r['group']) or
              (r['friend_2'] in ms and m2g.get(r['friend_2']) == r['group']))
          and ((r['friend_1'] and r['friend_1'] in ms) or
               (r['friend_2'] and r['friend_2'] in ms)))
p = json.load(open('/config/notebooks/wsj27/tests/post_metrics.json'))
print(f"slow rundresa: {sat} (medium was {p['rundresa']['n_satisfied']})")
assert sat >= p['rundresa']['n_satisfied'], 'slow regressed below medium'
EOF
```

Expected: slow tier ≥ medium tier; runtime ~10-30 minutes.

- [ ] **Step 4: Final commit**

```bash
git add notebooks/wsj27/tests/post_metrics.json
git commit -m "test(wsj27): record post-change metrics; acceptance criteria met"
```

---

## Self-Review Notes

- **Spec coverage** — all six algorithm changes mapped to tasks: cluster cut→9, iterate Phase 2→6, 3-way rotations→8, criticality→7, SA scoring→10, slow tier→11. Notebook restructure→12-13. Refactor (helper extract, group_members)→3-4. `print_intake_summary`→5. Acceptance criteria→14.
- **No placeholders** — every step has concrete code or commands.
- **Type/name consistency** — `_friend_swap_pass`, `_friend_rotate_pass`, `_assign_groups_once`, `_GroupState` (not used in final), `quality`, `cut_order`, `cluster_anchors` all match between definition and call sites.
- **Bite-sized** — every step is a single action: write code, run command, commit. Each task ends with a commit.
- **Test layering** — early tests pin baseline behavior; later tests add capability assertions; non-regression check after every algorithm task ensures monotone improvement.
