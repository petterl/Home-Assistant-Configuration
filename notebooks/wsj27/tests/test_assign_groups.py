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


class TestThreeWayRotation(unittest.TestCase):
    """Smoke test: rotations don't break things; mutual wishes get satisfied."""

    def test_mutual_wish_pair_in_same_group(self):
        df = fixture_three_way_rotation_unblocks()
        fw = u.build_friend_graph(df)
        df = u.assign_groups(df, 36, fw)
        m2g = dict(zip(df['member_no'], df['group']))
        # The fixture has person 1 wanting person 50 (and vice versa via mutual).
        # After all phases, they should be in the same group.
        self.assertEqual(m2g['1'], m2g['50'],
                         msg='persons 1 and 50 should be co-located after assign_groups')


if __name__ == '__main__':
    unittest.main()
