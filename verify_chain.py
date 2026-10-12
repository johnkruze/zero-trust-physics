#!/usr/bin/env python3
"""Verify a chain of runs from its saved answers, with no engine.

    python3 verify_chain.py first.json second.json [third.json ...]
    python3 verify_chain.py chain.json

In the first form each file is the text one call to Zero-Trust Physics returned
(run_trajectory, or verify_step for the last link), kept byte for byte, in
chain order: the first answer has no "chain", each later one has the "chain"
it was given. A file may also be the whole JSON-RPC message of that call. Each
answer's receipt is verified too.

In the second form the file is {"links": [<answer>, ...]}, the body the
verify_tape tool takes. The answers are then no longer the bytes that were
sent, so their receipts are not verified.

The rules of a chain, as this script carries them out: every run
alone, then for each link the upstream seals it names, the upstream outcome (a
continuation follows only "completed", a coupling "completed" or "ended"), the
model of a continuation, every handed value against the upstream's sealed final
state or request and against the downstream request, every start value of a
continued run being handed, and the chain seal. The first break is named:
chain, state, run_seal, upstream, outcome, pieces, handed, chain_seal.

It covers what the seals cover. It does not cover engine_version,
steps_requested, reject_detail, a frame's step label, the decimal copies, or a
key it does not read; the receipt covers those bytes of an answer kept byte for
byte. It shows the chain is consistent with itself. To see that the verifier
gives the same chain, send the last request, with its from, its run_seal and
its chain_seal, to verify_tape.

Exit code 0: every proof holds. 1: a proof is broken. 2: an input could not be
read as a chain. Python standard library only; it uses verify_run.py beside it.
Released under Apache-2.0.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_run import receipt, sealed_form, sha256_hex, state_digest, string_text  # noqa: E402

MAX_CHAIN_LINKS = 16
HEX = set("0123456789abcdef")


class NotRead(Exception):
    pass


def is_hex(text, digits):
    return isinstance(text, str) and len(text) == digits and set(text) <= HEX


def is_hex_value(value):
    if isinstance(value, str):
        return is_hex(value, 16)
    if isinstance(value, list):
        return bool(value) and all(is_hex_value(v) for v in value)
    return False


def hex_text(value):
    if isinstance(value, str):
        return string_text(value)
    return "[" + ",".join(hex_text(v) for v in value) + "]"


def chain_tail(kind, coupling, handed):
    """{"kind":..,"coupling":..,"handed":[{"from":..,"to":..,"unit":..,"value_hex":..},..]}"""
    entries = []
    for h in handed:
        entries.append('{"from":%s,"to":%s,"unit":%s,"value_hex":%s}' % (
            string_text(h["from"]), string_text(h["to"]),
            "null" if h["unit"] is None else string_text(h["unit"]), hex_text(h["value_hex"])))
    return '{"kind":%s,"coupling":%s,"handed":[%s]}' % (
        string_text(kind), "null" if coupling is None else string_text(coupling), ",".join(entries))


def chain_seal(upstream_commitment, tail, downstream_seal):
    return sha256_hex((upstream_commitment + tail + downstream_seal).encode("utf-8"))


def request_value_hex(value):
    """A number in a request, read as the nearest 64-bit number, as 16 hex digits."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return struct.pack(">d", float(value)).hex()
    if isinstance(value, list) and value:
        out = [request_value_hex(v) for v in value]
        return None if any(v is None for v in out) else out
    return None


def values_at(request, path):
    """One value for initial.<name> and parameters.<name>, one per segment for
    segments[*].load.<name>; None in the place of an absent value."""
    for prefix in ("initial.", "parameters."):
        if path.startswith(prefix):
            part = request.get(prefix[:-1])
            return [part.get(path[len(prefix):]) if isinstance(part, dict) else None]
    prefix = "segments[*].load."
    if path.startswith(prefix):
        name = path[len(prefix):]
        segments = request.get("segments") if isinstance(request.get("segments"), list) else []
        if not segments:
            return [None]
        return [s.get("load", {}).get(name) if isinstance(s, dict) and isinstance(s.get("load"), dict) else None
                for s in segments]
    raise KeyError(path)


