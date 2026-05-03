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
