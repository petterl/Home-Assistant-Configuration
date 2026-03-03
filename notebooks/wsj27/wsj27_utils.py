"""
WSJ 2027 - Shared utilities for group assignment notebooks.

Reusable code extracted from wsj_gruppindelning.ipynb.
Used by: rundresa, direktresa, and ledare notebooks.
"""

import requests
import json
import re
import math
import random
import os
import numpy as np
import pandas as pd
from collections import defaultdict, Counter
from datetime import date
from difflib import SequenceMatcher

# =============================================================================
# Constants
# =============================================================================

# Fee categories
DELTAGARE_RUNDRESA = '25694'
DELTAGARE_DIREKTRESA = '27561'
DELTAGARE_FEES = {DELTAGARE_RUNDRESA, DELTAGARE_DIREKTRESA}
IST_RUNDRESA = '25696'
IST_EGEN_RESA = '25702'
IST_FEES = {IST_RUNDRESA, IST_EGEN_RESA}
CMT_FEES = {'25697', '25693'}

WSJ_START = date(2027, 7, 29)
SCOUTNET_URL = "https://www.scoutnet.se/api/project/get/participants"

# Question IDs (from Scoutnet form 39188) for friend wishes
Q_FRIEND_1_MEMBER_NO = '87660'
Q_FRIEND_1_NAME = '87662'
Q_FRIEND_2_MEMBER_NO = '87663'
Q_FRIEND_2_NAME = '87665'

# Sex label map
SEX_MAP = {
    0: 'Okänt', 1: 'Man', 2: 'Kvinna', 3: 'Annat', 4: 'Icke-binär',
    '0': 'Okänt', '1': 'Man', '2': 'Kvinna', '3': 'Annat', '4': 'Icke-binär',
}

# Hilbert curve parameters
HILBERT_N = 256
LAT_RANGE = (55.0, 70.0)
LNG_RANGE = (10.0, 25.0)

# Sweden centroid for participants without coordinates
SWEDEN_LAT, SWEDEN_LNG = 62.0, 15.0

# 21 distinct colors for groups
GROUP_COLORS = [
    [31, 120, 180], [255, 127, 0], [51, 160, 44], [227, 26, 28],
    [166, 206, 227], [253, 191, 111], [178, 223, 138], [251, 154, 153],
    [202, 178, 214], [255, 255, 153], [106, 61, 154], [177, 89, 40],
    [141, 211, 199], [255, 255, 179], [190, 186, 218], [251, 128, 114],
    [128, 177, 211], [253, 180, 98], [179, 222, 105], [252, 205, 229],
    [217, 217, 217],
]

# Mapbox token for KeplerGL maps (loaded from scoutnet_secrets.py)
try:
    from scoutnet_secrets import MAPBOX_TOKEN
except ImportError:
    MAPBOX_TOKEN = os.environ.get("MAPBOX_TOKEN", "")


# =============================================================================
# 1. API and Data Loading
# =============================================================================

def fetch_participants():
    """Fetch all participants from Scoutnet API. Returns raw API response dict."""
    from scoutnet_secrets import SCOUTNET_API_ID, SCOUTNET_API_KEY
    response = requests.get(SCOUTNET_URL, auth=(SCOUTNET_API_ID, SCOUTNET_API_KEY))
    response.raise_for_status()
    raw_data = response.json()
    participants_raw = raw_data.get('participants', {})

    cancelled = sum(1 for p in participants_raw.values() if p.get('cancelled'))
    confirmed = sum(1 for p in participants_raw.values()
                    if p.get('confirmed') and not p.get('cancelled'))
    unconfirmed = sum(1 for p in participants_raw.values()
                      if not p.get('confirmed') and not p.get('cancelled'))

    print(f"Fetched {len(participants_raw)} participants")
    print(f"Confirmed: {confirmed}, Unconfirmed: {unconfirmed}, Cancelled: {cancelled}")

    return raw_data


def build_participant_dataframe(raw_data):
    """Build DataFrame from API response with age validation.

    Returns (df, skipped_list) where df has columns:
    member_no, name, birth_date, age, sex, fee_id, category, travel, kar, district, region,
    friend_1, friend_2, friend_1_name, friend_2_name, group
    """
    participants_raw = raw_data.get('participants', {})

    def exact_age(birth_date, ref_date):
        """Calculate exact age in whole years at ref_date."""
        years = ref_date.year - birth_date.year
        if (ref_date.month, ref_date.day) < (birth_date.month, birth_date.day):
            years -= 1
        return years

    def get_question(questions, qid):
        """Safely get a question answer, handling list/dict."""
        if not isinstance(questions, dict):
            return ''
        val = questions.get(qid, '')
        if val is None:
            return ''
        return str(val).strip()

    rows = []
    skipped = []
    skipped_unconfirmed = 0

    for mid, p in participants_raw.items():
        if p.get('cancelled'):
            continue

        # Skip unconfirmed registrations
        if not p.get('confirmed'):
            skipped_unconfirmed += 1
            continue

        fee_id = str(p.get('fee_id', ''))
        dob = p.get('date_of_birth', '')
        name = f"{p.get('first_name', '')} {p.get('last_name', '')}"

        birth = None
        if dob:
            try:
                birth = date.fromisoformat(dob)
            except ValueError:
                pass

        # Age validation
        if birth is None:
            skipped.append(f"  NO DOB: {name} fee={fee_id}")
            continue

        age = exact_age(birth, WSJ_START)

        if fee_id in DELTAGARE_FEES and (age < 14 or age >= 18):
            skipped.append(f"  DELTAGARE wrong age: {name} born {dob} (age {age})")
            continue
        if fee_id in IST_FEES and age < 18:
            skipped.append(f"  IST too young: {name} born {dob} (age {age})")
            continue

        # Determine category
        if fee_id in CMT_FEES:
            category = 'cmt'
        elif fee_id in DELTAGARE_FEES:
            category = 'deltagare'
        elif fee_id in IST_FEES:
            category = 'ist'
        else:
            category = 'deltagare' if 14 <= age <= 17 else 'ist'

        # Extract kar info
        membership = p.get('primary_membership_info', {})
        if isinstance(membership, dict):
            kar = membership.get('group_name', '')
            district = membership.get('district_name', '')
            region = membership.get('region_name', '')
        else:
            kar, district, region = '', '', ''

        # Extract friend wishes from questions
        questions = p.get('questions', {})
        friend_1 = get_question(questions, Q_FRIEND_1_MEMBER_NO)
        friend_2 = get_question(questions, Q_FRIEND_2_MEMBER_NO)
        friend_1_name = get_question(questions, Q_FRIEND_1_NAME)
        friend_2_name = get_question(questions, Q_FRIEND_2_NAME)

        # Clean friend member numbers (ignore '0' and empty)
        friend_1 = friend_1 if friend_1 and friend_1 != '0' else ''
        friend_2 = friend_2 if friend_2 and friend_2 != '0' else ''

        rows.append({
            'member_no': str(p.get('member_no', mid)),
            'name': name,
            'birth_date': dob,
            'age': age,
            'sex': p.get('sex', 0),
            'fee_id': fee_id,
            'category': category,
            'travel': ('rundresa' if fee_id in (DELTAGARE_RUNDRESA, IST_RUNDRESA)
                       else ('direktresa' if fee_id == DELTAGARE_DIREKTRESA
                             else ('egen_resa' if fee_id == IST_EGEN_RESA
                                   else 'other'))),
            'kar': kar,
            'district': district,
            'region': region,
            'friend_1': friend_1,
            'friend_2': friend_2,
            'friend_1_name': friend_1_name,
            'friend_2_name': friend_2_name,
            'group': None,  # To be assigned
        })

    df = pd.DataFrame(rows)

    print(f"Total confirmed participants: {len(df)}")
    print(f"Skipped: {skipped_unconfirmed} unconfirmed, {len(skipped)} wrong age/no DOB")
    print(f"\nBy category:")
    print(df['category'].value_counts().to_string())
    print(f"\nBy travel type:")
    print(df['travel'].value_counts().to_string())
    print(f"\nFriend wishes:")
    print(f"  With friend 1 member no: {(df['friend_1'] != '').sum()}")
    print(f"  With friend 2 member no: {(df['friend_2'] != '').sum()}")
    print(f"  With friend 1 name (text): {(df['friend_1_name'] != '').sum()}")
    print(f"  With friend 2 name (text): {(df['friend_2_name'] != '').sum()}")

    if skipped:
        print(f"\nSkipped participants:")
        for s in skipped:
            print(s)

    return df, skipped


