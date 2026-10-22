#!/usr/bin/env python3
"""Verify a chain of runs from its saved answers, with no engine (seal rule v2, SHA-384).

    python3 verify_chain.py first.json second.json [third.json ...] [signature options]
    python3 verify_chain.py chain.json [signature options]

    signature options: --public-key <file> --now <YYYY-MM-DDTHH:MM:SSZ> --nonce-ledger <file>

In the first form each file is the text one call to Zero-Trust Physics returned
(run_trajectory, or verify_step or solve for the last link), kept byte for byte, in
chain order: the first answer has no "chain", each later one has the "chain"
it was given. A file may also be the whole JSON-RPC message of that call. Each
answer's receipt is verified too.

In the second form the file is {"links": [<answer>, ...]}, the body the
verify_tape tool takes. The answers are then no longer the bytes that were
sent, so their receipts are not verified; a signature is still verified on each
answer's text as it stands in the file.

The rules of a chain, as this script carries them out: every run
alone, then for each link the upstream seals it names, the upstream outcome (a
continuation follows only "completed", a coupling "completed" or "ended"), the
model of a continuation, every handed value against the upstream's sealed final
state or request and against the downstream request, every start value of a
continued run being handed, and the chain seal. The first break is named:
chain, state, run_seal, solution_seal, upstream, outcome, pieces, handed,
chain_seal.

The last link may be a solve, handed by a coupling of a card into a solver
(engine 0.15.1): its solution_seal is recomputed from its answer's values (the
six seal_parts and the seal, by the engine's rule), a value may be handed from
frames[*].<slot> (that slot of every recorded frame of the upstream run, a
32-bit slot widened to 64 bits exactly) and may stand at places k.. of the
request's array (a "to" ending in [k..]). That the values are the solver's own
is shown by sending the chain's answers, as links, to verify_tape.

It covers what the seals cover. It does not cover engine_version,
steps_requested, reject_detail, a frame's step label, the decimal copies, or a
key it does not read; the receipt covers those bytes of an answer kept byte for
byte. It shows the chain is consistent with itself. To see that the verifier
gives the same chain, send the last request, with its from, its run_seal and
its chain_seal, to verify_tape.

Every hash is SHA-384, written as 96 hex digits (a step's seal is
sha384_seal). The engine's signature on each answer, when there is one, is
verified as verify_run.py verifies it, and its lines carry the answer's place,
links[0].signature, links[1].signature, ...

Exit code 0: every proof holds. 1: a proof is broken. 2: an input could not be
read as a chain; a record of seal rule v1 (SHA-256, engine 0.14.3 and earlier)
is not read, cause SealRuleNotServed. 5: every seal holds and a signature does
not. SHA-384 needs Python's standard library only; verifying a signature needs
dilithium-py 1.5.1. It uses verify_run.py and answer_signature.py beside it.
Released under Apache-2.0.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_run import receipt, result, sealed_form, sha384_hex, state_digest, string_text  # noqa: E402
from answer_signature import (NotRead as OptionNotRead, SealRuleNotServed, refuse_other_rule,  # noqa: E402
                              say_not_served, take_options)

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
    return sha384_hex((upstream_commitment + tail + downstream_seal).encode("utf-8"))


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
    link = sha384_hex(sealed_form(inputs).encode("utf-8"))
    for frame in answer["frames"]:
        data = bytes.fromhex(frame["frame_hex"])
        if len(data) != 64 or data[48:64] != bytes.fromhex(link)[:16]:
            return "chain"
        link = sha384_hex(data)
        if link != frame["link"]:
            return "chain"
    digest = state_digest(answer)
    if digest != answer["state_digest"]:
        return "state"
    tail = json.dumps({"outcome": answer["outcome"], "steps_landed": answer["steps_landed"],
                       "reject": answer["reject"], "state_digest": digest},
                      separators=(",", ":"), ensure_ascii=False)
    if sha384_hex((link + tail).encode("utf-8")) != answer["run_seal"]:
        return "run_seal"
    return None


FRAME_SLOTS = {"t": (0, 8), "pos[0]": (8, 4), "pos[1]": (12, 4), "pos[2]": (16, 4), "vel[0]": (20, 4),
               "vel[1]": (24, 4), "vel[2]": (28, 4), "force_torque": (32, 4), "residual": (36, 4)}
SOLUTION_PARTS = ("inputs", "engine_version", "result", "invariants", "field_sha384", "outcome")


def hex_lines(section, values):
    """One <section>.<key>:<hex> line for each key ending in _hex, sorted by key."""
    if values is None:
        return ""
    lines = []
    for key, value in values.items():
        if key.endswith("_hex"):
            if not (isinstance(value, str) or isinstance(value, list)):
                raise ValueError("%s.%s is not hex" % (section, key))
            lines.append((key, value if isinstance(value, str) else hex_list(value)))
    return "".join("%s.%s:%s\n" % (section, key, hex) for key, hex in sorted(lines))


def hex_list(value):
    return value if isinstance(value, str) else "[" + ",".join(hex_list(v) for v in value) + "]"


def solution_cause(answer, inputs):
    """A solve's seal recomputed from its answer: None when it holds, else solution_seal."""
    try:
        tail = json.dumps({"outcome": answer["outcome"], "iterations": answer["iterations"], "reject": answer.get("reject")},
                          separators=(",", ":"), ensure_ascii=False)
        texts = [sealed_form(inputs), "engine_version:%s\n" % answer["engine_version"],
                 hex_lines("result", answer.get("result")), hex_lines("invariants", answer.get("invariants")),
                 answer.get("field_sha384") or "null", tail]
    except (KeyError, ValueError, TypeError):
        return "solution_seal"
    parts = answer.get("seal_parts") or {}
    for name, text in zip(SOLUTION_PARTS, texts):
        if parts.get(name) != sha384_hex(text.encode("utf-8")):
            return "solution_seal"
    whole = texts[0] + texts[1] + texts[3] + texts[2] + texts[4] + texts[5]
    return None if sha384_hex(whole.encode("utf-8")) == answer["solution_seal"] else "solution_seal"


