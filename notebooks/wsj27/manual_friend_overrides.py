"""Manual overrides for WSJ 2027 group assignment.

Used by `wsj27_utils.apply_manual_overrides()` (friends/kår wishes) and
`wsj27_utils.assign_coordinates()` (coordinate fallbacks).

## When to edit this file

Run the rundresa or direktresa notebook. After it prints the friend-matching
summary, look at three sections:

  1. "Matched (verify these are correct)" — each fuzzy match shown with its
     ORIGINAL text. If a match is wrong, add an UNRESOLVED_PAIRS entry to
     override it with the correct member_no.

  2. "Unresolved" — text wishes the matcher couldn't resolve. If you can find
     the friend by name elsewhere in the project, add an UNRESOLVED_PAIRS
     entry with the correct member_no.

  3. "Generic wishes (skipped)" — text like "scouts from kåren X". Pick which
     kår the requester wants and add a KAR_WISHES entry. The algorithm picks
     the geographically nearest scout from that kår as the synthetic friend.

After editing, re-run the notebook. Overrides are applied AFTER fuzzy match,
so they take precedence over wrong matches.

## Format

UNRESOLVED_PAIRS:
    List of (requester_member_no, friend_member_no) tuples. Both as strings.
    Each entry creates ONE friend wish from requester → friend. To make it
    mutual, add both directions explicitly.

KAR_WISHES:
    Dict {requester_member_no: 'Kår Name'}. The kår name is matched
    case-insensitively as a substring against participants' kar field.

## Notes

- Both files take precedence over fuzzy match results. If a slot was
  already filled by registration form, manual overrides will overwrite it
  (a warning is printed).
- If a kår has no members in the requester's travel group (rundresa or
  direktresa), the wish is skipped with a warning.

## Coordinate overrides

When a kår is missing from the geocode cache, or when a participant has no
kår at all, the algorithm falls back to the Sweden centroid (62.0, 15.0)
which damages geographic clustering.

MANUAL_KAR_COORDS:
    Dict {kar_name: (lat, lng)}. Adds entries to the geocode lookup. Use
    this when a real scout kår exists in the dataset but isn't yet in
    `scoutkar_geocode_cache.json`.

MANUAL_PERSON_COORDS:
    Dict {member_no: (lat, lng)}. Overrides coordinates for a specific
    participant. Use this when someone has no kår, or when the kår is in
    Sweden but they live elsewhere.
"""

UNRESOLVED_PAIRS = [
    # Strong matches confirmed by name + kår agreement; both registered as rundresa.
    ('3398810', '3295882'),  # Axel Lindroth -> Charlie Lindberg (Saltsjö-Boo)
    # Ebba Stoor wished for "Elsie Pilawa Potgurski och Elsa Blomme" plus "Carl-Johan Samils".
    # Three friends but only two slots — Carl-Johan is already in friend_2 via fuzzy match,
    # so we can add only one of Elsie/Elsa. Picking Elsa (higher fuzzy score 0.78 vs 0.72).
    ('3357048', '3374890'),  # Ebba Stoor -> Elsa Blommé (Järlinden)
    ('3355409', '3357284'),  # Ester Magnusson -> Madeleine Meyer (Vallentuna)
    ('3497667', '3489697'),  # Molly Majnesjö -> Sebastian Kardin (Equmenia Scout)
    ('3444944', '3444947'),  # Moltas Adén -> Sven Kolterud (Equmenia Mölnlycke)
]

KAR_WISHES = {
    # All requesters are rundresa. Kår names verified to exist in the dataset.
    '3340070': 'Redbergslids Scoutkår',     # Anuttara Bailur "Redbergslid scouterna"
    '3358592': 'Danderyds Sjöscoutkår',     # Hjalmar Löf "Någon från Danderyds sjöscoutkår"
    '3350831': 'Hanekinds scoutkår',        # Sebastian Stjärnström "Övriga deltagare från Hanekinds scoutkår"
    '3352989': 'Scoutkåren Göta Lejon',     # Sam Evert "gärna någon från scoutkåren göta lejon"
    '3337698': 'Mölnlycke Scoutkår',        # Liv Wikström "scouter från Mölnlycke NSF" (no NSF kår exists; using Mölnlycke Scoutkår)
    '3320994': 'Växjö Scoutkår',            # Anton Törnblad "Växjö eller Rottne" (defaulted to Växjö; flip to Rottne if preferred)
}

MANUAL_KAR_COORDS = {
    # Kårer that aren't in scoutkar_geocode_cache.json yet.
    'Lidingö-Bodals Sjöscoutkår': (59.358, 18.133),  # Bodals harbour, south Lidingö
    'Valsätrakyrkans Scoutkår':   (59.835, 17.626),  # Valsätra, southern Uppsala (egen_resa only)
}

MANUAL_PERSON_COORDS = {
    # Participants with no kår or whose kår's coordinates don't reflect where they live.
    # '3357376': (59.33, 18.07),  # Emma Trehn — rundresa, no kår info. Replace with her actual location.
}

# ---------------------------------------------------------------------------
# Forced placement (post-algorithm, may violate kår=8)
# ---------------------------------------------------------------------------

PLACEMENT_MAX_KAR_WARN = 6  # warn in placement output when a swap pushes a kår above this

MANUAL_PLACEMENT = [
    # List of (member_no_A, member_no_B) tuples. After assign_groups runs,
    # apply_manual_placement() forces person A into person B's group by
    # swapping A with whoever in B's group would maximise the global friend
    # count. This may push the kår count in B's group above max_kar (=6) —
    # that's the explicit trade-off you accept by adding an entry here.
    #
    # Pre-populated with cases identified during the original max_kar=8 run.
    # Re-evaluate after lowering to max_kar=6: some entries may no longer
    # be needed (the algorithm finds new solutions) while others may need
    # to be added (more pairs become kår-blocked at the tighter limit).
    ('3356712', '3379909'),  # Judit Ströberg → Emelie Skålén (Tuve)
    ('3320628', '3306521'),  # Johannes Leander → Hugo Bratt (Viggbyholms)
    ('3374409', '3351676'),  # Frans Ågren → Tage Säfvestad (Segeltorps)
]