def tape_cause(answer, inputs):
    """One run alone: None when it holds, else chain, state or run_seal.
    inputs is the request read with every number as a 64-bit number, so -0 stays -0."""
    link = sha256_hex(sealed_form(inputs).encode("utf-8"))
    for frame in answer["frames"]:
        data = bytes.fromhex(frame["frame_hex"])
        if len(data) != 64 or data[48:64] != bytes.fromhex(link)[:16]:
            return "chain"
        link = sha256_hex(data)
        if link != frame["link"]:
            return "chain"
    digest = state_digest(answer)
    if digest != answer["state_digest"]:
        return "state"
    tail = json.dumps({"outcome": answer["outcome"], "steps_landed": answer["steps_landed"],
                       "reject": answer["reject"], "state_digest": digest},
                      separators=(",", ":"), ensure_ascii=False)
    if sha256_hex((link + tail).encode("utf-8")) != answer["run_seal"]:
        return "run_seal"
    return None


def read_link(index, answer, inputs, last):
    if not isinstance(answer, dict):
        raise NotRead("links[%d] is not a JSON object" % index)
    if not isinstance(inputs, dict) or not isinstance(inputs.get("domain"), str) or not isinstance(inputs.get("card"), str):
        raise NotRead("links[%d].inputs names no card" % index)
    is_step = "sha256_seal" in answer and "run_seal" not in answer
    if is_step and not last:
        raise NotRead("links[%d] must be a run_trajectory answer: only the last link may be a step" % index)
    key = "sha256_seal" if is_step else "run_seal"
    if not is_hex(answer.get(key), 64):
        raise NotRead("links[%d].%s is not 64 lowercase hex digits" % (index, key))
    if is_step:
        state = answer.get("state")
        if not isinstance(state, dict):
            raise NotRead("links[%d].state is not a JSON object" % index)
        outcome = "completed"
    else:
        if not isinstance(answer.get("outcome"), str):
            raise NotRead("links[%d].outcome is missing" % index)
        outcome = answer["outcome"]
        state = answer.get("final_state") if isinstance(answer.get("final_state"), dict) else None
    chain = answer.get("chain")
    if index == 0 and chain is not None:
        raise NotRead("links[0].chain must be absent: the first link is where the chain starts")
    if index > 0:
        if not isinstance(chain, dict):
            raise NotRead("links[%d].chain is missing" % index)
        allowed = {"kind", "coupling", "upstream_run_seal", "upstream_chain_seal", "handed", "chain_seal"}
        if set(chain) - allowed:
            raise NotRead("links[%d].chain has a key it should not: %s" % (index, sorted(set(chain) - allowed)))
        kind = chain.get("kind")
        if kind not in ("continuation", "coupling"):
            raise NotRead("links[%d].chain.kind is not continuation or coupling" % index)
        coupling = chain.get("coupling")
        if kind == "continuation" and coupling is not None:
            raise NotRead("links[%d].chain.coupling must be null for a continuation" % index)
        if kind == "coupling" and not (isinstance(coupling, str) and coupling):
            raise NotRead("links[%d].chain.coupling must name the coupling" % index)
        for k in ("upstream_run_seal", "chain_seal"):
            if not is_hex(chain.get(k), 64):
                raise NotRead("links[%d].chain.%s is not 64 lowercase hex digits" % (index, k))
        if "upstream_chain_seal" not in chain or not (chain["upstream_chain_seal"] is None or is_hex(chain["upstream_chain_seal"], 64)):
            raise NotRead("links[%d].chain.upstream_chain_seal is not null or 64 lowercase hex digits" % index)
        handed = chain.get("handed")
        if not isinstance(handed, list) or not handed:
            raise NotRead("links[%d].chain.handed is not an array of at least one value" % index)
        for at, h in enumerate(handed):
            if (not isinstance(h, dict) or set(h) != {"from", "to", "unit", "value_hex"}
                    or not isinstance(h["from"], str) or not isinstance(h["to"], str)
                    or not (h["unit"] is None or isinstance(h["unit"], str)) or not is_hex_value(h["value_hex"])):
                raise NotRead("links[%d].chain.handed[%d] is not {from, to, unit, value_hex}" % (index, at))
    return {"is_step": is_step, "pair": (inputs["domain"], inputs["card"]), "inputs": inputs,
            "outcome": outcome, "seal": answer[key], "state": state, "chain": chain}


