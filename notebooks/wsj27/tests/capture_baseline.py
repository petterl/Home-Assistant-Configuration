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
        return bool((f1 and f1 in member_set) or (f2 and f2 in member_set))

    def satisfied(row):
        g = row['group']
        f1, f2 = row['friend_1'], row['friend_2']
        return bool((f1 in member_set and member_to_group.get(f1) == g)
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