# =============================================================================
# 3. Geocoding
# =============================================================================

def assign_coordinates(df, geocode_cache_path='/config/notebooks/wsj27/scoutkar_geocode_cache.json'):
    """Add lat/lng columns to df from geocode cache. Fills missing with Sweden centroid.

    Modifies df in-place and returns it.
    """
    with open(geocode_cache_path, 'r', encoding='utf-8') as f:
        geocode_cache = json.load(f)

    def get_coords(kar_name):
        geo = geocode_cache.get(kar_name, {})
        return geo.get('lat'), geo.get('lng')

    df['lat'] = df['kar'].apply(lambda k: get_coords(k)[0])
    df['lng'] = df['kar'].apply(lambda k: get_coords(k)[1])

    no_coords = df['lat'].isna().sum()
    df['lat'] = df['lat'].fillna(SWEDEN_LAT)
    df['lng'] = df['lng'].fillna(SWEDEN_LNG)

    print(f"With coordinates: {len(df) - no_coords}")
    print(f"Without coordinates (Sweden centroid): {no_coords}")

    return df


def geocode_places(df, place_column='Bostadsort',
                   cache_path='/config/notebooks/wsj27/ledare_geocode_cache.json'):
    """Geocode place names to lat/lng using geopy with file cache.

    Adds lat/lng columns to df. Uses Nominatim with Sweden bias.
    Caches results to avoid repeated API calls.

    Modifies df in-place and returns it.
    """
    import time

    # Load or create cache
    if os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache = json.load(f)
    else:
        cache = {}

    # Clean place names: extract the main city
    def clean_place(raw):
        if not isinstance(raw, str) or not raw.strip():
            return None
        place = raw.strip()
        # Handle "X just nu men planerad flytt till Y" -> Y
        if 'flytt till' in place.lower():
            place = place.split('flytt till')[-1].strip()
        # Handle "X och Y" -> X
        if ' och ' in place:
            place = place.split(' och ')[0].strip()
        # Handle "X / Y" -> X
        if ' / ' in place:
            place = place.split(' / ')[0].strip()
        return place

    unique_places = set()
    for raw in df[place_column].dropna().unique():
        cleaned = clean_place(raw)
        if cleaned:
            unique_places.add(cleaned)

    # Geocode uncached places
    uncached = [p for p in unique_places if p not in cache]
    if uncached:
        from geopy.geocoders import Nominatim
        geo = Nominatim(user_agent='wsj27-ledare-geocoder')
        print(f"Geocoding {len(uncached)} new places...")
        for place in sorted(uncached):
            try:
                loc = geo.geocode(f"{place}, Sweden", timeout=10)
                if loc:
                    cache[place] = {'lat': loc.latitude, 'lng': loc.longitude,
                                    'display': loc.address}
                    print(f"  {place} -> {loc.latitude:.4f}, {loc.longitude:.4f}")
                else:
                    cache[place] = {'lat': None, 'lng': None, 'display': None}
                    print(f"  {place} -> NOT FOUND")
                time.sleep(1.1)  # Nominatim rate limit
            except Exception as e:
                cache[place] = {'lat': None, 'lng': None, 'display': None}
                print(f"  {place} -> ERROR: {e}")

        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print(f"Saved cache to {cache_path}")

    # Assign coordinates
    def get_coords(raw):
        cleaned = clean_place(raw)
        if cleaned and cleaned in cache:
            return cache[cleaned].get('lat'), cache[cleaned].get('lng')
        return None, None

    df['lat'] = df[place_column].apply(lambda p: get_coords(p)[0])
    df['lng'] = df[place_column].apply(lambda p: get_coords(p)[1])

    no_coords = df['lat'].isna().sum()
    df['lat'] = df['lat'].fillna(SWEDEN_LAT)
    df['lng'] = df['lng'].fillna(SWEDEN_LNG)

    print(f"With coordinates: {len(df) - no_coords}")
    print(f"Without coordinates (Sweden centroid): {no_coords}")

    return df


# =============================================================================
# 4. Hilbert Curve
# =============================================================================

def hilbert_xy2d(n, x, y):
    """Convert (x,y) to Hilbert curve distance in n x n grid."""
    d = 0
    s = n // 2
    while s > 0:
        rx = 1 if (x & s) > 0 else 0
        ry = 1 if (y & s) > 0 else 0
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x
        s //= 2
    return d


def geo_to_hilbert(lat, lng):
    """Convert lat/lng to Hilbert curve index."""
    x = int((lat - LAT_RANGE[0]) / (LAT_RANGE[1] - LAT_RANGE[0]) * (HILBERT_N - 1))
    y = int((lng - LNG_RANGE[0]) / (LNG_RANGE[1] - LNG_RANGE[0]) * (HILBERT_N - 1))
    x = max(0, min(HILBERT_N - 1, x))
    y = max(0, min(HILBERT_N - 1, y))
    return hilbert_xy2d(HILBERT_N, x, y)


def add_hilbert_index(df):
    """Add 'hilbert' column and return df sorted by it."""
    df['hilbert'] = df.apply(lambda r: geo_to_hilbert(r['lat'], r['lng']), axis=1)
    return df.sort_values('hilbert').reset_index(drop=True)


# =============================================================================
# 5. Friend Matching
# =============================================================================

def normalize_name(name):
    """Normalize a name for matching: lowercase, collapse whitespace."""
    return re.sub(r'\s+', ' ', name.strip().lower())


