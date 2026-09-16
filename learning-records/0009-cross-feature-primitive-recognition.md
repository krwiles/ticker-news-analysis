# Recognized a shared "new-row, compute-once" primitive across two features before either needed it built

While discussing embedding costs, the user asked whether `fetch_and_persist_headlines` distinguishes genuinely
new headlines from ones already known, then immediately generalized past the embedding case: "This question is
also going to be relevant once we start doing sentiment analysis because we are going to be storing the results
from the sentiments and purposefully not reevaluating them after doing it once." Sentiment analysis isn't
speced yet — the user connected it anyway, recognizing that both features need the identical checkpoint (has
this row been processed before, if so never touch it again), not two separate ad-hoc solutions.

Same instinct already on record in [[0006-derive-dont-store-normalization-instinct]] (deriving vs. storing a
fact) and [[0007-specs-are-behavior-adrs-are-architecture]] (recognizing a document doing two jobs at once) —
this user consistently looks past the immediate instance for the structural principle underneath it, across
schema, docs, and now cross-feature data-processing pipelines.

**Implication for future teaching**: when planning any future feature that processes headlines repeatedly
(sentiment analysis or beyond), check first whether it can reuse the new-row-detection mechanism lesson 19
introduces, and present it that way — as reuse, not a fresh design question. This user will likely notice, and
ask, if a shape of problem already solved once gets re-litigated as if it were new.
