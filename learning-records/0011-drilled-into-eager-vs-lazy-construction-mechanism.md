# Drilled past "make it lazy" to the exact mechanism separating SQLAlchemy's engine from pymilvus's client

After the Milvus-client-eager-connection bug was fixed by making `get_milvus_client()` a lazy singleton, the
user didn't accept the fix at face value. First question: "explain why we're using a global variable with the
Milvus client. Why are we treating this differently than with the database? Is that because the database
comes with its own session maker?" — a real hypothesis, offered for confirmation or correction, not just "why
does this work." Follow-up, after the real answer (SQLAlchemy's `create_async_engine` does no I/O at
construction; pymilvus's `MilvusClient.__init__` does): "so you're saying that as soon as a Milvus client is
declared, it tries to open a connection and that in turn can fail if the containers are not all up and
running?" — checking the generalized claim against the specific failure actually observed, and getting the
more precise version back (two distinct failure modes: hostname never resolves outside the docker network at
all, vs. the container simply not being ready yet — only the second is a timing problem).

Separately, the fix itself needed a second, non-obvious mechanism to explain: why `session_factory=async_session_factory`
could safely be a plain default parameter while the Milvus client couldn't use the same shape
(`milvus=get_milvus_client()` as a default). The reason is Python's own default-argument evaluation timing
(once, at `def` time — i.e. import time), not a stylistic choice — the user's question sequence is what made
surfacing this specific gotcha necessary rather than glossing over it.

**Implication for future teaching**: this user wants the actual causal mechanism, not just "this is now
fixed" — when introducing a fix, be ready for a follow-up that checks the generalized explanation against the
specific symptom, and don't round off a real distinction (e.g. "can't resolve" vs. "not ready yet") into one
vague cause. Also worth flagging proactively next time: Python's default-argument evaluation timing is a
recurring source of exactly this class of bug, and is likely already understood at some level given how
readily he traced it here.