def parse_friend_text(text):
    """Parse free-text friend wish into (name_part, kar_hint)."""
    text = text.strip()
    # Skip generic wishes (not a specific person)
    skip_patterns = ['gärna någon', 'övriga deltagare', 'scouter från']
    if any(p in text.lower() for p in skip_patterns):
        return None, text

    kar_hint = ''
    name_part = text

    if ',' in text:
        parts = [p.strip() for p in text.split(',')]
        name_part = parts[0]
        kar_hint = ' '.join(parts[1:])
    elif ' - ' in text:
        parts = [p.strip() for p in text.split(' - ', 1)]
        name_part = parts[0]
        kar_hint = parts[1]
    else:
        kar_starters = ['scoutkår', 'sjöscoutkår', 'scouterkår', 'scoutskår',
                        'equmenia', 'kåren', 'scoutkåren']
        text_lower = text.lower()
        for kw in kar_starters:
            idx = text_lower.find(kw)
            if idx > 0:
                before = text[:idx].rstrip()
                bwords = before.split()
                if len(bwords) > 2:
                    name_part = ' '.join(bwords[:2])
                    kar_hint = ' '.join(bwords[2:]) + ' ' + text[idx:]
                    kar_hint = kar_hint.strip()
                break
        else:
            words = text.split()
            if len(words) > 3:
                name_part = ' '.join(words[:2])
                kar_hint = ' '.join(words[2:])

    return name_part.strip(), kar_hint.strip()


def fuzzy_match_name(query_name, name_lookup, kar_hint='', threshold=0.75):
    """Find best matching participant by name with optional kar boost."""
    query_norm = normalize_name(query_name)

    # 1. Exact match
    if query_norm in name_lookup:
        matches = name_lookup[query_norm]
        if len(matches) == 1:
            return matches[0], 'exact', 1.0
        if kar_hint:
            kar_lower = kar_hint.lower()
            for m in matches:
                if kar_lower in m['kar'].lower() or m['kar'].lower() in kar_lower:
                    return m, 'exact+kar', 1.0
        return matches[0], 'exact(ambiguous)', 1.0

    # 2. Try first + last word
    query_words = query_norm.split()
    if len(query_words) >= 2:
        short_query = query_words[0] + ' ' + query_words[-1]
        if short_query in name_lookup:
            matches = name_lookup[short_query]
            if len(matches) == 1:
                return matches[0], 'first+last', 0.95

    # 3. Fuzzy matching
    best_score = 0
    best_match = None
    for norm_name, candidates in name_lookup.items():
        score = SequenceMatcher(None, query_norm, norm_name).ratio()
        cand_words = norm_name.split()
        if len(cand_words) >= 2:
            short_cand = cand_words[0] + ' ' + cand_words[-1]
            score = max(score, SequenceMatcher(None, query_norm, short_cand).ratio())
        if len(query_words) >= 2:
            short_q = query_words[0] + ' ' + query_words[-1]
            score = max(score, SequenceMatcher(None, short_q, norm_name).ratio())
        if score > best_score:
            best_score = score
            best_match = candidates[0]

    if best_score >= threshold and best_match:
        method = f'fuzzy({best_score:.2f})'
        if kar_hint:
            kar_lower = kar_hint.lower()
            if kar_lower in best_match['kar'].lower() or best_match['kar'].lower() in kar_lower:
                method += '+kar'
                best_score = min(best_score + 0.1, 1.0)
        return best_match, method, best_score

    return None, 'no_match', best_score


def resolve_friend_wishes(df_target, df_all):
    """Resolve text-only friend wishes via fuzzy name matching.

    df_target: the subset being grouped (e.g. rundresa only)
    df_all: all participants (for matching against)
    Returns updated df_target with friend member numbers populated.
    """
    # Build name lookup from ALL participants
    name_lookup = defaultdict(list)
    for _, row in df_all.iterrows():
        norm = normalize_name(row['name'])
        name_lookup[norm].append({
            'member_no': row['member_no'], 'name': row['name'],
            'kar': row['kar'], 'travel': row['travel'],
        })

    # Collect text-only wishes
    text_wishes = []
    for _, row in df_target.iterrows():
        if not row['friend_1'] and row['friend_1_name']:
            text_wishes.append({
                'wisher_member_no': row['member_no'], 'wisher': row['name'],
                'friend_text': row['friend_1_name'], 'slot': 'friend_1',
            })
        if not row['friend_2'] and row['friend_2_name']:
            text_wishes.append({
                'wisher_member_no': row['member_no'], 'wisher': row['name'],
                'friend_text': row['friend_2_name'], 'slot': 'friend_2',
            })

    # Match and validate
    verified = []
    unresolved = []
    skipped_generic = []

    for tw in text_wishes:
        name_part, kar_hint = parse_friend_text(tw['friend_text'])
        if name_part is None:
            skipped_generic.append(tw)
            continue

        match, method, score = fuzzy_match_name(name_part, name_lookup, kar_hint)

        if match:
            # Validate: first or last name must match
            parsed_words = normalize_name(name_part).split()
            match_words = normalize_name(match['name']).split()
            if score < 0.90:
                p_first = parsed_words[0]
                p_last = parsed_words[-1] if len(parsed_words) > 1 else ''
                m_first = match_words[0]
                m_last = match_words[-1] if len(match_words) > 1 else ''
                if p_first != m_first and p_last != m_last:
                    unresolved.append({**tw, 'reason': f'name mismatch ({match["name"]})'})
                    continue
            verified.append({**tw, 'match': match, 'method': method, 'score': score})
        else:
            unresolved.append({**tw, 'reason': 'no match found'})

    # Apply matches to DataFrame
    updates = 0
    for v in verified:
        idx = df_target[df_target['member_no'] == v['wisher_member_no']].index
        if len(idx) > 0 and df_target.at[idx[0], v['slot']] == '':
            df_target.at[idx[0], v['slot']] = v['match']['member_no']
            # Also update main df
            main_idx = df_all[df_all['member_no'] == v['wisher_member_no']].index
            if len(main_idx) > 0:
                df_all.at[main_idx[0], v['slot']] = v['match']['member_no']
            updates += 1

    print(f"=== Text Friend Name Matching ===")
    print(f"Text-only wishes: {len(text_wishes)}")
    print(f"Matched & applied: {len(verified)}")
    print(f"Generic wishes (not a person): {len(skipped_generic)}")
    print(f"Unresolved (friend not in project): {len(unresolved)}")

    print(f"\nMatched:")
    for v in sorted(verified, key=lambda x: x['wisher']):
        m = v['match']
        print(f"  {v['wisher']} -> {m['name']} ({m['kar']}) [{m['travel']}] via {v['method']}")

    if unresolved:
        print(f"\nUnresolved:")
        for u in sorted(unresolved, key=lambda x: x['wisher']):
            print(f"  {u['wisher']} -> \"{u['friend_text']}\" ({u['reason']})")

    if skipped_generic:
        print(f"\nGeneric wishes (skipped):")
        for s in skipped_generic:
            print(f"  {s['wisher']} -> \"{s['friend_text']}\"")

    return df_target


