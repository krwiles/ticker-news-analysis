# Correctly generalized "derive, don't store" after independently catching a processing-order ambiguity first

Two connected moments in the same design arc (the Story/Headline schema, lesson 17). First: given "a Story's
primary is always its earliest-published member," the assistant had described this loosely as "whichever was
processed first" — conflating processing order with publication order, which aren't guaranteed to match given
headlines arrive via concurrent, non-chronological provider responses. The user caught this precisely and
proposed the exact fix unprompted: "let's specify that headlines get processed oldest-to-newest so that as a
consequence, the primary headline... is going to be the first published headline about that particular story."
Not just noticing the ambiguity — proposing the correct mechanism to close it.

Second, reviewing the resulting schema (a `stories.primary_headline_id` back-pointer, nullable forever,
backfilled in a second write after the referenced headline existed), the user asked whether a more conventional
alternative existed. When the assistant offered a lighter `is_primary` flag as one option, the user pushed
further on their own: since "primary" is fully computable from `story_id` + `published_at`, neither a
back-pointer nor a flag needed to exist at all — the fact could just be derived via query. Correctly applied
the classic "don't store what you can derive" normalization principle to eliminate a working, already-tested
design (a circular FK) in favor of a genuinely simpler one, before it ever shipped.

**Implication for future teaching**: this user reliably asks "is this fact actually new information, or fully
derivable from what's already stored?" when reviewing a schema — a real normalization instinct, not a
memorized rule. Future data-model lessons don't need to re-derive "avoid redundant state" from first principles
for this user; a good move when explaining a schema decision is to lead with that exact question, since it's
the one that already found a real simplification here.
