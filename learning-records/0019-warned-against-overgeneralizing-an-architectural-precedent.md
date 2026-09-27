# Explicitly warned against applying an existing architectural precedent to a domain it doesn't fit

Asked to pick the OAuth implementation approach, the assistant's first lean was Authlib vs. hand-rolled
`httpx` — framed against ADR 0010's standing project-wide preference for raw HTTP over SDKs. The user
rejected that framing before an answer was even given: "do some research to find out what people typically
do with google sign in. Do not let the other raw httpx usage in this project influence the decision because
this is a completely seperate system we are building for user sign-in now."

The distinction the user drew: ADR 0010 was decided for a specific reason (`httpx`-uniform mocking across
`test_providers.py`, a stack item named in `MISSION.md`) that has nothing to do with whether OAuth's
fiddlier, security-sensitive parts (ID-token signature verification against rotating public keys) are a good
candidate for hand-rolling. A precedent that fits one domain doesn't automatically transfer to a
superficially similar one just because both involve an HTTP call. Research, prompted this way, found the
user's instinct was right: Google's own docs recommend a client library specifically for this step, and
further digging corrected the assistant's own first answer again (Authlib's classic OAuth flow → Google
Identity Services, once it turned out this app's actual need — identity only, no Google API access — has a
simpler, Google-recommended path that classic OAuth over-serves).

**Implication for future teaching**: this is the same instinct as [[0007-specs-are-behavior-adrs-are-architecture]]
(a document/decision doing a job it wasn't built for) and [[0018-traced-skipped-and-error-write-mechanics]]
(won't accept two things are handled alike without checking why), but aimed at a new target: standing
architectural precedents themselves. Expect this user to name explicitly when an existing convention is being
reached for out of habit rather than because it actually fits the new decision — and to ask for real research
before accepting a recommendation, not just a reference to what this codebase already does elsewhere.