def build_friend_graph(df_target):
    """Build friend_wishes dict and print summary.

    Returns friend_wishes: {member_no: [list of friend member_nos in target]}
    """
    member_set = set(df_target['member_no'].values)

    friend_wishes = {}
    for _, row in df_target.iterrows():
        wishes = []
        if row['friend_1'] and row['friend_1'] in member_set:
            wishes.append(row['friend_1'])
        if row['friend_2'] and row['friend_2'] in member_set:
            wishes.append(row['friend_2'])
        if wishes:
            friend_wishes[row['member_no']] = wishes

    # Mutual pairs
    mutual_pairs = set()
    one_way = []
    for member, wishes in friend_wishes.items():
        for friend in wishes:
            if friend in friend_wishes and member in friend_wishes[friend]:
                pair = tuple(sorted([member, friend]))
                mutual_pairs.add(pair)
            else:
                one_way.append((member, friend))

    # Cross-category and unknown (check against all members - but here we only have target)
    print(f"=== Final Friend Wish Summary ===")
    print(f"Participants with >=1 wish in target set: {len(friend_wishes)}")
    print(f"Mutual pairs (both wish each other): {len(mutual_pairs)}")
    print(f"One-way wishes: {len(one_way)}")
    print(f"Without any resolved friend wish: {len(df_target) - len(friend_wishes)}")

    return friend_wishes


# =============================================================================
# 6. Group Assignment Engine
# =============================================================================

