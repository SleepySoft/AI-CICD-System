#!/usr/bin/env bash
# End-to-end persistence test for the tmux backend (runs in WSL/Linux).
set -u
cd "$HOME/atr-e2e"
PY=.venv/bin/python
export ATR_BASE_URL=http://127.0.0.1:18651
export ATR_PORT=18651
export ATR_DEFAULT_BACKEND=tmux
FAIL=0

step() { echo; echo "=== $1 ==="; }
check() { if [ $? -eq 0 ]; then echo "PASS: $1"; else echo "FAIL: $1"; FAIL=1; fi; }

step "0. deps"
$PY -c 'import fastapi, uvicorn, pyte, pydantic; print("deps ok")' || { echo "deps missing"; exit 1; }

step "1. start service (tmux backend)"
tmux kill-server 2>/dev/null
$PY scripts/terminal_runtime_service.py > /tmp/atr-svc1.log 2>&1 &
SVC1=$!
sleep 3
curl -s http://127.0.0.1:18651/health
check "health"

step "2. create tmux session (idempotent)"
$PY scripts/terminal_runtime_client.py create --session-id e2e --command bash --backend tmux --ensure | head -5
check "create"
# ensure again -> created:false, no error
$PY scripts/terminal_runtime_client.py create --session-id e2e --command bash --backend tmux --ensure | grep -q '"created": false'
check "ensure idempotent"

step "3. act + observe"
$PY scripts/terminal_runtime_client.py act --session-id e2e --type submit --text 'echo E2E_MARKER_123' > /dev/null
check "act"
$PY scripts/terminal_runtime_client.py wait --session-id e2e --until screen_stable --timeout-ms 8000 --stable-ms 800 > /dev/null
curl -s http://127.0.0.1:18651/sessions/e2e/screenshot | grep -q E2E_MARKER_123
check "marker visible on screen"
curl -s http://127.0.0.1:18651/sessions/e2e/observe | grep -q '"backend":\s*"tmux"'
check "observe shows tmux backend"

step "4. simulate service crash (kill -9)"
kill -9 $SVC1
sleep 1
tmux has-session -t atr-e2e 2>/dev/null
check "tmux session survives service crash"

step "5. restart service -> auto adopt"
$PY scripts/terminal_runtime_service.py > /tmp/atr-svc2.log 2>&1 &
SVC2=$!
sleep 3
grep -q "adopted" /tmp/atr-svc2.log
check "startup log reports adoption"
curl -s http://127.0.0.1:18651/sessions | grep -q '"session_id":\s*"e2e"'
check "session id rediscovered via list"
sleep 1
curl -s http://127.0.0.1:18651/sessions/e2e/screenshot | grep -q E2E_MARKER_123
check "screen context preserved after reattach"

step "6. session still controllable after reattach"
$PY scripts/terminal_runtime_client.py act --session-id e2e --type submit --text 'echo AFTER_RESTART_456' > /dev/null
$PY scripts/terminal_runtime_client.py wait --session-id e2e --until screen_stable --timeout-ms 8000 --stable-ms 800 > /dev/null
curl -s http://127.0.0.1:18651/sessions/e2e/screenshot | grep -q AFTER_RESTART_456
check "act works after reattach"

step "7. delete destroys tmux session"
curl -s -X DELETE http://127.0.0.1:18651/sessions/e2e > /dev/null
sleep 1
tmux has-session -t atr-e2e 2>/dev/null
if [ $? -ne 0 ]; then echo "PASS: delete destroyed tmux session"; else echo "FAIL: delete destroyed tmux session"; FAIL=1; fi

step "8. security gate"
kill $SVC2 2>/dev/null; sleep 1
OUT=$(ATR_HOST=0.0.0.0 ATR_API_TOKEN= $PY scripts/terminal_runtime_service.py 2>&1)
echo "$OUT" | head -1
echo "$OUT" | grep -qi "refusing to listen"
check "refuses public bind without token"

step "9. graceful shutdown detaches (tmux survives)"
$PY scripts/terminal_runtime_service.py > /tmp/atr-svc3.log 2>&1 &
SVC3=$!
sleep 3
$PY scripts/terminal_runtime_client.py create --session-id e2e2 --command bash --backend tmux > /dev/null
kill -TERM $SVC3
sleep 2
tmux has-session -t atr-e2e2 2>/dev/null
check "tmux session survives graceful shutdown"
tmux kill-session -t atr-e2e2 2>/dev/null

echo
if [ $FAIL -eq 0 ]; then echo "ALL E2E PASS"; else echo "E2E FAILURES PRESENT"; exit 1; fi
