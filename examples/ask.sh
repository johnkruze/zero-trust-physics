#!/bin/sh
# Ask Zero-Trust Physics a question with curl.
#
#     sh examples/ask.sh              # list what is served, then run one model
#     sh examples/ask.sh answer.json  # the same, and keep the whole reply of the run
#
# The address is open to any agent. It speaks the Model Context Protocol over
# HTTP: one POST, one JSON answer. It is shared, and when it is busy it says so
# at once, so this waits a moment and sends the same request again.
#
# Released under Apache-2.0.

ADDRESS="https://mcp.zerotrustphysics.com/mcp"

ask() {
  # $1: the tool's name. $2: its arguments, as JSON.
  wait=2
  for try in 1 2 3 4 5 6; do
    reply=$(curl -sS --max-time 90 -w '\n%{http_code}' "$ADDRESS" \
      -H 'Content-Type: application/json' \
      -H 'Accept: application/json, text/event-stream' \
      -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"$1\",\"arguments\":$2}}")
    status=$(printf '%s' "$reply" | tail -n 1)
    body=$(printf '%s' "$reply" | sed '$d')
    if [ "$status" = "429" ] || printf '%s' "$body" | grep -q 'Too many concurrent physics tasks.'; then
      sleep "$wait"; wait=$((wait * 2)); continue
    fi
    printf '%s\n' "$body"
    return 0
  done
  echo "the address stayed busy; try again in a minute" >&2
  return 1
}

# 1. What is served. Each list begins with its own count.
ask list_cards '{}' | cut -c 1-400
echo

# 2. One run: a cold plate, one watt of heat, ten steps of 0.1 s.
RUN='{"domain":"energy","card":"thermal","initial":{"temperature_k":293.15},"dt_s":0.1,"segments":[{"steps":10,"load":{"heat_power_w":1.0,"ambient_k":293.15}}],"record_every":10}'
if [ -n "$1" ]; then
  ask run_trajectory "$RUN" > "$1" && echo "kept: $1  (verify it with: python3 verify_run.py $1)"
else
  ask run_trajectory "$RUN"
fi
