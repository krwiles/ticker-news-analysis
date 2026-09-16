import logging

import structlog


def configure_logging() -> None:
    """Structured JSON logging, shared by every mode (ui/api/worker)."""
    # Hand the record to structlog's own renderer as-is -- no stdlib
    # formatting of its own, so it doesn't fight with the JSON below.
    logging.basicConfig(format="%(message)s", level=logging.INFO)
    structlog.configure(
        # Runs left to right -- every call becomes one JSON line with a timestamp + level.
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),  # add an ISO-8601 `timestamp` field
            structlog.processors.add_log_level,  # add a `level` field (info/warning/...)
            structlog.processors.JSONRenderer(),  # serialize the whole event dict to one JSON line
        ],
        # Filters out any call below INFO before it reaches the processors
        # above -- cheaper than logging then discarding.
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        # Plain print() to stdout -- the container runtime collects it from there.
        logger_factory=structlog.PrintLoggerFactory(),
    )
