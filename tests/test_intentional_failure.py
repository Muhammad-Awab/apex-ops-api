"""Intentional failure required by the assessment.

This test is deliberately wrong. It is skipped by default and switched on with
RUN_INTENTIONAL_FAILURE=1 (locally: ``scripts/ci_local.sh --with-intentional-failure``;
in GitHub Actions: run the workflow manually with ``demo_intentional_failure: true``).
When enabled it must turn the test job red and the build/scan/release jobs must
be skipped. That shows a failing test stops a release.
"""

import os

import pytest


@pytest.mark.skipif(
    os.getenv("RUN_INTENTIONAL_FAILURE") != "1",
    reason="intentional failure demo disabled (set RUN_INTENTIONAL_FAILURE=1)",
)
def test_intentional_failure_blocks_release(client):
    # Simulates a regression: a contract change nobody updated the API for.
    assert client.get("/healthz").json() == {"status": "healthy"}
