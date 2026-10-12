#!/usr/bin/env python3
"""Recompute the cryptographic proof of one run from a saved answer, with no engine.

    python3 verify_run.py answer.json

answer.json is the text a run_trajectory call to Zero-Trust Physics returned,
kept byte for byte. It may also be the whole JSON-RPC message of that call; the
answer's text is then read from result.content[0].text.

The script recomputes link_0 from the request, follows the chain of recorded
frames, recomputes the state digest, the run seal and the receipt, and prints
one line for each. Exit code 0: every proof holds. 1: a proof is broken.
2: the file could not be read as an answer.

A run sent with "from" is the run of the same request typed by hand, so this
script verifies it as any run; its "chain" is verified by verify_chain.py
beside this script.

The rules are the code below, each in a few lines.
Python standard library only. Released under Apache-2.0.
"""
import hashlib
import json
import struct
import sys


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def number_text(x) -> str:
    """A number is x and the 16 hex digits of the bits of the nearest 64-bit number."""
    return "x" + struct.pack(">d", float(x)).hex()


def string_text(s: str) -> str:
    """The JSON encoding of a string: \\" \\\\ \\b \\t \\n \\f \\r, \\u00xx below U+0020, the rest as is."""
    return json.dumps(s, ensure_ascii=False)


def sealed_form(value) -> str:
    """The text a request is hashed in. It is not JSON and is never sent."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return number_text(value)
    if isinstance(value, str):
        return string_text(value)
    if isinstance(value, list):
        return "[" + ",".join(sealed_form(v) for v in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value, key=lambda k: k.encode("utf-8"))
        return "{" + ",".join(string_text(k) + ":" + sealed_form(value[k]) for k in keys) + "}"
    raise ValueError("a value of type %s has no sealed form" % type(value).__name__)


def state_digest(answer):
    """SHA-256 of one line key:value for every _hex key and every boolean of the final
    state, sorted by key, then the two ledger-error lines. Null when no step landed."""
    state = answer["final_state"]
    if not answer["steps_landed"] or state is None:
        return None
    lines = []
    for key in sorted(state, key=lambda k: k.encode("utf-8")):
        value = state[key]
        if isinstance(value, bool):
            lines.append("%s:%s\n" % (key, "true" if value else "false"))
        elif key.endswith("_hex"):
            if isinstance(value, list):
                if any(not isinstance(v, str) for v in value):
                    raise ValueError("the state field %s holds a nested array; this script reads only flat ones" % key)
                value = ",".join(value)
            lines.append("%s:%s\n" % (key, value))
    lines.append("final_residual_conservation_error_hex:%s\n" % answer["final_residual_conservation_error_hex"])
    lines.append("max_residual_conservation_error_hex:%s\n" % answer["max_residual_conservation_error_hex"])
    return sha256_hex("".join(lines).encode("utf-8"))


def receipt(text: str):
    """The hash of the bytes before the tail ,"receipt_sha256":"<64 hex>"} closed with }."""
    marker = ',"receipt_sha256":"'
    at = text.rfind(marker)
    tail = text[at + len(marker):]
    if at < 0 or len(tail) != 66 or not tail.endswith('"}'):
        return None, None
    return tail[:64], sha256_hex((text[:at] + "}").encode("utf-8"))


def read_answer(path):
    raw = open(path, "rb").read().decode("utf-8")
    # A number is read as the nearest 64-bit number; a whole number too, so -0 stays -0.
    outer = json.loads(raw, parse_int=float)
    if isinstance(outer, dict) and "jsonrpc" in outer:
        raw = json.loads(raw)["result"]["content"][0]["text"]
    return raw, json.loads(raw, parse_int=float), json.loads(raw)


def main(path):
    try:
        text, answer, plain = read_answer(path)
        request = answer["inputs"]
        frames = plain["frames"]
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        print("not read:", e)
        return 2

    broken = []

    def report(name, ok, detail=""):
        print("%-14s %s%s" % (name + ":", "holds" if ok else "BROKEN", "  " + detail if detail else ""))
        if not ok:
            broken.append(name)

    link = sha256_hex(sealed_form(request).encode("utf-8"))
    print("%-14s %s" % ("link_0:", link))

    chain_ok, where = True, ""
    for frame in frames:
        data = bytes.fromhex(frame["frame_hex"])
        if len(data) != 64:
            chain_ok, where = False, "frame of step %s is not 64 bytes" % frame["step"]
            break
        if data[48:64] != bytes.fromhex(link)[:16]:
            chain_ok, where = False, "proof slot of the frame of step %s" % frame["step"]
            break
        link = sha256_hex(data)
        if link != frame["link"]:
            chain_ok, where = False, "link of the frame of step %s" % frame["step"]
            break
    report("chain", chain_ok, where or "%d frames, last link %s" % (len(frames), link))

    try:
        digest = state_digest(plain)
    except ValueError as e:
        print("not read:", e)
        return 2
    report("state_digest", digest == plain["state_digest"], str(digest))

    tail = json.dumps({"outcome": plain["outcome"], "steps_landed": plain["steps_landed"],
                       "reject": plain["reject"], "state_digest": digest},
                      separators=(",", ":"), ensure_ascii=False)
    seal = sha256_hex((link + tail).encode("utf-8"))
    report("run_seal", chain_ok and seal == plain["run_seal"], seal)

    given, made = receipt(text)
    report("receipt", given is not None and given == made, str(made))

    print("result:", "every proof holds" if not broken else "broken: " + ", ".join(broken))
    return 0 if not broken else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
