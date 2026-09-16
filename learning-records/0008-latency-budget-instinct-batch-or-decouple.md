# Diagnosed a per-item latency budget problem unprompted, and generated both standard fixes for it

Right after lesson 18's live verification measured ~2.23s for one embedding call, the user did the
multiplication themselves, unprompted, before it was raised as a risk: "It is clear that if one heading takes
two seconds that's gonna be way too long for a typical news fetch which can get tens of headings." They then
proposed both of the two standard resolutions for exactly this class of problem — amortize the cost (batch
the requests into one call) or decouple it (stream raw results to the UI immediately, process embeddings/
grouping in the background, push updates staggered) — not just one, and not a vague "make it faster."

Batching turned out to be sufficient (live-verified: 10 headlines batched took 1.13s, flat against batch size,
vs. an ~18s naive-serial estimate) and was the one implemented; the decoupled/progressive-UI pattern was set
aside as a validated fallback, not built.

**Implication for future teaching**: this user reliably checks whether a per-item external-call cost will
survive multiplication against realistic volume, and reaches for the correct resolution *shape* (batch vs.
decouple) without being taught the pattern first. Future lessons touching any per-item external API call inside
a bounded-timeout job don't need this trade-off re-explained from scratch — lead with "does this batch?" and
treat the progressive/async-UI pattern as an already-known fallback, not a new concept.
