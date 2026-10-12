#!/usr/bin/env python3
"""Ask Zero-Trust Physics a question and keep the answer with its cryptographic proof.

    python3 examples/ask.py                # list what is served, run one model, verify the proof
    python3 examples/ask.py answer.json    # the same, and keep the run's answer byte for byte

The address is https://mcp.zerotrustphysics.com/mcp and it is open to any agent.
It speaks the Model Context Protocol over HTTP. Each request stands alone: one
POST, one JSON answer.

Python standard library only. Released under Apache-2.0.
"""
import json
import sys
import time
import urllib.error
import urllib.request

ADDRESS = "https://mcp.zerotrustphysics.com/mcp"
BUSY = "Too many concurrent physics tasks."


def call(tool, arguments=None, tries=8):
    """Call one tool and return the text of its answer, exactly as it was sent.

    The address is shared. When it is busy it says so at once and holds nothing
    in a queue, so this waits a moment and sends the same request again.
    """
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": tool, "arguments": arguments or {}}}).encode("utf-8")
    request = urllib.request.Request(ADDRESS, data=body, headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "zero-trust-physics-example/1",
    })
    wait = 2.0
    for _ in range(tries):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                message = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code != 429:
                raise
            time.sleep(float(error.headers.get("Retry-After") or wait))
            wait *= 1.5
            continue
        if "error" in message:
            text, stopped = message["error"].get("message", ""), True
        else:
            text = message["result"]["content"][0]["text"]
            stopped = bool(message["result"].get("isError"))
        if stopped and BUSY in text:
            time.sleep(wait)
            wait *= 1.5
            continue
        if stopped:
            raise RuntimeError(text)
        return text
    raise RuntimeError("the address stayed busy; try again in a minute")


def main(keep=None):
    # 1. What is served.
    cards = json.loads(call("list_cards"))
    solvers = json.loads(call("list_solvers"))
    print("models stepped through time:", cards["count"])
    print("field solvers:", solvers["count"])

    # 2. Read one model before running it: its inputs, its limits, the real
    #    thing it was tested on and how it did, in its own words.
    description = call("describe_card", {"domain": "aerospace", "card": "capsule_stardust"})
    print("the Stardust capsule's description:", len(description), "characters")

    # 3. Run a small model: a cold plate, one watt of heat, ten steps of 0.1 s.
    question = {
        "domain": "energy", "card": "thermal",
        "initial": {"temperature_k": 293.15},
        "dt_s": 0.1,
        "segments": [{"steps": 10, "load": {"heat_power_w": 1.0, "ambient_k": 293.15}}],
        "record_every": 1,
    }
    text = call("run_trajectory", question)
    answer = json.loads(text)
    print("outcome:", answer["outcome"])
    print("temperature after ten steps:", answer["final_state"]["temperature_k"], "K")
    print("run_seal:", answer["run_seal"])
    if keep:
        with open(keep, "wb") as out:
            out.write(text.encode("utf-8"))
        print("kept, byte for byte:", keep)

    # 4. Ask the verifier to run the same question again and compare the proofs.
    again = json.loads(call("verify_tape", {"request": answer["inputs"], "run_seal": answer["run_seal"]}))
    print("run again, the proof holds:", again["holds"])
    return 0 if again["holds"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