def frame_values(frames, slot):
    if slot not in FRAME_SLOTS or not isinstance(frames, list) or not frames:
        return None
    at, width = FRAME_SLOTS[slot]
    out = []
    for frame in frames:
        data = bytes.fromhex(frame["frame_hex"])[at:at + width]
        value = struct.unpack("<d", data)[0] if width == 8 else struct.unpack("<f", data)[0]
        out.append(struct.pack(">d", value).hex())
    return out


def read_link(index, answer, inputs, last):
    if not isinstance(answer, dict):
        raise NotRead("links[%d] is not a JSON object" % index)
    is_solve = isinstance(inputs, dict) and isinstance(inputs.get("solver"), str) and "solution_seal" in answer
    if is_solve and (not last or index == 0):
        raise NotRead("links[%d] must be a run_trajectory answer: only the last link may be a solve" % index)
    if not is_solve and (not isinstance(inputs, dict) or not isinstance(inputs.get("domain"), str) or not isinstance(inputs.get("card"), str)):
        raise NotRead("links[%d].inputs names no card" % index)
    if is_solve:
        if not is_hex(answer.get("solution_seal"), 96) or not isinstance(answer.get("outcome"), str):
            raise NotRead("links[%d].solution_seal is not 96 lowercase hex digits, or outcome is missing" % index)
    is_step = not is_solve and "sha384_seal" in answer and "run_seal" not in answer
    if is_step and not last:
        raise NotRead("links[%d] must be a run_trajectory answer: only the last link may be a step" % index)
    key = "solution_seal" if is_solve else ("sha384_seal" if is_step else "run_seal")
    if not is_hex(answer.get(key), 96):
        raise NotRead("links[%d].%s is not 96 lowercase hex digits" % (index, key))
    if is_solve:
        state, outcome = None, answer["outcome"]
    elif is_step:
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
            if not is_hex(chain.get(k), 96):
                raise NotRead("links[%d].chain.%s is not 96 lowercase hex digits" % (index, k))
        if "upstream_chain_seal" not in chain or not (chain["upstream_chain_seal"] is None or is_hex(chain["upstream_chain_seal"], 96)):
            raise NotRead("links[%d].chain.upstream_chain_seal is not null or 96 lowercase hex digits" % index)
        handed = chain.get("handed")
        if not isinstance(handed, list) or not handed:
            raise NotRead("links[%d].chain.handed is not an array of at least one value" % index)
        for at, h in enumerate(handed):
            if (not isinstance(h, dict) or set(h) != {"from", "to", "unit", "value_hex"}
                    or not isinstance(h["from"], str) or not isinstance(h["to"], str)
                    or not (h["unit"] is None or isinstance(h["unit"], str)) or not is_hex_value(h["value_hex"])):
                raise NotRead("links[%d].chain.handed[%d] is not {from, to, unit, value_hex}" % (index, at))
    pair = ("solver", inputs["solver"]) if is_solve else (inputs["domain"], inputs["card"])
    return {"is_step": is_step, "is_solve": is_solve, "pair": pair, "inputs": inputs, "frames": answer.get("frames"),
            "outcome": outcome, "seal": answer[key], "state": state, "chain": chain}


