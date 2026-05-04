"""Manual friend-wish overrides for WSJ 2027 group assignment.

Used by `wsj27_utils.apply_manual_overrides()` to handle two situations the
fuzzy matcher in `resolve_friend_wishes` can't resolve.

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
"""

UNRESOLVED_PAIRS = [
    # ('123456', '789012'),  # member_no requester, member_no friend
]

KAR_WISHES = {
    # '123456': 'Mölnlycke NSF Scoutkår',  # requester -> kår
}
