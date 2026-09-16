# Insisted on isolating and fully re-verifying a risky refactor before any feature work was built on it

Planning lesson 20's grouping tests surfaced a real DI gap: Milvus calls reached a global client internally,
unlike every other dependency in `providers.py`. The user's exact instruction once this was agreed: "execute
the refactor then test it. wait to execute the rest." Not "do the refactor as part of the lesson" — a
deliberate, separate first step, with its own verification gate before the actual test-writing work began.

The verification bar set was real, not token: not just the existing `pytest` suite, but re-running all three
of lesson 19's own live-verification scripts against the real running stack (the deterministic 4-scenario
test, the 20-iteration late-match test, the 250-headline MSFT scale test), confirming byte-for-byte identical
behavior before treating the refactor as safe to build on. This caught a second, unplanned gap
(`fetch_and_persist_headlines` itself also needed the same injectable parameter, one level up from
`_assign_stories`) — found only because the isolation step forced a real re-verification pass, not a glance
at green tests.

**Implication for future teaching/practice**: when a plan combines a foundational/risky change with feature
work that depends on it, default to sequencing them as two explicit phases — refactor, verify against both
the test suite and any live checks, confirm, *then* build the feature — rather than bundling them into one
pass. This user will ask for that separation explicitly if it isn't offered, and the isolation step itself has
already once surfaced a bug the bundled version would have hidden.
