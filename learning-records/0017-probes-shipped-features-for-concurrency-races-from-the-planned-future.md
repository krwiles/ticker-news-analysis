# Probed a shipped feature for concurrent-request races, unprompted, reasoning from the planned architecture

With no bug report and nothing failing, the user asked whether the existing fetch logic would survive two
requests for the same ticker arriving before the first finished: "would this cause race conditions? would the
second request just overwrite the first? would there be issues? can we implement a system that allows only one
fetch to a company at a time? like a semaphore for company lookups?" Asked directly why, they named the road
ahead rather than a present problem: "I am thinking ahead about a multi-user project with user accounts and
potentially multiple people fetching for tickers as well as automatic ticker fetching being done in the
background."

Two things are worth separating. The **semaphore** was the right family of tool — a per-key guard, an idea the
user already had from lesson 26's `Semaphore(20)` — but a lock keyed by ticker *serializes*: the second request
waits and then repeats the whole fetch. The distinction between serializing and **sharing** one in-flight run
(single-flight) wasn't one the user had raised; the assistant supplied it, and offered "join the in-flight
fetch" versus "wait your turn and refetch" as the choice. The user picked joining without hesitation, and their
reason was the future callers, not the current one: another user, or a background job, should share a run that's
already happening rather than repeat it.

The question also turned out to be well-placed empirically. Reproduced live before any fix, two simultaneous
searches hit a real `UniqueViolationError` on the first-ever lookup of a ticker, and two overlapping sentiment
jobs double-counted every score into the Story aggregates (224 recorded against 112 real; see lesson 31). Notably
this happened on the project's **single** worker process — the overlap comes from async jobs interleaving, not
from multiple workers, which is the model record 0015 corrected earlier. Nobody needed a second worker for the
race to be real.

**Implication for future teaching**: this user stress-tests shipped features against the *planned* architecture,
not just the current one, and does it by asking "what happens when N callers hit this?" — so concurrency and
multi-user lessons can start from that question rather than from a definition of a race condition. When they
propose a mechanism, expect it to be a sound instinct that may still miss a design distinction (serialize vs.
share); the useful teaching move is to present the trade-off as a choice and let them decide, as happened here.
The future background refresher should reuse `jobs.py`'s per-ticker job IDs rather than re-deriving coordination.
