#!/bin/bash
# Tests the full stack is wired correctly
set -e

echo "=== Testing Vyrex API ==="
curl -s --unix-socket /run/vyrex/api.sock \
  http://localhost/v1/models | jq .

echo "=== Testing Prax Agent ==="
node /opt/kryos/agent/dist/index.js "take a screenshot and tell me what you see"

echo "=== Testing Input Control ==="
ydotool mousemove -x 500 -y 500
echo "Mouse moved to 500,500"

echo "=== Testing Screen Capture ==="
grim /tmp/test-capture.png && echo "Screenshot saved"

echo "=== All integration tests passed ==="
