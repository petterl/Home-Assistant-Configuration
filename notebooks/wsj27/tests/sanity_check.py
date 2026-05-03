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
