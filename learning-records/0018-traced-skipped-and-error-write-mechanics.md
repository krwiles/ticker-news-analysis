# Traced skipped's and error's actual write mechanics instead of assuming symmetric handling

Asked to leave `skipped` headlines untouched by a status-reset fix (by analogy with an earlier note that
excluded it from a related frontend check), the user didn't accept the symmetry: "Do we mark headlines as
skipped in the same way we mark them as error? ... What would go differently if we come back to a skipped
headline versus an errored headline?" That question forced tracing the actual mechanism rather than reasoning
from the shared "terminal, non-ok status" label: `error` is written per-headline, only after a real timed
attempt fails; `skipped` is written to every pending headline in one synchronous batch, before any network
call, purely as a function of whether `OPENAI_API_KEY` is currently set. The right rule turned out to be gated
on that live config state, not on the status value at all.

**Implication for future teaching**: this user won't accept that two states are safe to handle identically just
because they look structurally alike (both "not ok," both excluded from the same WHERE clause) — expect a
"what's actually different about how these two get set" question whenever a fix treats several statuses/flags
as a group. Present the underlying write path for each state up front next time, rather than waiting to be
asked. Related instinct, different angle, to [[0007-specs-are-behavior-adrs-are-architecture]] (won't accept a
document serving two purposes) and [[0009-cross-feature-primitive-recognition]] (looks for the structural
principle rather than the surface instance) — here the same instinct runs in the opposite direction: refusing
a superficial shared structure until the underlying mechanism is actually shown to match.
