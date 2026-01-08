#!/bin/bash
# Run UI tests for Raspberry Pi Camera Control

set -e

echo "🧪 Raspberry Pi Camera Control - UI Test Suite"
echo "=============================================="
echo ""

# Check if in tests directory
if [ ! -f "conftest.py" ]; then
    if [ -d "tests" ]; then
        cd tests
    else
        echo "❌ Error: Run this script from the project root or tests directory"
        exit 1
    fi
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
if [ ! -f "venv/.installed" ]; then
    echo "📦 Installing test dependencies..."
    pip install -q --upgrade pip
    pip install -q -r requirements.txt
    
    echo "🌐 Installing Playwright browsers..."
    playwright install chromium
    
    touch venv/.installed
    echo "✅ Dependencies installed"
    echo ""
fi

# Get Pi IP address
PI_IP="${PI_IP:-192.168.0.169}"
BASE_URL="http://${PI_IP}:5000"

echo "🎯 Target: $BASE_URL"
echo ""

# Check if camera service is running
echo "🔍 Checking if camera service is reachable..."
if ! curl -s --connect-timeout 5 "$BASE_URL" > /dev/null; then
    echo "⚠️  Warning: Cannot reach $BASE_URL"
    echo "   Make sure the camera control service is running on the Pi"
    echo ""
fi

# Parse command line arguments
HEADED=""
MARKERS=""
VERBOSE="-v"
HTML_REPORT="--html=test-report.html --self-contained-html"

while [[ $# -gt 0 ]]; do
    case $1 in
        --headed)
            HEADED="--headed"
            echo "🖥️  Running in headed mode (browser window visible)"
            shift
            ;;
        --quick)
            MARKERS='-m "not slow"'
            echo "⚡ Running quick tests only (skipping slow tests)"
            shift
            ;;
        --slow)
            MARKERS='-m "slow"'
            echo "🐌 Running slow tests only"
            shift
            ;;
        --no-report)
            HTML_REPORT=""
            shift
            ;;
        -v|-vv)
            VERBOSE="$1"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--headed] [--quick] [--slow] [--no-report] [-v|-vv]"
            exit 1
            ;;
    esac
done

echo ""
echo "🚀 Running tests..."
echo ""

# Run pytest with Playwright
eval "pytest $VERBOSE \
    --base-url='$BASE_URL' \
    $HEADED \
    $MARKERS \
    $HTML_REPORT \
    test_ui.py"

TEST_EXIT_CODE=$?

echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✅ All tests passed!"
else
    echo "❌ Some tests failed (exit code: $TEST_EXIT_CODE)"
fi

if [ -n "$HTML_REPORT" ] && [ -f "test-report.html" ]; then
    echo ""
    echo "📊 HTML report generated: test-report.html"
fi

exit $TEST_EXIT_CODE
