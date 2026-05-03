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
