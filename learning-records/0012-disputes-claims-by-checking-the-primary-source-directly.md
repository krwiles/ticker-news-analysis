# When an explanation didn't match lived experience, demanded a direct check against the real upstream source rather than a better explanation

Told the AAPL "Today" bucket was empty because nothing had been published yet (verified against our own
database), the user didn't accept it: "wait, there is absolutely news on aapl now. can you curl the finhub
call directly to verify." Not a request for a clearer explanation of the existing evidence — a demand to
re-derive the evidence itself, one layer further upstream, from Finnhub's real API rather than our own stored
copy of it. The direct curl confirmed Finnhub's own feed genuinely had nothing newer for AAPL at that moment,
closing the question with primary-source evidence rather than a second-hand explanation of secondary data.

Followed immediately by a second instinct: rather than accept the negative result as final, pick a *different*
ticker (MSFT) more likely to have a positive case, and prove the pipeline works end-to-end when the data
actually supports it — not just explain why it doesn't fire in this one instance.

**Implication for future teaching/practice**: when a live observation seems to contradict an explanation,
expect a request to verify against the actual upstream source (the real third-party API, not our cache of
it), not just a restatement of the reasoning. Already-verified data from our own database is not treated as
equivalent to independently checking the primary source when the two could in principle diverge. Related:
[[0010-isolate-and-reverify-risky-refactors-before-building-on-them]] — same "prove it against reality, not
just against our own prior work" instinct, applied here to a live data claim instead of a code refactor.
