#!/bin/bash

# Test runner script for Pair Programming API
# Runs all tests with coverage and generates reports

set -e  # Exit on error

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "========================================================================="
echo -e "${BLUE}🧪 Pair Programming API - Test Suite${NC}"
echo "========================================================================="
echo ""

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# ============================================================================
# SETUP
# ============================================================================

echo -e "${BLUE}📋 Setup${NC}"
echo "---"

# Check if virtual environment exists
if [ ! -d "venv" ] && [ ! -d ".venv" ]; then
    echo -e "${YELLOW}⚠️  No virtual environment found. Creating one...${NC}"
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    # Activate virtual environment
    if [ -d "venv" ]; then
        source venv/bin/activate
    else
        source .venv/bin/activate
    fi
fi

echo -e "${GREEN}✓ Virtual environment activated${NC}"

# Check if dependencies are installed
if ! python -c "import pytest" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Installing test dependencies...${NC}"
    pip install -r requirements.txt
fi

echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# ============================================================================
# DATABASE SETUP
# ============================================================================

echo -e "${BLUE}🗄️  Database Setup${NC}"
echo "---"

# Set test database URL
export TEST_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/pairprogramming_test"
export DATABASE_URL="$TEST_DATABASE_URL"
export ENVIRONMENT="test"

echo "Test database: pairprogramming_test"

# Check if PostgreSQL is running
if ! pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
    echo -e "${RED}✗ PostgreSQL is not running!${NC}"
    echo "Please start PostgreSQL:"
    echo "  docker start fastapi-postgres"
    echo "  OR"
    echo "  brew services start postgresql"
    exit 1
fi

echo -e "${GREEN}✓ PostgreSQL is running${NC}"

# Create test database if it doesn't exist
psql -h localhost -U postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'pairprogramming_test'" 2>/dev/null | grep -q 1 || \
    psql -h localhost -U postgres -c "CREATE DATABASE pairprogramming_test" 2>/dev/null

echo -e "${GREEN}✓ Test database ready${NC}"
echo ""

# ============================================================================
# RUN TESTS
# ============================================================================

echo -e "${BLUE}🧪 Running Tests${NC}"
echo "---"
echo ""

# Parse command line arguments
TEST_ARGS=""
MARKER=""
VERBOSE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -u|--unit)
            MARKER="-m unit"
            echo "Running unit tests only"
            shift
            ;;
        -i|--integration)
            MARKER="-m integration"
            echo "Running integration tests only"
            shift
            ;;
        -e|--e2e)
            MARKER="-m e2e"
            echo "Running end-to-end tests only"
            shift
            ;;
        -w|--websocket)
            MARKER="-m websocket"
            echo "Running WebSocket tests only"
            shift
            ;;
        -s|--slow)
            MARKER="-m slow"
            echo "Running slow tests only"
            shift
            ;;
        -v|--verbose)
            VERBOSE="-vv"
            shift
            ;;
        --no-cov)
            export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
            TEST_ARGS="--no-cov"
            shift
            ;;
        *)
            TEST_ARGS="$TEST_ARGS $1"
            shift
            ;;
    esac
done

# Run pytest
if pytest $MARKER $VERBOSE $TEST_ARGS; then
    TEST_EXIT_CODE=0
    echo ""
    echo -e "${GREEN}=========================================================================${NC}"
    echo -e "${GREEN}✅ All tests passed!${NC}"
    echo -e "${GREEN}=========================================================================${NC}"
else
    TEST_EXIT_CODE=$?
    echo ""
    echo -e "${RED}=========================================================================${NC}"
    echo -e "${RED}❌ Some tests failed!${NC}"
    echo -e "${RED}=========================================================================${NC}"
fi

echo ""

# ============================================================================
# COVERAGE REPORT
# ============================================================================

if [ -z "$PYTEST_DISABLE_PLUGIN_AUTOLOAD" ]; then
    echo -e "${BLUE}📊 Coverage Report${NC}"
    echo "---"
    
    # Check if coverage data exists
    if [ -f ".coverage" ]; then
        # Get coverage percentage
        COVERAGE=$(coverage report | tail -1 | awk '{print $NF}' | sed 's/%//')
        
        echo ""
        if (( $(echo "$COVERAGE >= 80" | bc -l) )); then
            echo -e "${GREEN}✓ Coverage: ${COVERAGE}% (meets 80% threshold)${NC}"
        else
            echo -e "${YELLOW}⚠️  Coverage: ${COVERAGE}% (below 80% threshold)${NC}"
        fi
        
        # Generate HTML report
        echo ""
        echo "HTML coverage report generated in: htmlcov/index.html"
        echo "Open with: open htmlcov/index.html"
        
        # Generate XML report for CI/CD
        echo "XML coverage report generated: coverage.xml"
    fi
fi

echo ""

# ============================================================================
# SUMMARY
# ============================================================================

echo -e "${BLUE}📋 Test Summary${NC}"
echo "---"

# Count test files
TEST_FILES=$(find tests -name "test_*.py" | wc -l | tr -d ' ')
echo "Test files: $TEST_FILES"

# Count total tests (approximate)
if [ -f ".pytest_cache/v/cache/nodeids" ]; then
    TOTAL_TESTS=$(wc -l < .pytest_cache/v/cache/nodeids | tr -d ' ')
    echo "Total tests: $TOTAL_TESTS"
fi

echo ""
echo "Test Categories:"
echo "  • Unit tests:        pytest -m unit"
echo "  • Integration tests: pytest -m integration"
echo "  • E2E tests:         pytest -m e2e"
echo "  • WebSocket tests:   pytest -m websocket"
echo "  • All tests:         pytest"
echo ""
echo "Coverage:"
echo "  • HTML report:  htmlcov/index.html"
echo "  • XML report:   coverage.xml"
echo "  • Terminal:     coverage report"
echo ""

# ============================================================================
# EXIT
# ============================================================================

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}=========================================================================${NC}"
    echo -e "${GREEN}🎉 Test run complete! All tests passed.${NC}"
    echo -e "${GREEN}=========================================================================${NC}"
else
    echo -e "${RED}=========================================================================${NC}"
    echo -e "${RED}⚠️  Test run complete with failures. Please review the output above.${NC}"
    echo -e "${RED}=========================================================================${NC}"
fi

echo ""

exit $TEST_EXIT_CODE

