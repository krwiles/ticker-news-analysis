"""configure_logging()'s guard against credentials reaching the logs -- see docs/plans/0040-*.md."""

import logging

from ticker_backend.logging import configure_logging


def test_httpx_request_urls_are_not_logged_at_info():
    # Arrange: the production situation -- root at INFO (pytest's own setup would otherwise mask the bug).
    root = logging.getLogger()
    httpx_logger = logging.getLogger("httpx")
    saved = (root.level, httpx_logger.level)
    root.setLevel(logging.INFO)
    httpx_logger.setLevel(logging.NOTSET)
    try:
        # Act.
        configure_logging()

        # Assert: INFO is filtered out, so the request-URL line httpx emits per call never prints.
        assert not httpx_logger.isEnabledFor(logging.INFO)
    finally:
        # Restore, so this test can't change logging behavior for the rest of the suite.
        root.setLevel(saved[0])
        httpx_logger.setLevel(saved[1])
