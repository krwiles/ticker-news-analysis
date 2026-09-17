# Evaluated OpenAI's Batch API as a genuine async job system against a real latency requirement, correctly rejected it

Building on [[0008-latency-budget-instinct-batch-or-decouple]]'s already-recorded batch-vs-decouple instinct,
this went a level further: rather than just asking whether batching multiple items into one call would help
(0008's own case), the user asked whether OpenAI has "a system for parallelization of large amounts of
requests" specifically — recognizing that a genuinely different kind of system, not just a bigger request,
might be the real answer. Presented with OpenAI's real Batch API (a 50% cost discount, its own separate
higher rate-limit pool, but only a 24-hour completion guarantee, never a fixed SLA), the user weighed it
directly against their own explicitly-stated requirement ("I do not want to be waiting more than a minute")
and correctly rejected it — recognizing that a system's *typical* fast turnaround doesn't substitute for a
missing guarantee once a hard constraint is actually in play. Chose the standard synchronous API fired
concurrently instead, verified live to comfortably meet the real requirement (20 concurrent calls in ~6.6s).

**Implication for future teaching**: this user can evaluate a genuine async job/queue system's real trade-offs
(cost/throughput vs. latency guarantee) against a concrete requirement, not just recognize "batching helps."
Future lessons on ARQ's own job model, or any other async-processing system, can assume this trade-off
vocabulary (SLA vs. typical performance, throughput vs. latency) is already understood, not something to
reintroduce from scratch.
