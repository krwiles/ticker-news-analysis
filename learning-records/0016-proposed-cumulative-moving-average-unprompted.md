# Independently proposed the cumulative-moving-average update formula for an incrementally-maintained aggregate

Designing how a Story's aggregate sentiment score should stay updated as new members resolve, the user
proposed, unprompted, computing it via "a formula for taking the existing average and then adding in the
effect of a new number" — rather than accepting the option initially offered (a live `AVG(...)` query
recomputed on every read, modeled on this project's own ADR 0009 precedent for deriving Story's primary).
This is the standard online/cumulative-moving-average update
(`new_average = old_average + (new_score - old_average) / new_count`). The user correctly anticipated, before
being told, that this requires a stored running count alongside the average, and explicitly reasoned about it
as the option requiring the least new code.

**Implication for future teaching**: this user has genuine, transferable algorithmic literacy beyond
backend/frontend mechanics — comfortable with streaming/incremental computation techniques, not just
directing at a product level (see also [[user_profile]] in Claude's own memory, extended with this same
finding). Future lessons touching any kind of running aggregate, cache invalidation, or
incremental-vs-recompute trade-off can introduce the concept at this level rather than starting from "here's
what an average is."