def assign_groups(df_sorted, group_size, friend_wishes, max_kar=8,
                  diversity_iterations=10000, geo_weight=2.0, seed=42):
    """Run the full group assignment algorithm.

    Phases:
    1. Geographic sort + cut into groups
    2. Fix friend wishes via swaps
    3. Fix kar violations with geo-aware swaps
    2b. Re-fix friends broken during kar balancing
    4. Diversity optimization (simulated annealing)

    Returns df_sorted with 'group' column assigned (0-indexed).
    """
    random.seed(seed)

    n = len(df_sorted)
    n_full_groups = n // group_size
    remainder = n % group_size
    total_groups = n_full_groups + (1 if remainder > 0 else 0)

    print(f"Participants: {n}")
    print(f"Groups: {n_full_groups} x {group_size} + 1 x {remainder} = {total_groups} total")

    # Fast lookup arrays (avoid pandas overhead in hot loops)
    lats = df_sorted['lat'].values.copy()
    lngs = df_sorted['lng'].values.copy()
    kars_arr = df_sorted['kar'].values.copy()
    ages_arr = df_sorted['age'].values.copy()
    sexes_arr = df_sorted['sex'].values.copy()
    member_arr = df_sorted['member_no'].values.copy()
    f1_arr = df_sorted['friend_1'].values.copy()
    f2_arr = df_sorted['friend_2'].values.copy()
    member_to_idx = {m: i for i, m in enumerate(member_arr)}
    rundresa_set = set(member_arr)

    # Reverse friend index: who depends on each participant for their friend wish
    friend_of = defaultdict(set)
    for i in range(n):
        if f1_arr[i] and f1_arr[i] in rundresa_set:
            friend_of[f1_arr[i]].add(i)
        if f2_arr[i] and f2_arr[i] in rundresa_set:
            friend_of[f2_arr[i]].add(i)

    # Group assignment array
    group_of = np.zeros(n, dtype=int)
    for i in range(n_full_groups):
        group_of[i * group_size:(i + 1) * group_size] = i
    if remainder > 0:
        group_of[n_full_groups * group_size:] = n_full_groups

    MAX_KAR = max_kar

    # -----------------------------------------------------------------------
    # Helper functions
    # -----------------------------------------------------------------------
    def get_group_members(g):
        return np.where(group_of == g)[0]

    def has_friend_wish(idx):
        f1, f2 = f1_arr[idx], f2_arr[idx]
        return bool((f1 and f1 in rundresa_set) or (f2 and f2 in rundresa_set))

    def friend_satisfied(idx):
        g = group_of[idx]
        gm = set(member_arr[get_group_members(g)])
        f1, f2 = f1_arr[idx], f2_arr[idx]
        return (f1 in gm) or (f2 in gm)

    def kar_count_in_group(g, kar):
        gm = get_group_members(g)
        return sum(1 for i in gm if kars_arr[i] == kar)

    def can_swap(i1, i2):
        """Check if swap respects kar limit (max_kar)."""
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
        group_of[i1], group_of[i2] = group_of[i2], group_of[i1]

    def count_friend_satisfied():
        return sum(1 for i in range(n) if has_friend_wish(i) and friend_satisfied(i))

    def count_friend_total():
        return sum(1 for i in range(n) if has_friend_wish(i))

    def count_kar_violations():
        total = 0
        for g in range(total_groups):
            gm = get_group_members(g)
            counts = Counter(kars_arr[i] for i in gm if kars_arr[i])
            total += sum(max(0, c - MAX_KAR) for c in counts.values())
        return total

    def affected_by_swap(i1, i2):
        """Get all participants whose friend satisfaction could change from a swap."""
        affected = {i1, i2}
        m1, m2 = member_arr[i1], member_arr[i2]
        affected.update(friend_of.get(m1, set()))
        affected.update(friend_of.get(m2, set()))
        return affected

    def geo_dist_sq(i1, i2):
        """Squared geographic distance (fast, no sqrt needed for comparison)."""
        return (lats[i1] - lats[i2])**2 + (lngs[i1] - lngs[i2])**2

    def group_geo_spread(g):
        """Mean squared distance to group centroid (geographic compactness)."""
        gm = get_group_members(g)
        if len(gm) <= 1:
            return 0.0
        clat = np.mean(lats[gm])
        clng = np.mean(lngs[gm])
        return np.mean([(lats[i] - clat)**2 + (lngs[i] - clng)**2 for i in gm])

    def group_diversity(g):
        """Diversity score: age entropy + sex entropy (higher = more diverse)."""
        gm = get_group_members(g)
        if len(gm) == 0:
            return 0
        age_c = Counter(ages_arr[i] for i in gm)
        total = sum(age_c.values())
        age_ent = -sum((c / total) * math.log2(c / total) for c in age_c.values() if c > 0)
        sex_c = Counter(sexes_arr[i] for i in gm)
        total_s = sum(sex_c.values())
        sex_ent = -sum((c / total_s) * math.log2(c / total_s) for c in sex_c.values() if c > 0)
        return age_ent + sex_ent

    # -----------------------------------------------------------------------
    # Phase 1: Initial geographic assignment (already done by sort + cut)
    # -----------------------------------------------------------------------
    friend_total = count_friend_total()
    print("\n=== Phase 1: Geographic sort + cut ===")
    print(f"  Friend satisfaction: {count_friend_satisfied()}/{friend_total}")
    print(f"  Kar violations: {count_kar_violations()}")
    print(f"  Avg geo spread: {np.mean([group_geo_spread(g) for g in range(total_groups)]):.4f}")

    # -----------------------------------------------------------------------
    # Phase 2: Fix friend wishes via targeted swaps
    # -----------------------------------------------------------------------
    print("\n=== Phase 2: Fix friend wishes ===")
    friend_swaps = 0
    for idx in range(n):
        if not has_friend_wish(idx) or friend_satisfied(idx):
            continue

        target_groups = set()
        for fid in [f1_arr[idx], f2_arr[idx]]:
            if fid and fid in member_to_idx:
                target_groups.add(group_of[member_to_idx[fid]])
        target_groups.discard(group_of[idx])
        if not target_groups:
            continue

        best_cidx = None
        best_net = -999
        best_dist = float('inf')
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
                # Prefer higher net friend gain, then closer geographically
                if net > best_net or (net == best_net and dist < best_dist):
                    best_net = net
                    best_cidx = cidx
                    best_dist = dist

        if best_cidx is not None and best_net >= 0:
            do_swap(idx, best_cidx)
            friend_swaps += 1

    print(f"  Swaps: {friend_swaps}")
    print(f"  Friend satisfaction: {count_friend_satisfied()}/{friend_total}")
    print(f"  Kar violations: {count_kar_violations()}")
    print(f"  Avg geo spread: {np.mean([group_geo_spread(g) for g in range(total_groups)]):.4f}")

    # -----------------------------------------------------------------------
    # Phase 3: Fix kar violations (prefer geographically closest swap)
    # -----------------------------------------------------------------------
    print("\n=== Phase 3: Fix kar violations (geo-aware) ===")
    kar_swaps = 0
    for g in range(total_groups):
        gm = get_group_members(g)
        counts = Counter(kars_arr[i] for i in gm if kars_arr[i])
        for kar, cnt in counts.items():
            if cnt <= MAX_KAR:
                continue
            excess = [i for i in gm if kars_arr[i] == kar]
            for idx in excess[MAX_KAR:]:
                # Collect ALL valid swap candidates across all other groups
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
                # Pick the geographically closest candidate
                best_cidx = min(candidates, key=lambda c: geo_dist_sq(idx, c))
                do_swap(idx, best_cidx)
                kar_swaps += 1

    print(f"  Swaps: {kar_swaps}")
    print(f"  Kar violations: {count_kar_violations()}")
    print(f"  Friend satisfaction: {count_friend_satisfied()}/{friend_total}")
    print(f"  Avg geo spread: {np.mean([group_geo_spread(g) for g in range(total_groups)]):.4f}")

    # -----------------------------------------------------------------------
    # Phase 2b: Re-fix friend wishes lost in Phase 3
    # -----------------------------------------------------------------------
    print("\n=== Phase 2b: Re-fix friends after kar fix ===")
    friend_swaps_2b = 0
    for idx in range(n):
        if not has_friend_wish(idx) or friend_satisfied(idx):
            continue

        target_groups = set()
        for fid in [f1_arr[idx], f2_arr[idx]]:
            if fid and fid in member_to_idx:
                target_groups.add(group_of[member_to_idx[fid]])
        target_groups.discard(group_of[idx])
        if not target_groups:
            continue

        best_cidx = None
        best_net = -999
        best_dist = float('inf')
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
                    best_net = net
                    best_cidx = cidx
                    best_dist = dist

        if best_cidx is not None and best_net >= 0:
            do_swap(idx, best_cidx)
            friend_swaps_2b += 1

    print(f"  Swaps: {friend_swaps_2b}")
    print(f"  Friend satisfaction: {count_friend_satisfied()}/{friend_total}")
    print(f"  Kar violations: {count_kar_violations()}")
    print(f"  Avg geo spread: {np.mean([group_geo_spread(g) for g in range(total_groups)]):.4f}")

    # -----------------------------------------------------------------------
    # Phase 4: Diversity optimization (simulated annealing)
    # Preserves friend satisfaction AND geographic compactness
    # -----------------------------------------------------------------------
    print(f"\n=== Phase 4: Diversity optimization (geo-penalized) ===")

    GEO_WEIGHT = geo_weight

    div_before = sum(group_diversity(g) for g in range(total_groups))
    geo_before = np.mean([group_geo_spread(g) for g in range(total_groups)])
    diversity_swaps = 0
    temperature = 1.0

    for iteration in range(diversity_iterations):
        i1 = random.randint(0, n - 1)
        i2 = random.randint(0, n - 1)
        g1, g2 = group_of[i1], group_of[i2]
        if g1 == g2 or not can_swap(i1, i2):
            continue

        # Check all affected participants' friend satisfaction
        affected = affected_by_swap(i1, i2)
        old_sat = sum(1 for a in affected if has_friend_wish(a) and friend_satisfied(a))

        old_div = group_diversity(g1) + group_diversity(g2)
        old_geo = group_geo_spread(g1) + group_geo_spread(g2)
        do_swap(i1, i2)

        new_sat = sum(1 for a in affected if has_friend_wish(a) and friend_satisfied(a))
        new_div = group_diversity(g1) + group_diversity(g2)
        new_geo = group_geo_spread(g1) + group_geo_spread(g2)

        # Combined score: diversity gain minus geographic spread penalty
        div_improvement = new_div - old_div
        geo_penalty = (new_geo - old_geo) * GEO_WEIGHT
        improvement = div_improvement - geo_penalty

        # Reject if any friend satisfaction is lost, or if combined score worsens (with SA)
        if new_sat < old_sat or (improvement < 0 and random.random() > math.exp(improvement / max(temperature, 0.01))):
            do_swap(i1, i2)  # reject
        else:
            diversity_swaps += 1

        temperature *= 0.9995

    div_after = sum(group_diversity(g) for g in range(total_groups))
    geo_after = np.mean([group_geo_spread(g) for g in range(total_groups)])
    print(f"  Swaps: {diversity_swaps}")
    print(f"  Diversity score: {div_before:.2f} -> {div_after:.2f}")
    print(f"  Avg geo spread: {geo_before:.4f} -> {geo_after:.4f}")

    # -----------------------------------------------------------------------
    # Write results back to DataFrame
    # -----------------------------------------------------------------------
    df_sorted['group'] = group_of

    print(f"\n{'=' * 50}")
    print(f"=== FINAL RESULTS ===")
    print(f"{'=' * 50}")
    print(f"Groups: {n_full_groups} x {group_size} + 1 x {remainder}")
    print(f"Friend satisfaction: {count_friend_satisfied()}/{friend_total} "
          f"({count_friend_satisfied() / max(1, friend_total) * 100:.0f}%)")
    print(f"Kar violations: {count_kar_violations()}")
    print(f"Total swaps: {friend_swaps + kar_swaps + friend_swaps_2b + diversity_swaps}")
    print(f"Diversity: {div_after:.2f}")
    print(f"Avg geo spread: {geo_after:.4f}")

    return df_sorted


# =============================================================================
# 7. Quality Metrics
# =============================================================================