def handed_hold(up, link):
    state, chain = up["state"], link["chain"]
    if state is None:
        return False
    for h in chain["handed"]:
        if h["from"].startswith("final_state."):
            if state.get(h["from"][len("final_state."):] + "_hex") != h["value_hex"]:
                return False
        elif h["from"].startswith("inputs."):
            try:
                values = values_at(up["inputs"], h["from"][len("inputs."):])
            except KeyError:
                return False
            if any(request_value_hex(v) != h["value_hex"] for v in values):
                return False
        else:
            return False
        try:
            values = values_at(link["inputs"], h["to"])
        except KeyError:
            return False
        if any(request_value_hex(v) != h["value_hex"] for v in values):
            return False
    if chain["kind"] == "continuation" and not link["is_step"]:
        initial = link["inputs"].get("initial")
        if not isinstance(initial, dict):
            return False
        targets = {h["to"] for h in chain["handed"]}
        if any("initial." + k not in targets for k in initial):
            return False
    return True


def verify_links(answers, numbers):
    """answers as read; numbers the same with every number read as a 64-bit number.
    Returns (holds, broken_link, cause, last_chain_seal)."""
    count = len(answers)
    if count < 2:
        raise NotRead("a chain is at least two answers")
    if count > MAX_CHAIN_LINKS:
        raise NotRead("a chain is at most 16 answers")
    inputs = [n.get("inputs") if isinstance(n, dict) else None for n in numbers]
    links = [read_link(i, a, inputs[i], i + 1 == count) for i, a in enumerate(answers)]
    for i, (link, answer) in enumerate(zip(links, answers)):
        if link["is_step"]:
            continue
        cause = tape_cause(answer, link["inputs"])
        if cause:
            return False, i, cause, None
    commitment, last = links[0]["seal"], None
    for i in range(1, count):
        up, link = links[i - 1], links[i]
        chain = link["chain"]
        if chain["upstream_run_seal"] != up["seal"] or chain["upstream_chain_seal"] != (None if i == 1 else last):
            return False, i, "upstream", None
        admitted = up["outcome"] == "completed" or (chain["kind"] == "coupling" and up["outcome"] == "ended")
        if not admitted or up["state"] is None:
            return False, i, "outcome", None
        if chain["kind"] == "continuation" and up["pair"] != link["pair"]:
            return False, i, "pieces", None
        if not handed_hold(up, link):
            return False, i, "handed", None
        rebuilt = chain_seal(commitment, chain_tail(chain["kind"], chain["coupling"], chain["handed"]), link["seal"])
        if rebuilt != chain["chain_seal"]:
            return False, i, "chain_seal", None
        commitment = last = rebuilt
    return True, None, None, last


def load(path):
    raw = open(path, "rb").read().decode("utf-8")
    outer = json.loads(raw)
    if isinstance(outer, dict) and "jsonrpc" in outer:
        raw = outer["result"]["content"][0]["text"]
    # Read twice: as written, and with a whole number too read as the nearest
    # 64-bit number, so a request's -0 stays -0 when it is hashed.
    return raw, json.loads(raw), json.loads(raw, parse_int=float)


def main(paths):
    texts = []
    try:
        if len(paths) == 1:
            _, body, body_numbers = load(paths[0])
            if not isinstance(body, dict) or set(body) != {"links"} or not isinstance(body["links"], list):
                raise NotRead("one file must be {\"links\": [<answer>, ...]}")
            answers, numbers = body["links"], body_numbers["links"]
        else:
            loaded = [load(p) for p in paths]
            texts = [t for t, _, _ in loaded]
            answers = [a for _, a, _ in loaded]
            numbers = [n for _, _, n in loaded]
        holds, at, cause, last = verify_links(answers, numbers)
    except (OSError, ValueError, KeyError, IndexError, TypeError, NotRead) as e:
        print("not read:", e)
        return 2

    broken = []
    print("%-14s %d" % ("links:", len(answers)))
    if holds:
        print("%-14s holds  last chain_seal %s" % ("chain:", last))
    else:
        print("%-14s BROKEN  first break at links[%d]: %s" % ("chain:", at, cause))
        broken.append("chain")
    for i, text in enumerate(texts):
        given, made = receipt(text)
        ok = given is not None and given == made
        print("%-14s %s  %s" % ("receipt[%d]:" % i, "holds" if ok else "BROKEN", made))
        if not ok:
            broken.append("receipt[%d]" % i)
    if answers[-1].get("sha256_seal") and "run_seal" not in answers[-1]:
        print("note:          the last link is a step; its sha256_seal is shown by sending its request to verify_step again")
    print("result:", "every proof holds" if not broken else "broken: " + ", ".join(broken))
    return 0 if not broken else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1:]))
