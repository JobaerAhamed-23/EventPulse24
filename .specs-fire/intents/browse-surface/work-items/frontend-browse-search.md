---
id: frontend-browse-search
title: Inline Keyword Search — the Grammar, and the Two Different Emptinesses
intent: browse-surface
complexity: medium
mode: confirm
status: completed
depends_on:
  - frontend-browse-shell-and-grid
created: 2026-11-12
run_id: run-eventpulse24-029
completed_at: 2026-11-12T12:18:21.644Z
---

# Work Item: Inline Keyword Search — the Grammar, and the Two Different Emptinesses

## Description

Amendment A-11 replaced the city page's filter chip rail with a single search input, and
locked the chip rail out. One `<input type="search">` below the hero is the **only** filter
surface on this page: no chips, no date pickers, no preset toggles.

The placeholder teaches the grammar in place — "Search this week — jazz, free, outdoor,
tag:music" — and the grammar is small enough to be honest about: whitespace-split, lowercased,
AND-matched; `tag:` literals constrained to the why-tag set.

Matching runs **client-side over the loaded set**, decided at capture. That is a real
limitation and this item owns stating it rather than hiding it.

## Acceptance Criteria

- [ ] A single `<input type="search">` renders below the hero, full-width to max-width 720px,
      using `component.input.field` tokens with the documented A-11 `surface.paper` fill
- [ ] Placeholder is verbatim: `Search this week — jazz, free, outdoor, tag:music`
- [ ] Plain words are whitespace-split, lowercased and trimmed, then **AND**-matched against
      the card's headline, its where line, and its why-tag tokens — a card matches only if
      every term matches something
- [ ] `tag:<token>` literals match **only** against the why-tag set, and combine with plain
      words by AND
- [ ] The ten documented tags all work: music, tech, community, arts, family, food, sports,
      outdoor, indoor, rooftop
- [ ] An unknown `tag:` token matches nothing rather than falling back to a plain-word match
      — silently widening a constrained query would make the grammar untrustworthy
- [ ] When a query matches zero cards, **the section heads and grid are removed** and one
      full-width `component.emptystate.quiet` renders in the grid container: "Nothing
      matched." + a `Text.Meta` "Clear" link that empties the input
- [ ] **The two empty states are distinguishable in the DOM, not just to the eye.** A test
      asserts that the no-match state and the zero-events state render different copy and
      different recovery actions, so the user always knows whether their query or the data
      is the reason
- [ ] No chip rail, no category buttons, no date presets exist in the markup — asserted by a
      test, since A-11 is a lock and locks need enforcement
- [ ] Filtering is instant on the loaded set, with no network request per keystroke
- [ ] **The chunk-bounded limitation is documented in the component's own doc comment**: the
      search sees only loaded cards, so a match past the current chunk does not appear until
      that chunk loads
- [ ] Accessibility: the input has an accessible label, and the result-count change is
      announced politely rather than silently replacing the grid

## Technical Notes

`mockups/browse-desktop-filtered.html` is the reference for the filtered state and
`browse-desktop-empty.html` for the no-match state. The latter's copy — *"No cards in
tonight + 7 days satisfy both `quantum` and `poetry`. Drop a term, or browse the full
list."* — shows the intended tone: it names the terms back to the user.

Tokenisation is the kind of thing that looks trivial and has edge cases. Test at minimum:
empty query, whitespace-only query, mixed case, a plain word that is also a tag name, a
`tag:` with no token after the colon, and two tags at once.

## Dependencies

- frontend-browse-shell-and-grid
