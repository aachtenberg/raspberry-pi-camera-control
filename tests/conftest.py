"""
Pytest configuration for browser UI tests
"""
import pytest


def pytest_addoption(parser):
    """Add custom command-line options"""
    parser.addoption(
        "--base-url",
        action="store",
        default="http://192.168.0.169:5000",
        help="Base URL for the camera control interface"
    )
    parser.addoption(
        "--headed",
        action="store_true",
        default=False,
        help="Run browser tests in headed mode (show browser window)"
    )


@pytest.fixture(scope="session")
def base_url(request):
    """Get base URL from command line or use default"""
    return request.config.getoption("--base-url")


@pytest.fixture(scope="session")
def browser_context_args(request):
    """Configure browser context"""
    headed = request.config.getoption("--headed")
    return {
        "viewport": {"width": 1920, "height": 1080},
        "ignore_https_errors": True,
    }


@pytest.fixture(scope="session")
def browser_type_launch_args(request):
    """Configure browser launch arguments"""
    headed = request.config.getoption("--headed")
    return {
        "headless": not headed,
        "slow_mo": 100 if headed else 0,  # Slow down actions in headed mode
    }
