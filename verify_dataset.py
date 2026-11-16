#!/usr/bin/env python3
"""Verify a dataset of runs with no engine (seal rule v2, SHA-384).

    python3 verify_dataset.py answer.json [signature options]   # a run_dataset answer asked with "answer": "full"
    python3 verify_dataset.py <folder> [signature options]      # a folder holding head.json, rows.jsonl and frames.bin

    signature options: --public-key <file> --now <YYYY-MM-DDTHH:MM:SSZ> --nonce-ledger <file>

In the first form the file is the text a run_dataset call to Zero-Trust Physics
returned, kept byte for byte, when the request asked "store": "frames",
"return": "inline" and "answer": "full": its head, every row whole and
frames_hex. It may also be the whole JSON-RPC message of that call. In the
second form the folder holds the same three parts as files.

It verifies the plan hash, the request of every row against a list plan, every
row's chain of frames, state digest, run seal and leaf, the row tree (RFC 6962),
the dataset seal, the two hashes of the rows and the frames, the frame file's
80-byte header (GKF3, layout 2, the counts, the dataset seal), and the head's
receipt, and prints one line for each. Where the rows are not the plan's rows
in their places it names the first place that does not hold its own row and
says whether a row was dropped, repeated, swapped or changed. It also holds
what no seal covers to what the engine writes: every decimal of a final state
to the exact value beside it (its _hex), bit for bit, and every _hex to a decimal
beside it, the keys of each row, and a sentence (reject_detail) on each row that
did not complete and on no other, which on a run refused part way ends with the
step it is sealed to.

Every hash is SHA-384, written as 96 hex digits, under the rule the head names:
"seal_rule":"zero-trust-physics/seal/v2". The leaf of a row is the compact JSON
of row, request_sha384, outcome, run_seal and reject_detail_sha384: the SHA-384
of the UTF-8 bytes of the row's sentence, or null when it has none. The head's
signature, when it carries one, follows its receipt, and is verified as
verify_run.py verifies an answer's.

Exit code 0: every proof holds. 1: a proof is broken, or a value no seal covers
is not as the engine writes it. 2: not read; a record of seal rule v1 (SHA-256,
engine 0.14.3 and earlier, a GKF2 frame file) is not read, cause
SealRuleNotServed. 5: every seal holds and the signature does not.

A grid or a sample plan is expanded by rules this script does not hold: for
those it verifies every proof and says that the rows were not compared with the
plan. A plan of solves is not read here.

The rules are the code below, each in a few lines. SHA-384 needs Python's
standard library only; verifying a signature needs dilithium-py 1.5.1. It uses
verify_run.py and answer_signature.py beside it. Released under Apache-2.0.
"""
import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_run import receipt, result, sealed_form, sha384_hex, state_digest  # noqa: E402
from answer_signature import (NotRead, SealRuleNotServed, refuse_other_rule, say_not_served,  # noqa: E402
                              take_options)

HEADER_LEN = 80
MAGIC = b"GKF3"
LAYOUT = 2


def split(count):
    """The largest power of two below count, for count of at least 2 (RFC 6962)."""
    power = 1
    while power <= (count - 1) // 2:
        power *= 2
    return power


def tree_root(leaves):
    if len(leaves) == 1:
        return leaves[0]
    at = split(len(leaves))
    return hashlib.sha384(b"\x01" + tree_root(leaves[:at]) + tree_root(leaves[at:])).digest()


def leaf_text(number, request_hash, row):
    """The leaf of a row as the engine writes it, or None when the sentence is neither a string nor null."""
    sentence = row["reject_detail"]
    if sentence is not None and not isinstance(sentence, str):
        return None
    leaf = {"row": number, "request_sha384": request_hash, "outcome": row["outcome"], "run_seal": row["run_seal"],
            "reject_detail_sha384": None if sentence is None else sha384_hex(sentence.encode("utf-8"))}
    return json.dumps(leaf, separators=(",", ":"), ensure_ascii=False)


