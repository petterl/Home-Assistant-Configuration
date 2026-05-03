"""Measure friend-satisfaction metrics for rundresa and direktresa.

Default: prints clean JSON to stdout (verbose progress redirected to stderr).
With `--save-baseline`: also overwrites /config/notebooks/wsj27/tests/baseline_metrics.json.
The saved JSON is the immutable comparison target — only re-save when you intend
to re-baseline."""

import sys, json, time, io
from contextlib import redirect_stdout
sys.path.insert(0, '/config/notebooks/wsj27')
import wsj27_utils as u


def measure(travel):
    # Suppress wsj27_utils' verbose prints; route them to stderr instead.
    buf = io.StringIO()
    with redirect_stdout(buf):
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
    sys.stderr.write(buf.getvalue())

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
    if '--save-baseline' in sys.argv:
        path = '/config/notebooks/wsj27/tests/baseline_metrics.json'
        with open(path, 'w') as f:
            json.dump(out, f, indent=2)
        sys.stderr.write(f"\nWrote baseline to {path}\n")
    print(json.dumps(out, indent=2))
