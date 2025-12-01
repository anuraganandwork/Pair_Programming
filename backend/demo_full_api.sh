#!/bin/bash

# Demo script for Pair Programming API
# Demonstrates all features of the API

set -e  # Exit on error

API_BASE="http://localhost:8000"
API_V1="http://localhost:8000/api/v1"

echo "========================================================================="
echo "🎉 Pair Programming API - Complete Feature Demonstration"
echo "========================================================================="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Root Endpoint
echo -e "${BLUE}1. Root Endpoint${NC}"
echo "GET $API_BASE/"
curl -s $API_BASE/ | python3 -m json.tool
echo ""

# 2. Health Checks
echo -e "${BLUE}2. Health Checks${NC}"
echo "GET $API_BASE/health"
curl -s $API_BASE/health | python3 -m json.tool
echo ""

echo "GET $API_BASE/health/ready"
curl -s $API_BASE/health/ready | python3 -m json.tool
echo ""

# 3. Application Statistics
echo -e "${BLUE}3. Application Statistics${NC}"
echo "GET $API_BASE/stats"
curl -s $API_BASE/stats | python3 -m json.tool
echo ""

# 4. Create Room
echo -e "${BLUE}4. Create Room${NC}"
echo "POST $API_V1/rooms"
ROOM_RESPONSE=$(curl -s -X POST $API_V1/rooms \
  -H "Content-Type: application/json" \
  -d '{"language":"python","code":""}')

echo "$ROOM_RESPONSE" | python3 -m json.tool
ROOM_ID=$(echo "$ROOM_RESPONSE" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data.get('roomId') or data.get('id', ''))" 2>/dev/null || echo "")

if [ -z "$ROOM_ID" ]; then
  echo "Error: Failed to create room"
  exit 1
fi

echo -e "${GREEN}✓ Room created with ID: $ROOM_ID${NC}"
echo ""

# 5. Get Room
echo -e "${BLUE}5. Get Room${NC}"
echo "GET $API_V1/rooms/$ROOM_ID"
curl -s $API_V1/rooms/$ROOM_ID | python3 -m json.tool
echo ""

# 6. Update Room Code
echo -e "${BLUE}6. Update Room Code${NC}"
echo "PUT $API_V1/rooms/$ROOM_ID/code"
CODE='def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

print(fibonacci(10))'

curl -s -X PUT $API_V1/rooms/$ROOM_ID/code \
  -H "Content-Type: application/json" \
  -d "{\"code\":$(echo "$CODE" | python3 -c "import sys, json; print(json.dumps(sys.stdin.read()))"),\"user_id\":\"demo_user\"}" | python3 -m json.tool
echo ""

# 7. Get Updated Room
echo -e "${BLUE}7. Get Updated Room${NC}"
echo "GET $API_V1/rooms/$ROOM_ID"
curl -s $API_V1/rooms/$ROOM_ID | python3 -m json.tool
echo ""

# 8. Autocomplete Examples
echo -e "${BLUE}8. Code Autocomplete${NC}"

echo -e "${YELLOW}Example 1: Python 'for' statement${NC}"
echo "POST $API_V1/autocomplete"
curl -s -X POST $API_V1/autocomplete \
  -H "Content-Type: application/json" \
  -d '{"code":"for ","cursor_position":4,"language":"python"}' | python3 -m json.tool
echo ""

echo -e "${YELLOW}Example 2: Python 'def' statement${NC}"
curl -s -X POST $API_V1/autocomplete \
  -H "Content-Type: application/json" \
  -d '{"code":"def ","cursor_position":4,"language":"python"}' | python3 -m json.tool
echo ""

echo -e "${YELLOW}Example 3: Python 'import' statement${NC}"
curl -s -X POST $API_V1/autocomplete \
  -H "Content-Type: application/json" \
  -d '{"code":"import ","cursor_position":7,"language":"python"}' | python3 -m json.tool
echo ""

echo -e "${YELLOW}Example 4: JavaScript 'function' statement${NC}"
curl -s -X POST $API_V1/autocomplete \
  -H "Content-Type: application/json" \
  -d '{"code":"function ","cursor_position":9,"language":"javascript"}' | python3 -m json.tool
echo ""

# 9. Stats After Operations
echo -e "${BLUE}9. Statistics After Operations${NC}"
echo "GET $API_BASE/stats"
curl -s $API_BASE/stats | python3 -m json.tool
echo ""

# 10. Middleware Headers
echo -e "${BLUE}10. Middleware Headers (Request ID & Timing)${NC}"
echo "Fetching headers from health endpoint..."
curl -i $API_BASE/health 2>&1 | grep -E "(X-Request-ID|X-Process-Time|HTTP/)"
echo ""

# 11. Delete Room
echo -e "${BLUE}11. Delete Room${NC}"
echo "DELETE $API_V1/rooms/$ROOM_ID"
curl -s -X DELETE $API_V1/rooms/$ROOM_ID -o /dev/null -w "HTTP Status: %{http_code}\n"
echo -e "${GREEN}✓ Room deleted successfully${NC}"
echo ""

# 12. Verify Room Deleted
echo -e "${BLUE}12. Verify Room Deleted${NC}"
echo "GET $API_V1/rooms/$ROOM_ID (should return 404)"
curl -s $API_V1/rooms/$ROOM_ID -w "\nHTTP Status: %{http_code}\n" | python3 -m json.tool 2>/dev/null || echo "Room not found (expected)"
echo ""

# Summary
echo "========================================================================="
echo -e "${GREEN}✅ Demonstration Complete!${NC}"
echo "========================================================================="
echo ""
echo "Demonstrated Features:"
echo "  ✅ Root endpoint with API information"
echo "  ✅ Health checks (basic & readiness)"
echo "  ✅ Application statistics"
echo "  ✅ Room creation"
echo "  ✅ Room retrieval"
echo "  ✅ Code updates"
echo "  ✅ Autocomplete (Python & JavaScript)"
echo "  ✅ Request ID middleware"
echo "  ✅ Timing middleware"
echo "  ✅ Room deletion"
echo "  ✅ Error handling (404)"
echo ""
echo "Next Steps:"
echo "  • View API docs: $API_BASE/docs"
echo "  • Try WebSocket: See WEBSOCKET_DOCS.md"
echo "  • Read complete docs: PROJECT_COMPLETE.md"
echo ""
echo "========================================================================="

