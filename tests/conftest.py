"""
Pytest configuration for browser UI tests
Uses pytest-playwright's built-in fixtures and options
"""
import pytest
from pathlib import Path

# pytest-playwright provides:
# - page fixture: A browser page instance for each test
# - browser fixture: A browser instance
# - context fixture: A browser context for isolation
# - browser_type_launch_args fixture: For customizing browser launch
# - base_url fixture: From --base-url command line argument
# - headed mode: From --headed command line argument

# You can customize Playwright behavior here if needed
def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "ui: marks tests as UI tests"
    )

# Optional: Add custom fixture for handling timeouts
@pytest.fixture(scope="session")
def browser_launch_args():
    """Customize browser launch arguments"""
    return {
        "args": [
            "--disable-blink-features=AutomationControlled",  # Hide automation detection
        ],
        "headless": True,  # Set to False for --headed mode
    }

# Optional: Slow down browser actions for debugging (disabled by default)
@pytest.fixture
def slow_mo():
    """Return slow motion delay in milliseconds (0 = disabled)"""
    return 0  # Set to 100 or higher for slow motion debugging
