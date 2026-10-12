#!/usr/bin/env python3
"""Verify a dataset of runs with no engine.

    python3 verify_dataset.py answer.json    # a run_dataset answer asked with "answer": "full"
    python3 verify_dataset.py <folder>       # a folder holding head.json, rows.jsonl and frames.bin

In the first form the file is the text a run_dataset call to Zero-Trust Physics
returned, kept byte for byte, when the request asked "store": "frames",
"return": "inline" and "answer": "full": its head, every row whole and
frames_hex. It may also be the whole JSON-RPC message of that call. In the
second form the folder holds the same three parts as files.

It verifies the plan hash, the request of every row against a list plan, every
row's chain of frames, state digest, run seal and leaf, the row tree (RFC 6962),
the dataset seal, the two hashes of the rows and the frames, and the head's
receipt, and prints one line for each. Exit code 0: every proof holds. 1: a
proof is broken. 2: not read.

A grid or a sample plan is expanded by rules this script does not hold: for
those it verifies every proof and says that the rows were not compared with the
plan. A plan of solves is not read here.

The rules are the code below, each in a few lines. Python standard
library only; it uses verify_run.py beside it. Released under Apache-2.0.
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_run import receipt, sealed_form, sha256_hex, state_digest  # noqa: E402


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
    return hashlib.sha256(b"\x01" + tree_root(leaves[:at]) + tree_root(leaves[at:])).digest()


def read_folder(folder):
    head_text = open(os.path.join(folder, "head.json"), encoding="utf-8").read().rstrip("\n")
    rows_bytes = open(os.path.join(folder, "rows.jsonl"), "rb").read()
    frames_bytes = open(os.path.join(folder, "frames.bin"), "rb").read()
    return head_text, rows_bytes, frames_bytes


def read_answer(path):
    """The three parts of an inline answer, each as the bytes that were sent.

    The answer is {"head":{...},"rows":[{...},...],"frames_hex":"..."}. The head and
    each row are cut out of the text as they stand, so the receipt and the hash of
    the rows are those of the bytes received. The rows file is each row on its own line.
    """
    text = open(path, "rb").read().decode("utf-8")
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


def verify(head_text, rows_bytes, frames_bytes):
    head_exact = json.loads(head_text, parse_int=float)
    head = json.loads(head_text)
    broken = []

    def report(name, ok, detail=""):
        print("%-14s %s%s" % (name + ":", "holds" if ok else "BROKEN", "  " + detail if detail else ""))
        if not ok:
            broken.append(name)

    plan_hash = sha256_hex(sealed_form(head_exact["request"]).encode("utf-8"))
    report("plan", plan_hash == head["plan_sha256"], plan_hash)

    plan = head["request"].get("plan", {})
    planned = None
    if plan.get("kind") == "list":
        planned = [dict(run, domain=head["request"]["domain"], card=head["request"]["card"])
                   for run in json.loads(json.dumps(head_exact["request"]["plan"]["runs"]))]

    leaves, at, first_break = [], 64, ""
    lines = rows_bytes.decode("utf-8").splitlines()
    for number, line in enumerate(lines):
        row_exact, row = json.loads(line, parse_int=float), json.loads(line)
        where = "row %d" % number
        request_hash = sha256_hex(sealed_form(row_exact["request"]).encode("utf-8"))
        if planned is not None and (number >= len(planned) or
                                    sealed_form(planned[number]) != sealed_form(row_exact["request"])):
            first_break = first_break or where + ": request is not the plan's"
        link = request_hash
        for _ in range(row["frames"]):
            frame = frames_bytes[at:at + 64]
            at += 64
            if len(frame) != 64 or frame[48:64] != bytes.fromhex(link)[:16]:
                first_break = first_break or where + ": chain"
            link = hashlib.sha256(frame).hexdigest()
        if row["frames"] and link != row["last_link"]:
            first_break = first_break or where + ": chain"
        if row["outcome"] != "unadmitted":
            digest = state_digest(row)
            if digest != row["state_digest"]:
                first_break = first_break or where + ": state"
            tail = json.dumps({"outcome": row["outcome"], "steps_landed": row["steps_landed"],
                               "reject": row["reject"], "state_digest": digest},
                              separators=(",", ":"), ensure_ascii=False)
            if sha256_hex((link + tail).encode("utf-8")) != row["run_seal"]:
                first_break = first_break or where + ": run_seal"
        leaf = json.dumps({"row": number, "request_sha256": request_hash, "outcome": row["outcome"],
                           "run_seal": row["run_seal"]}, separators=(",", ":"), ensure_ascii=False)
        if json.dumps(row["leaf"], separators=(",", ":"), ensure_ascii=False) != leaf:
            first_break = first_break or where + ": leaf"
        leaves.append(hashlib.sha256(b"\x00" + leaf.encode("utf-8")).digest())
    if at != len(frames_bytes):
        first_break = first_break or "the frames hold frames no row names"
    report("rows", not first_break and len(lines) == head["rows"],
           first_break or "%d rows%s" % (len(lines), "" if planned is not None else
                                         "; the plan is not a list, so rows were not compared with it"))

    root = tree_root(leaves).hex() if leaves else None
    report("merkle_root", root == head["merkle_root"], str(root))
    # The counts carry "ended" between "completed" and "refused". A head made
    # before that outcome existed has no "ended", and its counts text has none.
    ended = ',"ended":%d' % head["ended"] if "ended" in head else ""
    counts = ('{"engine_version":%s,"rows":%d,"completed":%d%s,"refused":%d,"unadmitted":%d,"frames":%d}'
              % (json.dumps(head["engine_version"], ensure_ascii=False), head["rows"], head["completed"],
                 ended, head["refused"], head["unadmitted"], head["frames"]))
    seal = sha256_hex((head["plan_sha256"] + str(root) + counts).encode("utf-8"))
    report("dataset_seal", seal == head["dataset_seal"], seal)
    report("rows_hash", hashlib.sha256(rows_bytes).hexdigest() == head["rows_sha256"])
    report("frames_hash", hashlib.sha256(frames_bytes).hexdigest() == head["frames_sha256"]
           and frames_bytes[:4] == b"GKF2" and frames_bytes[24:56].hex() == head["dataset_seal"])
    given, made = receipt(head_text)
    report("receipt", given is not None and given == made, str(made))
    print("result:", "every proof holds" if not broken else "broken: " + ", ".join(broken))
    return 0 if not broken else 1


def main(path):
    try:
        parts = read_folder(path) if os.path.isdir(path) else read_answer(path)
        json.loads(parts[0])
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        print("not read:", e)
        return 2
    try:
        return verify(*parts)
    except (ValueError, KeyError, IndexError, TypeError) as e:
        print("not read:", e)
        return 2


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
