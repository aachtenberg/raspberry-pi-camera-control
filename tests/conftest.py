"""
Pytest configuration for browser UI tests
"""
import pytest


def pytest_addoption(parser):
    """Add custom command-line options"""
    parser.addoption(
        "--headed",
        action="store_true",
        default=False,
        help="Run browser tests in headed mode (show browser window)"
    )


@pytest.fixture(scope="session")
def browser_type_launch_args(request):
    """Configure browser launch arguments"""
    headed = request.config.getoption("--headed")
    return {
        "headless": not headed,
        "slow_mo": 100 if headed else 0,  # Slow down actions in headed mode
    }
