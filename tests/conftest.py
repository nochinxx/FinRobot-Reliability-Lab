"""
pytest configuration for FinRobot Reliability Lab.

Sets DEV_MODE=1 by default so all tests run completely offline (no FMP or SEC EDGAR calls).
Live tests must be tagged @pytest.mark.live and are skipped unless --live flag is passed.

Usage:
  conda run -n agent python -m pytest tests/               # offline (default)
  conda run -n agent python -m pytest tests/ --live        # include live API tests
"""
import os
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--live", action="store_true", default=False,
        help="Run live API tests (requires FMP key and internet access)"
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "live: marks tests that make real API calls (skip with default run)")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--live"):
        skip_live = pytest.mark.skip(reason="Live API test — run with --live flag to enable")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)


@pytest.fixture(autouse=True)
def enforce_offline(request):
    """Force DEV_MODE=1 for all tests unless the test is marked @pytest.mark.live."""
    if "live" in request.keywords:
        yield
        return
    original = os.environ.get("DEV_MODE")
    os.environ["DEV_MODE"] = "1"
    yield
    if original is None:
        os.environ.pop("DEV_MODE", None)
    else:
        os.environ["DEV_MODE"] = original