def haversine_km(lat1, lng1, lat2, lng2):
    """Compute haversine distance between two lat/lng points in km."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2)**2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2)**2)
    return R * 2 * math.asin(min(1.0, math.sqrt(a)))


def print_group_metrics(df_sorted, group_of, total_groups, group_size=36, age_columns=None):
    """Print per-group quality table.

    df_sorted: DataFrame with participant data (must have lat, lng, kar, age, sex, member_no,
               friend_1, friend_2 columns)
    group_of: numpy array of group assignments (0-indexed)
    total_groups: number of groups
    group_size: expected group size (for display)
    age_columns: list of ages to show as columns (default: [14, 15, 16, 17]).
                 Use e.g. ['18-24', '25-34', '35-44', '45+'] for age range buckets.
                 If items are strings containing '-' or '+', ages are bucketed into ranges.
    """
    if age_columns is None:
        age_columns = [14, 15, 16, 17]
    lats = df_sorted['lat'].values
    lngs = df_sorted['lng'].values
    kars_arr = df_sorted['kar'].values
    ages_arr = df_sorted['age'].values
    sexes_arr = df_sorted['sex'].values
    member_arr = df_sorted['member_no'].values
    f1_arr = df_sorted['friend_1'].values
    f2_arr = df_sorted['friend_2'].values
    member_set = set(member_arr)

    def get_group_members(g):
        return np.where(group_of == g)[0]

    def has_friend_wish(idx):
        f1, f2 = f1_arr[idx], f2_arr[idx]
        return bool((f1 and f1 in member_set) or (f2 and f2 in member_set))

    def friend_satisfied(idx):
        g = group_of[idx]
        gm = set(member_arr[get_group_members(g)])
        f1, f2 = f1_arr[idx], f2_arr[idx]
        return (f1 in gm) or (f2 in gm)

    # Parse age columns: support both individual ages [14, 15, 16, 17]
    # and range buckets ['18-24', '25-34', '35-44', '45+']
    use_buckets = any(isinstance(c, str) and ('-' in c or '+' in c) for c in age_columns)

    if use_buckets:
        # Parse range strings into (label, min_age, max_age) tuples
        age_buckets = []
        for col in age_columns:
            col_str = str(col)
            if '+' in col_str:
                lo = int(col_str.replace('+', ''))
                age_buckets.append((col_str, lo, 999))
            elif '-' in col_str:
                lo, hi = col_str.split('-')
                age_buckets.append((col_str, int(lo), int(hi)))
            else:
                age_buckets.append((col_str, int(col_str), int(col_str)))

        def bucket_age(age):
            """Return bucket label for a given age."""
            for label, lo, hi in age_buckets:
                if lo <= age <= hi:
                    return label
            return '?'

        def count_ages_in_group(gm):
            """Return dict of bucket_label -> count."""
            c = Counter(bucket_age(ages_arr[i]) for i in gm)
            return c
    else:
        def count_ages_in_group(gm):
            """Return dict of age -> count."""
            return Counter(ages_arr[i] for i in gm)

    # Build column width: max of label length and 3
    age_col_widths = [max(len(str(c)), 3) for c in age_columns]
    age_header = ' '.join(f"{str(c):>{w}}" for c, w in zip(age_columns, age_col_widths))
    sep_len = 48 + sum(w + 1 for w in age_col_widths) + 16

    print(f"{'Grupp':>5} {'Storlek':>7} {'Van%':>5} {'MaxKar':>6} {'M/K/A':>9} "
          f"{age_header} {'AvstandKm':>10} {'Karer':>5}")
    print("-" * sep_len)

    all_dists = []
    for g in range(total_groups):
        gm = get_group_members(g)
        rows = df_sorted.loc[gm]

        # Size
        size = len(gm)

        # Friend satisfaction
        f_ok = sum(1 for i in gm if has_friend_wish(i) and friend_satisfied(i))
        f_tot = sum(1 for i in gm if has_friend_wish(i))
        f_pct = f"{f_ok}/{f_tot}" if f_tot > 0 else "-"

        # Max kar count
        kar_c = Counter(kars_arr[i] for i in gm if kars_arr[i])
        max_kar_val = max(kar_c.values()) if kar_c else 0

        # Sex distribution
        sex_c = Counter(SEX_MAP.get(sexes_arr[i], '?') for i in gm)
        m_k_a = f"{sex_c.get('Man', 0)}/{sex_c.get('Kvinna', 0)}/{sex_c.get('Annat', 0)}"

        # Age distribution
        age_c = count_ages_in_group(gm)

        # Geographic spread: mean distance to centroid
        clat, clng = np.mean(lats[gm]), np.mean(lngs[gm])
        avg_dist = np.mean([haversine_km(lats[i], lngs[i], clat, clng) for i in gm])
        all_dists.append(avg_dist)

        # Unique karer
        n_karer = len(kar_c)

        # Build age values string
        age_vals = ' '.join(
            f"{age_c.get(c, 0):>{w}}" for c, w in zip(age_columns, age_col_widths)
        )

        print(f"{g + 1:>5} {size:>7} {f_pct:>5} {max_kar_val:>6} {m_k_a:>9} "
              f"{age_vals} "
              f"{avg_dist:>9.0f} {n_karer:>5}")

    # Overall stats
    print("-" * sep_len)
    print(f"Avg geographic spread: {np.mean(all_dists):.0f} km")
    print(f"Min/Max spread: {np.min(all_dists):.0f} / {np.max(all_dists):.0f} km")


# =============================================================================
# 8. Export
# =============================================================================

def export_results(df_sorted, group_of, total_groups, output_dir, prefix='wsj27'):
    """Export CSV + JSON. Returns (csv_path, json_path).

    df_sorted: DataFrame with participant data
    group_of: numpy array of group assignments (0-indexed)
    total_groups: number of groups
    output_dir: directory to write files to
    prefix: filename prefix
    """
    lats = df_sorted['lat'].values
    lngs = df_sorted['lng'].values
    kars_arr = df_sorted['kar'].values
    ages_arr = df_sorted['age'].values
    sexes_arr = df_sorted['sex'].values
    member_arr = df_sorted['member_no'].values

    def get_group_members(g):
        return np.where(group_of == g)[0]

    # Build export DataFrame
    export_cols = ['group', 'name', 'member_no', 'age', 'sex', 'kar', 'district', 'region',
                   'friend_1', 'friend_2', 'lat', 'lng']
    df_export = df_sorted[export_cols].copy()
    df_export['group'] = df_export['group'] + 1  # 1-indexed for humans
    df_export['sex'] = df_export['sex'].map(SEX_MAP)
    df_export = df_export.sort_values(['group', 'kar', 'name']).reset_index(drop=True)

    # Save CSV
    csv_path = f'{output_dir}/{prefix}_grupper.csv'
    df_export.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"Saved {len(df_export)} participants to {csv_path}")

    # Save JSON summary
    group_summary = []
    for g in range(total_groups):
        gm = get_group_members(g)
        kar_c = Counter(kars_arr[i] for i in gm if kars_arr[i])
        age_c = Counter(int(ages_arr[i]) for i in gm)
        sex_c = Counter(SEX_MAP.get(sexes_arr[i], '?') for i in gm)
        clat = float(np.mean(lats[gm]))
        clng = float(np.mean(lngs[gm]))

        group_summary.append({
            'group': g + 1,
            'size': int(len(gm)),
            'centroid': {'lat': round(clat, 4), 'lng': round(clng, 4)},
            'age_distribution': dict(sorted(age_c.items())),
            'sex_distribution': dict(sex_c),
            'karer': dict(kar_c.most_common()),
            'members': [
                {'name': df_sorted.at[i, 'name'], 'member_no': str(member_arr[i]),
                 'kar': str(kars_arr[i]), 'age': int(ages_arr[i])}
                for i in sorted(gm, key=lambda x: kars_arr[x])
            ]
        })

    json_path = f'{output_dir}/{prefix}_grupper.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(group_summary, f, ensure_ascii=False, indent=2)
    print(f"Saved group summary to {json_path}")

    # Preview
    print(f"\nCSV preview (first 10 rows):")
    print(df_export.head(10).to_string(index=False))

    return csv_path, json_path


# =============================================================================
# 9. Map Generation (using direct CDN HTML, not keplergl Python)
# =============================================================================

_HTML_TEMPLATE = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<link href="https://d1a3f4spazzrp4.cloudfront.net/kepler.gl/uber-fonts/4.0.0/superfine.css" rel="stylesheet">
<link href="https://api.tiles.mapbox.com/mapbox-gl-js/v1.1.1/mapbox-gl.css" rel="stylesheet">
<script src="https://unpkg.com/react@17.0.2/umd/react.production.min.js" crossorigin></script>
<script src="https://unpkg.com/react-dom@17.0.2/umd/react-dom.production.min.js" crossorigin></script>
<script src="https://unpkg.com/redux@3.7.2/dist/redux.js" crossorigin></script>
<script src="https://unpkg.com/react-redux@7.1.3/dist/react-redux.min.js" crossorigin></script>
<script src="https://unpkg.com/react-intl@3.12.0/dist/react-intl.min.js" crossorigin></script>
<script src="https://unpkg.com/react-copy-to-clipboard@5.0.2/build/react-copy-to-clipboard.min.js" crossorigin></script>
<script src="https://unpkg.com/styled-components@4.1.3/dist/styled-components.min.js" crossorigin></script>
<script src="https://unpkg.com/kepler.gl@2.5.5/umd/keplergl.min.js" crossorigin></script>
<style>
  font-family: ff-clan-web-pro, 'Helvetica Neue', Helvetica, sans-serif;
  font-weight: 400;
  font-size: 0.875em;
  line-height: 1.71429;
  *, *:before, *:after { box-sizing: border-box; }
  body { margin: 0; padding: 0; }
  #app { width: 100vw; height: 100vh; position: absolute; top: 0; left: 0; }
</style>
</head>
<body>
<div id="app"></div>
<script>window.__keplerglDataConfig = __DATA_CONFIG__;</script>
<script>
(function() {
  var K = window.KeplerGl;
  var Redux = window.Redux;

  // Store with KeplerGL reducer
  var reducer = K.keplerGlReducer.initialState({
    uiState: { currentModal: null, activeSidePanel: null }
  });
  var middlewares = K.enhanceReduxMiddleware([]);
  var store = Redux.createStore(
    Redux.combineReducers({ keplerGl: reducer }),
    {},
    Redux.applyMiddleware.apply(null, middlewares)
  );

  // Default KeplerGL component with all features (export, filters, etc)
  var MapApp = K.injectComponents([]);

  // Resize tracking
  var dims = { w: window.innerWidth, h: window.innerHeight };
  function App() {
    var ref = React.useState(dims);
    var size = ref[0], setSize = ref[1];
    React.useEffect(function() {
      function onResize() { setSize({ w: window.innerWidth, h: window.innerHeight }); }
      window.addEventListener('resize', onResize);
      return function() { window.removeEventListener('resize', onResize); };
    }, []);
    return React.createElement(
      ReactRedux.Provider, { store: store },
      React.createElement(MapApp, {
        mapboxApiAccessToken: '__MAPBOX_TOKEN__',
        id: 'map',
        width: size.w,
        height: size.h,
        appName: '__TITLE__'
      })
    );
  }

  ReactDOM.render(React.createElement(App), document.getElementById('app'));

  // Load data
  var cfg = window.__keplerglDataConfig;
  var datasets = Object.keys(cfg.data).map(function(key) {
    var d = cfg.data[key];
    return {
      info: { id: key, label: key },
      data: {
        fields: d.columns.map(function(c) { return { name: c }; }),
        rows: d.data
      }
    };
  });

  store.dispatch(K.addDataToMap({
    datasets: datasets,
    config: cfg.config,
    options: cfg.options || { centerMap: true }
  }));
})();
</script>
</body>
</html>'''


def generate_group_map_html(df_sorted, total_groups, output_path, title='WSJ 2027',
                            friend_wishes=None, show_group_arcs=False):
    """Generate KeplerGL HTML map with groups colored. Uses CDN, no Python keplergl needed.

    df_sorted: DataFrame with columns: name, kar, age, lat, lng, group (0-indexed)
    total_groups: number of groups
    output_path: path to write HTML file
    title: page title
    friend_wishes: optional dict {member_no: [friend_member_nos]} to show arc connections.
                   Green arcs = satisfied (same group), red arcs = unsatisfied.
    show_group_arcs: if True, add arcs between all members within the same group
                     (hidden by default, toggle on in KeplerGL UI).
    """
    # Build map DataFrame with small jitter so same-kar participants don't overlap
    np.random.seed(42)
    df_map = df_sorted[['name', 'kar', 'age', 'lat', 'lng', 'group']].copy()
    df_map['group'] = df_map['group'] + 1  # 1-indexed
    df_map['group_name'] = df_map['group'].apply(lambda g: f'Grupp {g}')
    # Add jitter (+/-0.01 degrees ~ +/-1km) so overlapping kar members spread out
    jitter_lat = np.random.uniform(-0.01, 0.01, len(df_map))
    jitter_lng = np.random.uniform(-0.01, 0.01, len(df_map))
    df_map['lat'] = df_map['lat'] + jitter_lat
    df_map['lng'] = df_map['lng'] + jitter_lng

    layers = [
        {
            'id': 'groups',
            'type': 'point',
            'config': {
                'dataId': 'grupper',
                'label': 'Deltagare',
                'isVisible': True,
                'columns': {'lat': 'lat', 'lng': 'lng'},
                'color': [31, 120, 180],
                'colorField': {'name': 'group', 'type': 'integer'},
                'colorScale': 'ordinal',
                'visConfig': {
                    'radius': 8,
                    'fixedRadius': False,
                    'opacity': 0.85,
                    'outline': True,
                    'thickness': 1.5,
                    'strokeColor': [255, 255, 255],
                    'colorRange': {
                        'name': 'Group Colors',
                        'type': 'qualitative',
                        'category': 'Custom',
                        'colors': [
                            '#' + ''.join(f'{c:02x}' for c in rgb)
                            for rgb in GROUP_COLORS[:total_groups]
                        ],
                    },
                    'radiusRange': [4, 12],
                    'filled': True,
                },
            },
        }
    ]

    data = {'grupper': df_map.to_dict(orient='split')}
    arc_rows = []

    # Build friend connection arcs if friend_wishes provided
    if friend_wishes:
        member_to_idx = {m: i for i, m in enumerate(df_sorted['member_no'].values)}
        member_set = set(df_sorted['member_no'].values)
        groups = df_sorted['group'].values
        # Use jittered coordinates so arcs connect to visible dot positions
        map_lats = df_map['lat'].values
        map_lngs = df_map['lng'].values

        seen_pairs = set()
        for member, friends in friend_wishes.items():
            if member not in member_to_idx:
                continue
            src_idx = member_to_idx[member]
            for friend in friends:
                if friend not in member_to_idx:
                    continue
                pair = tuple(sorted([member, friend]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                dst_idx = member_to_idx[friend]
                satisfied = int(groups[src_idx] == groups[dst_idx])
                arc_rows.append({
                    'src_name': df_sorted.iloc[src_idx]['name'],
                    'dst_name': df_sorted.iloc[dst_idx]['name'],
                    'src_lat': float(map_lats[src_idx]),
                    'src_lng': float(map_lngs[src_idx]),
                    'dst_lat': float(map_lats[dst_idx]),
                    'dst_lng': float(map_lngs[dst_idx]),
                    'satisfied': satisfied,
                    'src_group': int(groups[src_idx] + 1),
                    'dst_group': int(groups[dst_idx] + 1),
                })

        if arc_rows:
            df_arcs = pd.DataFrame(arc_rows)
            data['vanonskan'] = df_arcs.to_dict(orient='split')

            n_ok = sum(1 for r in arc_rows if r['satisfied'])
            n_fail = len(arc_rows) - n_ok
            print(f"Friend arcs: {len(arc_rows)} ({n_ok} satisfied, {n_fail} unsatisfied)")

            # Satisfied arcs (green, visible by default)
            layers.append({
                'id': 'friends-ok',
                'type': 'arc',
                'config': {
                    'dataId': 'vanonskan',
                    'label': 'Vänönskan (uppfylld)',
                    'isVisible': True,
                    'columns': {
                        'lat0': 'src_lat', 'lng0': 'src_lng',
                        'lat1': 'dst_lat', 'lng1': 'dst_lng',
                    },
                    'color': [46, 204, 113],
                    'visConfig': {
                        'opacity': 0.6,
                        'thickness': 2,
                        'targetColor': [46, 204, 113],
                    },
                },
                'visualChannels': {
                    'sizeField': None,
                    'colorField': None,
                },
                'textLabel': [],
            })

            # Unsatisfied arcs (red, hidden by default - can toggle on)
            layers.append({
                'id': 'friends-fail',
                'type': 'arc',
                'config': {
                    'dataId': 'vanonskan',
                    'label': 'Vänönskan (ej uppfylld)',
                    'isVisible': False,
                    'columns': {
                        'lat0': 'src_lat', 'lng0': 'src_lng',
                        'lat1': 'dst_lat', 'lng1': 'dst_lng',
                    },
                    'color': [231, 76, 60],
                    'visConfig': {
                        'opacity': 0.5,
                        'thickness': 1.5,
                        'targetColor': [231, 76, 60],
                    },
                },
                'visualChannels': {
                    'sizeField': None,
                    'colorField': None,
                },
                'textLabel': [],
            })

    # Build group-internal arcs (all pairs within same group)
    if show_group_arcs:
        groups_arr = df_map['group'].values  # 1-indexed
        map_lats_all = df_map['lat'].values
        map_lngs_all = df_map['lng'].values
        names_arr = df_map['name'].values

        group_arc_rows = []
        for g in range(1, total_groups + 1):
            members = np.where(groups_arr == g)[0]
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    mi, mj = members[i], members[j]
                    group_arc_rows.append([
                        float(map_lats_all[mi]), float(map_lngs_all[mi]),
                        float(map_lats_all[mj]), float(map_lngs_all[mj]),
                        int(g), str(names_arr[mi]), str(names_arr[mj]),
                    ])

        if group_arc_rows:
            df_ga = pd.DataFrame(group_arc_rows,
                                 columns=['src_lat', 'src_lng', 'dst_lat', 'dst_lng',
                                          'group', 'src_name', 'dst_name'])
            data['grupp_kopplingar'] = df_ga.to_dict(orient='split')
            print(f"Group arcs: {len(group_arc_rows)} connections across {total_groups} groups")

            group_hex = ['#' + ''.join(f'{c:02x}' for c in rgb)
                         for rgb in GROUP_COLORS[:total_groups]]
            layers.append({
                'id': 'group-arcs',
                'type': 'arc',
                'config': {
                    'dataId': 'grupp_kopplingar',
                    'label': 'Gruppkopplingar',
                    'isVisible': False,
                    'columns': {
                        'lat0': 'src_lat', 'lng0': 'src_lng',
                        'lat1': 'dst_lat', 'lng1': 'dst_lng',
                    },
                    'color': [200, 200, 200],
                    'colorField': {'name': 'group', 'type': 'integer'},
                    'colorScale': 'ordinal',
                    'visConfig': {
                        'opacity': 0.3,
                        'thickness': 1,
                        'colorRange': {
                            'name': 'Group Colors',
                            'type': 'qualitative',
                            'category': 'Custom',
                            'colors': group_hex,
                        },
                    },
                },
                'visualChannels': {
                    'sizeField': None,
                },
                'textLabel': [],
            })

    kepler_config = {
        'version': 'v1',
        'config': {
            'mapState': {
                'latitude': 60.0,
                'longitude': 15.5,
                'zoom': 5,
            },
            'visState': {
                'filters': [],
                'layers': layers,
            },
        },
    }

    # Add filters to split arcs by satisfied status
    if friend_wishes and arc_rows:
        kepler_config['config']['visState']['filters'] = [
            {
                'dataId': ['vanonskan'],
                'id': 'filter-satisfied',
                'name': ['satisfied'],
                'type': 'range',
                'value': [1, 1],
                'enlarged': False,
                'plotType': 'histogram',
                'animationWindow': 'free',
                'yAxis': None,
                'layerId': ['friends-ok'],
            },
            {
                'dataId': ['vanonskan'],
                'id': 'filter-unsatisfied',
                'name': ['satisfied'],
                'type': 'range',
                'value': [0, 0],
                'enlarged': False,
                'plotType': 'histogram',
                'animationWindow': 'free',
                'yAxis': None,
                'layerId': ['friends-fail'],
            },
        ]

    data_config = {
        'config': kepler_config,
        'data': data,
        'options': {'readOnly': False, 'centerMap': False},
    }

    data_config_json = json.dumps(data_config)
    html_content = (_HTML_TEMPLATE
                    .replace('__DATA_CONFIG__', data_config_json)
                    .replace('__MAPBOX_TOKEN__', MAPBOX_TOKEN)
                    .replace('__TITLE__', title))

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"Saved group map: {output_path}")
    return output_path
