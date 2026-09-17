# When re-examining an already-tuned parameter, explicitly ruled out anchoring the new experiment to the old value or findings

Spotting a real grouping split (two genuinely-same-event Stories that should have merged), the natural next
step would have been "lower the threshold until this one case passes." The user's actual instruction was the
opposite: "pull a larger real sample from multiple stocks... DO NOT use any current values for thresholds or
allow previous findings to influence this experiment. We are running a new test from scratch to determine a
threshold value using a larger sample size." A deliberate methodological choice: build the ground-truth
labels (which pairs should/shouldn't group) from reading real content only, blind to any similarity score or
the existing 0.75 cutoff, precisely so the experiment couldn't be unconsciously steered toward re-confirming
whatever number was already in place.

The result was more informative *because* of that discipline: the larger sample showed the two distributions
(same-event vs. different-event cosine scores) genuinely overlap, with no cosine value cleanly separating
them — and, independently, that the existing 0.75 already sits in the best available zero-false-positive gap
this new sample supports. Had the experiment been designed by tuning toward the one failing case, that overlap
and the specific new false-positive risk (a real, different pair that would have started incorrectly merging)
would likely have gone undetected.

**Implication for future teaching/practice**: when a proposed fix is "adjust a number until this one failure
goes away," expect a request to test against a fresh, independently-labeled sample instead — one built
without reference to the current value or any single failing case, so the result reflects the actual
underlying distribution rather than a fix narrowly tailored to one symptom. This is a general empirical-
methodology instinct (avoiding confirmation bias / anchoring in experiment design), applied here to embedding-
similarity threshold tuning specifically, worth flagging proactively next time a threshold, cutoff, or
tunable constant comes under question.
