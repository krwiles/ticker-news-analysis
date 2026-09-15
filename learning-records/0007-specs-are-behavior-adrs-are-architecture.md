# Diagnosed specs mixing behavior with implementation as a root cause, not a one-off friction point

After spec 0002 was finalized via a full grilling round, and separately after confirming a real implementation
deviation from it (`headlines.story_id` nullable rather than the spec's stated `NOT NULL`), the user paused and
named the actual problem rather than letting it slide as case-by-case friction: "a specification should not
have any details of implementation if it is written well, it should only have desired behavior specified.
Perhaps we should modify our spec before this gets confusing?"

This wasn't prompted — the assistant had been treating the nullable-vs-`NOT NULL` tension as a normal spec-
vs-reality gap to work around, not as a symptom of specs doing two jobs at once. The user correctly diagnosed
that this project's specs (including the already-shipped spec 0001, though left alone since it wasn't causing
active friction) had always blended desired-behavior with implementation prose, and that this only became a
real liability once a spec started being actively revised *during* implementation rather than written once and
left alone. The proposed fix was structural, not cosmetic: route implementation-level decisions into ADRs (a
mechanism the project already had, per ADR 0001–0005, but was under-using for spec 0002), and keep specs to
pure desired-behavior. Confirmed via `/mattpocock-skills:ask-matt` that `/domain-modeling` was the right tool
for the ADR half specifically, then executed: spec 0002 trimmed from 117 to 81 lines, four new ADRs (0006–0009)
written, and a durable standing convention adopted for future specs, not just a one-off cleanup of this one.

**Implication for future teaching/practice**: this user thinks about documentation *architecture*, not just
code architecture — recognizing when one document type is being asked to serve two purposes and that this
compounds into real confusion over time, not just noticing an immediate inconsistency. Future spec-writing
should default to behavior-only without re-litigating it each session; if a spec conversation starts
accumulating real implementation reasoning, route it to a new ADR immediately (this user's own established
preference), rather than waiting for a contradiction to force the question later.
