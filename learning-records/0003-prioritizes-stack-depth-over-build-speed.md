# Consistently weights genuine stack-learning depth over the leanest build path

Twice now, when a leaner/faster implementation option was on the table, the user explicitly chose the option
that cost more (latency, complexity, time) specifically because it taught more of the actual stack: routing
the provider fetch through an ARQ job the user enqueues and awaits (ADR 0004) instead of a direct function call,
and building a real targeted test suite (ADR 0005) instead of continuing pure manual verification, both
justified explicitly by "I need to learn this" rather than by the feature's own requirements.

**Implication for future teaching and scope decisions**: when a build-speed-vs-learning-depth trade-off comes
up, default to surfacing the deeper/more-instructive option as a real candidate rather than pre-filtering it
out as "too much for a personal project" — this user has shown a repeated, explicit preference for depth here,
distinct from the general "keep it simple" instinct also expressed elsewhere for things like ticker validation
or Refresh throttling. The two aren't in tension: simplicity for genuinely unnecessary complexity, depth for
anything that's actually part of the stack being learned.