def handed_hold(up, link):
    state, chain = up["state"], link["chain"]
    if state is None:
        return False
    for h in chain["handed"]:
        if h["from"].startswith("final_state."):
            if state.get(h["from"][len("final_state."):] + "_hex") != h["value_hex"]:
                return False
        elif h["from"].startswith("frames[*]."):
            if chain["kind"] != "coupling" or frame_values(up["frames"], h["from"][len("frames[*]."):]) != h["value_hex"]:
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
        if h["to"].endswith("..]") and "[" in h["to"]:
            # An array handed to places first.. of the request's array.
            path, first = h["to"][:h["to"].rindex("[")], h["to"][h["to"].rindex("[") + 1:-3]
            if not first.isdigit() or not isinstance(h["value_hex"], list):
                return False
            try:
                array = values_at(link["inputs"], path)[0]
            except KeyError:
                return False
            first = int(first)
            if not isinstance(array, list) or len(array) < first + len(h["value_hex"]):
                return False
            if [request_value_hex(v) for v in array[first:first + len(h["value_hex"])]] != h["value_hex"]:
                return False
            continue
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
    for answer in answers:
        if isinstance(answer, dict):
            refuse_other_rule(answer)
            if isinstance(answer.get("chain"), dict):
                refuse_other_rule(answer["chain"])
    inputs = [n.get("inputs") if isinstance(n, dict) else None for n in numbers]
    links = [read_link(i, a, inputs[i], i + 1 == count) for i, a in enumerate(answers)]
    for i, (link, answer) in enumerate(zip(links, answers)):
        if link["is_step"]:
            continue
        if link["is_solve"]:
            cause = solution_cause(answer, link["inputs"])
            if cause:
                return False, i, cause, None
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
        if chain["kind"] == "continuation" and (up["pair"] != link["pair"] or link["is_solve"]):
            return False, i, "pieces", None
        if not handed_hold(up, link):
            return False, i, "handed", None
        rebuilt = chain_seal(commitment, chain_tail(chain["kind"], chain["coupling"], chain["handed"]), link["seal"])
        if rebuilt != chain["chain_seal"]:
            return False, i, "chain_seal", None
        commitment = last = rebuilt
    return True, None, None, last


def load(path):
    with open(path, "rb") as handle:
        raw = handle.read().decode("utf-8")
    outer = json.loads(raw)
    if isinstance(outer, dict) and "jsonrpc" in outer:
        raw = outer["result"]["content"][0]["text"]
    # Read twice: as written, and with a whole number too read as the nearest
    # 64-bit number, so a request's -0 stays -0 when it is hashed.
    return raw, json.loads(raw), json.loads(raw, parse_int=float)


def link_texts(raw):
    """The text of each answer of {"links": [<answer>, ...]} as it stands in the file."""
    decoder = json.JSONDecoder()
    at = raw.index("[", raw.index('"links"')) + 1
    texts = []
    while True:
        while raw[at] in " \t\r\n,":
            at += 1
        if raw[at] == "]":
            return texts
        _, end = decoder.raw_decode(raw, at)
        texts.append(raw[at:end])
        at = end


def main(arguments):
    try:
        paths, given = take_options(arguments)
    except OptionNotRead as e:
        print("not read:", e)
        return 2
    if not paths:
        print(__doc__)
        return 2
    texts = []
    try:
        if len(paths) == 1:
            raw, body, body_numbers = load(paths[0])
            if not isinstance(body, dict) or set(body) != {"links"} or not isinstance(body["links"], list):
                raise NotRead("one file must be {\"links\": [<answer>, ...]}")
            answers, numbers = body["links"], body_numbers["links"]
            signed_texts = link_texts(raw)
        else:
            loaded = [load(p) for p in paths]
            texts = [t for t, _, _ in loaded]
            answers = [a for _, a, _ in loaded]
            numbers = [n for _, _, n in loaded]
            signed_texts = texts
        holds, at, cause, last = verify_links(answers, numbers)
    except SealRuleNotServed as e:
        return say_not_served(e)
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
        given_receipt, made = receipt(text)
        ok = given_receipt is not None and given_receipt == made
        print("%-14s %s  %s" % ("receipt[%d]:" % i, "holds" if ok else "BROKEN", made))
        if not ok:
            broken.append("receipt[%d]" % i)
    if answers[-1].get("sha384_seal") and "run_seal" not in answers[-1]:
        print("note:          the last link is a step; its sha384_seal is shown by sending its request to verify_step again")
    if isinstance(answers[-1].get("inputs"), dict) and "solver" in answers[-1]["inputs"]:
        print("note:          the last link is a solve; its solution_seal is recomputed from its values, which verify_tape given these links shows are the solver's own")
    signature_fails = False
    try:
        for i, text in enumerate(signed_texts):
            signature_fails |= given.show(given.check(text), "links[%d]" % i)
    except OptionNotRead as e:
        print("not read:", e)
        return 2
    return result(broken, signature_fails)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
