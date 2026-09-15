import logging

import structlog


def configure_logging() -> None:
    """Structured JSON logging, shared by every mode (ui/api/worker)."""
    # Hand the record to structlog's own renderer as-is -- no stdlib
    # formatting of its own, so it doesn't fight with the JSON below.
    logging.basicConfig(format="%(message)s", level=logging.INFO)
    structlog.configure(
        # Each log call flows through these in order, left to right --
        # every call ends up as one line of JSON with a timestamp and a
        # level, regardless of which module logged it.
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),  # add an ISO-8601 `timestamp` field
            structlog.processors.add_log_level,  # add a `level` field (info/warning/...)
            structlog.processors.JSONRenderer(),  # serialize the whole event dict to one JSON line
        ],
        # Filters out any call below INFO before it reaches the processors
        # above -- cheaper than logging then discarding.
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        # Plain print() to stdout -- correct for containers, where the
        # runtime (Docker/Kubernetes) is what collects stdout, not this
        # process writing to a file or a logging service directly.
        logger_factory=structlog.PrintLoggerFactory(),
    )
