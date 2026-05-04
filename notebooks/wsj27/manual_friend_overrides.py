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