def whole(value):
    """A row number as the engine writes it: a whole number of at least 0, else None."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def misplaced(read, planned, planned_rows):
    """The first place that does not hold its own row, and what happened there. read holds, for each
    place, the number the row carries (its "row") and its request in sealed form; planned holds the
    plan's requests in sealed form for a list plan, else None, and then a row is known by its number
    alone. None when every row read is in its place and none is missing."""
    count = len(read)

    def is_row(row, request):
        return planned is None or (row < len(planned) and planned[row] == request)

    def stands(place):
        number, request = read[place]
        return number == place and is_row(place, request)

    def row_of(place):
        """The row of the plan the row in place is: the one whose number it carries when it carries
        that row's request, else the one of its place when it carries that request, else the
        nearest row of the plan with its request. With no list, the number it carries, unless the
        row of that number stands in its own place with another request."""
        number, request = read[place]
        if planned is None:
            if number is not None and number != place and number < count and read[number][0] == number:
                return number if read[number][1] == request else place
            return number
        if number is not None and is_row(number, request):
            return number
        if is_row(place, request):
            return place
        for step in range(1, len(planned) + 1):
            for row in (place + step, place - step):
                if 0 <= row < len(planned) and planned[row] == request:
                    return row
        return None

    for place in range(count):
        if stands(place):
            continue
        number, row = read[place][0], row_of(place)
        if row is not None and row > place and row < count and row_of(row) == place:
            return "row %d: rows %d and %d are swapped" % (place, place, row)
        if row is not None and row > place and count < planned_rows:
            return "row %d: row %d was dropped, and the row here is row %d" % (place, place, row)
        if row is not None and row > place and row < count and stands(row):
            return "row %d: row %d is repeated here, so row %d is missing" % (place, row, place)
        if row is not None and row > place:
            return "row %d: the row here is row %d, out of its place" % (place, row)
        if row is not None and row < place:
            if place >= planned_rows:
                return "row %d: row %d is repeated here, after the plan's last row" % (place, row)
            if count > planned_rows:
                return "row %d: row %d is repeated here" % (place, row)
            return "row %d: row %d is repeated here, so row %d is missing" % (place, row, place)
        if row is not None and planned is None:
            return "row %d: the row here carries the number %s, and row %s stands in its own place with another request" % (
                place, json.dumps(number), json.dumps(number))
        if row is not None:
            return "row %d: the row here carries the request of row %d and the number %s" % (
                place, place, json.dumps(number))
        if place >= planned_rows:
            return "row %d: a row added, after the plan's last row" % place
        if number == place:
            return "row %d: request is not the plan's" % place
        return "row %d: the row here is not the plan's row of this place" % place
    if count < planned_rows and planned is None:
        return ("row %d: the first row missing by the numbers the rows carry, after the last row read (%d rows read, "
                "%d in the head; the plan is not a list, so rows were not compared with it)" % (count, count, planned_rows))
    if count < planned_rows:
        return "row %d: the first row missing, after the last row read (%d rows read, %d in the head)" % (
            count, count, planned_rows)
    return None


def is_exact(text):
    """16 lowercase hex digits: the bits of a 64-bit number, as the engine writes them."""
    return isinstance(text, str) and len(text) == 16 and all(c in "0123456789abcdef" for c in text)


def decimal_not_its_hex(row):
    """The first decimal of a final state that is not the exact value beside it (its _hex), or None.
    A decimal that is not a number (a string, null) is not its exact value. A _hex that is not 16 hex
    digits is left to the state digest, which it breaks."""
    def differs(value, exact):
        if isinstance(exact, list):
            return (not isinstance(value, list) or len(value) != len(exact)
                    or any(differs(v, e) for v, e in zip(value, exact)))
        if not is_exact(exact):
            return False
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return True
        # The bits, so a minus zero is not a zero.
        try:
            return struct.pack(">d", float(value)).hex() != exact
        except OverflowError:
            return True
    state = row.get("final_state")
    if not isinstance(state, dict):
        return None
    for key, value in state.items():
        if key.endswith("_hex") or isinstance(value, bool) or key + "_hex" not in state:
            continue
        if differs(value, state[key + "_hex"]):
            return "final_state.%s reads %s and its exact value %s_hex is %s" % (
                key, json.dumps(value), key, json.dumps(state[key + "_hex"]))
    return None


ROW_KEYS = ("row", "request", "outcome", "steps_landed", "reject", "reject_detail", "final_state",
            "final_residual_conservation_error_hex", "max_residual_conservation_error_hex",
            "state_digest", "frames", "last_link", "run_seal", "leaf")


def refused_tail(steps_landed):
    """The last sentence of a run refused part way, as the engine writes it."""
    if steps_landed == 0:
        return "The run is sealed with no step landed. The state at step 1 was refused and is not sealed."
    return "The run is sealed to step %d. The state at step %d was refused and is not sealed." % (steps_landed, steps_landed + 1)


def field_not_written(row):
    """The first field of a row that is not as the engine writes it, or None: a key the engine does
    not write, a value of a final state with no _hex beside it, or a sentence (reject_detail) where
    none is written or none where one is. A run that completed has no sentence; one that ended or was
    refused, and a request turned away (unadmitted), has one. The leaf seals the sentence; this still
    names a dataset sealed again by hand (no key is needed) with a sentence where the engine writes
    none, or none where it writes one."""
    for key in row:
        if key not in ROW_KEYS:
            return "%s is not a key of a row" % json.dumps(key)
    for key in ROW_KEYS:
        if key not in row:
            return "the row has no %s" % key
    state = row["final_state"]
    if isinstance(state, dict):
        for key, value in state.items():
            if not key.endswith("_hex") and not isinstance(value, bool) and key + "_hex" not in state:
                return "final_state.%s has no exact value beside it, so no seal covers it" % key
            if key.endswith("_hex") and key[:-4] not in state:
                return "final_state.%s has no decimal beside it, which the engine writes for every exact value" % key
    sentence = row["reject_detail"]
    if row["outcome"] == "completed" and sentence is not None:
        return "a completed run carries a sentence, reject_detail %s" % json.dumps(sentence)
    if row["outcome"] != "completed" and (not isinstance(sentence, str) or not sentence):
        return "a run that is %s carries no sentence: reject_detail is %s" % (row["outcome"], json.dumps(sentence))
    # A refused run's sentence ends with the step it is sealed to.
    steps = row["steps_landed"] if isinstance(row["steps_landed"], int) else 0
    if row["outcome"] == "refused" and not sentence.endswith(" " + refused_tail(steps)):
        return "a run refused part way ends its sentence with %s" % json.dumps(refused_tail(steps))
    return None


def read_folder(folder):
    with open(os.path.join(folder, "head.json"), encoding="utf-8") as handle:
        head_text = handle.read().rstrip("\n")
    with open(os.path.join(folder, "rows.jsonl"), "rb") as handle:
        rows_bytes = handle.read()
    with open(os.path.join(folder, "frames.bin"), "rb") as handle:
        frames_bytes = handle.read()
    return head_text, rows_bytes, frames_bytes


def read_answer(path):
    """The three parts of an inline answer, each as the bytes that were sent.

    The answer is {"head":{...},"rows":[{...},...],"frames_hex":"..."}. The head and
    each row are cut out of the text as they stand, so the receipt and the hash of
    the rows are those of the bytes received. The rows file is each row on its own line.
    """
    with open(path, "rb") as handle:
        text = handle.read().decode("utf-8")
    outer = json.loads(text)
    if isinstance(outer, dict) and "jsonrpc" in outer:
        text = outer["result"]["content"][0]["text"]
    decoder = json.JSONDecoder()

    def expect(at, literal):
        if not text.startswith(literal, at):
            raise ValueError("this is not a full inline answer: %r was expected at character %d" % (literal, at))
        return at + len(literal)

    at = expect(0, '{"head":')
    _, end = decoder.raw_decode(text, at)
    head_text = text[at:end]
    at = expect(end, ',"rows":[')
    rows = []
    while not text.startswith("]", at):
        _, end = decoder.raw_decode(text, at)
        rows.append(text[at:end])
        at = end + 1 if text.startswith(",", end) else end
    at = expect(at, '],"frames_hex":')
    frames_hex, end = decoder.raw_decode(text, at)
    if not isinstance(frames_hex, str):
        raise ValueError('the answer holds no frames: ask with "store": "frames"')
    rows_bytes = "".join(row + "\n" for row in rows).encode("utf-8")
    return head_text, rows_bytes, bytes.fromhex(frames_hex)


def refuse_v1(head_text, rows_bytes, frames_bytes):
    """Name a dataset of seal rule v1 before any of it is read: its head, a row, or a GKF2 frame file."""
    refuse_other_rule(json.loads(head_text))
    for line in rows_bytes.decode("utf-8").splitlines():
        row = json.loads(line)
        refuse_other_rule(row)
        if isinstance(row, dict):
            refuse_other_rule(row.get("leaf"))
    if frames_bytes[:4] == b"GKF2":
        raise SealRuleNotServed("its frame file starts with GKF2")


def header_holds(frames_bytes, head):
    """The 80-byte header: GKF3, layout 2 (u32), rows (u64), frames (u64), dataset_seal (48 bytes), 8 zero bytes."""
    if len(frames_bytes) < HEADER_LEN:
        return False
    magic, layout, rows, frames = frames_bytes[:4], *struct.unpack("<IQQ", frames_bytes[4:24])
    return (magic == MAGIC and layout == LAYOUT and rows == head["rows"] and frames == head["frames"]
            and frames_bytes[24:72].hex() == head["dataset_seal"] and frames_bytes[72:80] == bytes(8))


def verify(head_text, rows_bytes, frames_bytes, given):
    head_exact = json.loads(head_text, parse_int=float)
    head = json.loads(head_text)
    broken = []

    def report(name, ok, detail=""):
        print("%-14s %s%s" % (name + ":", "holds" if ok else "BROKEN", "  " + detail if detail else ""))
        if not ok:
            broken.append(name)

    plan_hash = sha384_hex(sealed_form(head_exact["request"]).encode("utf-8"))
    report("plan", plan_hash == head["plan_sha384"], plan_hash)

    plan = head["request"].get("plan", {})
    planned = None
    if plan.get("kind") == "list":
        planned = [dict(run, domain=head["request"]["domain"], card=head["request"]["card"])
                   for run in json.loads(json.dumps(head_exact["request"]["plan"]["runs"]))]

    planned_forms = None if planned is None else [sealed_form(run) for run in planned]
    leaves, at, first_break, first_decimal, first_field, read = [], HEADER_LEN, "", "", "", []
    lines = rows_bytes.decode("utf-8").splitlines()
    for number, line in enumerate(lines):
        row_exact, row = json.loads(line, parse_int=float), json.loads(line)
        where = "row %d" % number
        read.append((whole(row.get("row")), sealed_form(row_exact["request"])))
        if not first_decimal:
            found = decimal_not_its_hex(row)
            first_decimal = where + ": " + found if found else ""
        if not first_field:
            found = field_not_written(row)
            first_field = where + ": " + found if found else ""
        request_hash = sha384_hex(sealed_form(row_exact["request"]).encode("utf-8"))
        if planned_forms is not None and (number >= len(planned_forms) or planned_forms[number] != read[-1][1]):
            first_break = first_break or where + ": request is not the plan's"
        link = request_hash
        for _ in range(row["frames"]):
            frame = frames_bytes[at:at + 64]
            at += 64
            if len(frame) != 64 or frame[48:64] != bytes.fromhex(link)[:16]:
                first_break = first_break or where + ": chain"
            link = hashlib.sha384(frame).hexdigest()
        if row["frames"] and link != row["last_link"]:
            first_break = first_break or where + ": chain"
        if row["outcome"] != "unadmitted":
            digest = state_digest(row)
            if digest != row["state_digest"]:
                first_break = first_break or where + ": state"
            tail = json.dumps({"outcome": row["outcome"], "steps_landed": row["steps_landed"],
                               "reject": row["reject"], "state_digest": digest},
                              separators=(",", ":"), ensure_ascii=False)
            if sha384_hex((link + tail).encode("utf-8")) != row["run_seal"]:
                first_break = first_break or where + ": run_seal"
        leaf = leaf_text(number, request_hash, row)
        if json.dumps(row["leaf"], separators=(",", ":"), ensure_ascii=False) != leaf:
            first_break = first_break or where + ": leaf"
        leaves.append(hashlib.sha384(b"\x00" + (leaf or "").encode("utf-8")).digest())
    if at != len(frames_bytes):
        first_break = first_break or "the frames hold frames no row names"
    # A row out of its place is named as such before any break it causes further on.
    first_break = misplaced(read, planned_forms, head["rows"]) or first_break
    report("rows", not first_break and len(lines) == head["rows"],
           first_break or "%d rows%s" % (len(lines), "" if planned is not None else
                                         "; the plan is not a list, so rows were not compared with it"))
    report("decimals", not first_decimal, first_decimal or "each decimal of a final state is the exact value beside it")
    report("fields", not first_field, first_field or "each row has the engine's keys, and a sentence where a run did not complete")

    root = tree_root(leaves).hex() if leaves else None
    report("merkle_root", root == head["merkle_root"], str(root))
    # The counts carry "ended" between "completed" and "refused". A head made
    # before that outcome existed has no "ended", and its counts text has none.
    ended = ',"ended":%d' % head["ended"] if "ended" in head else ""
    counts = ('{"engine_version":%s,"rows":%d,"completed":%d%s,"refused":%d,"unadmitted":%d,"frames":%d}'
              % (json.dumps(head["engine_version"], ensure_ascii=False), head["rows"], head["completed"],
                 ended, head["refused"], head["unadmitted"], head["frames"]))
    seal = sha384_hex((head["plan_sha384"] + str(root) + counts).encode("utf-8"))
    report("dataset_seal", seal == head["dataset_seal"], seal)
    report("rows_hash", hashlib.sha384(rows_bytes).hexdigest() == head["rows_sha384"])
    report("frames_hash", hashlib.sha384(frames_bytes).hexdigest() == head["frames_sha384"])
    report("frames_header", header_holds(frames_bytes, head),
           "GKF3, layout 2, the counts of rows and frames and the dataset seal, 80 bytes")
    given_receipt, made = receipt(head_text)
    report("receipt", given_receipt is not None and given_receipt == made, str(made))
    return result(broken, given.show(given.check(head_text)))


def main(arguments):
    try:
        arguments, given = take_options(arguments)
    except NotRead as e:
        print("not read:", e)
        return 2
    if len(arguments) != 1:
        print(__doc__)
        return 2
    path = arguments[0]
    try:
        parts = read_folder(path) if os.path.isdir(path) else read_answer(path)
        json.loads(parts[0])
        refuse_v1(*parts)
    except SealRuleNotServed as e:
        return say_not_served(e)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        print("not read:", e)
        return 2
    try:
        return verify(*parts, given)
    except (ValueError, KeyError, IndexError, TypeError, NotRead) as e:
        print("not read:", e)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
