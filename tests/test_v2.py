#!/usr/bin/env python3
"""The verifiers here under seal rule v2 and the engine's signature, each case named, each held to genesis_seal.

    pip install dilithium-py==1.5.1
    GENESIS_SEAL=<path to the genesis_seal program, 0.7.0 or later> python3 -m unittest discover -s tests -v

What it checks: a v2 run, chain and dataset hold; the signed run in
examples/answers holds with its key at a time inside its window; a forged
signature (another key's value) is SignatureDoesNotVerify; an expired one
SignatureExpired; a nonce already in the ledger SignatureNonceReplayed; a
decimal changed after signing ReceiptDoesNotMatch, and with the receipt made
again SignatureDoesNotVerify; the wrong key SignatureKeyMismatch; an unsigned
answer checked with a key SignatureAbsent; a record of seal rule v1
SealRuleNotServed, exit code 2. For every case it runs genesis_seal on the same
file with the same options and compares the exit code and every signature_cause
line. Without GENESIS_SEAL the comparisons are skipped and said so.

With GENESIS_SEAL_VECTORS (the genesis_seal crate's vectors folder, holding
outside_check_v2.py) and ZERO_TRUST_PHYSICS_RUNS (the saved runs of seal rule
v2) it also builds a two-row dataset from two saved LAGEOS-1 runs and holds
verify_dataset.py and genesis_seal verify-dataset to it.

The keys here are made from fixed labelled test seeds, the first 32 bytes of
SHA-384 of "a test answer key, never an operator's: <label>", as the engine's
own tests make theirs. They are test keys, never an operator's.
"""
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ANSWERS = os.path.join(ROOT, "examples", "answers")
FIXTURES = os.path.join(HERE, "fixtures")
PROGRAM = os.environ.get("GENESIS_SEAL")
VECTORS = os.environ.get("GENESIS_SEAL_VECTORS")
RUNS = os.environ.get("ZERO_TRUST_PHYSICS_RUNS")

sys.path.insert(0, ROOT)
import answer_signature  # noqa: E402

from dilithium_py.ml_dsa import ML_DSA_87  # noqa: E402

# The signed run's window: issued 2026-10-19T19:37:32Z, expires 2026-10-19T20:37:32Z.
INSIDE = "2026-10-19T20:00:00Z"
AFTER = "2026-10-19T20:37:33Z"
BEFORE = "2026-10-19T19:36:31Z"
# The issue time of the signatures made here.
ISSUED = answer_signature.parse_time("2026-10-18T21:04:05Z")


def test_key(label):
    """A test answer key from a labelled seed, never an operator's: (public key, signing key)."""
    seed = hashlib.sha384(("a test answer key, never an operator's: %s" % label).encode()).digest()[:32]
    return ML_DSA_87.key_derive(seed)


def sign_text(text, keys, issued_s, ttl_s, nonce):
    """text, an unsigned answer ending with its receipt, with the signature written after the
    receipt, as the engine writes it (ML-DSA-87, deterministic, empty context)."""
    public, secret = keys
    mark = '"receipt_sha384":"'
    at = text.index(mark) + len(mark)
    receipt = text[at:at + 96]
    envelope = {
        "alg": "ML-DSA-87",
        "key_id": hashlib.sha384(public).hexdigest(),
        "issued_at": answer_signature.format_time(issued_s),
        "expires_at": answer_signature.format_time(issued_s + ttl_s),
        "nonce": nonce.hex(),
    }
    signed = answer_signature.message(envelope["key_id"], receipt, envelope["issued_at"], envelope["expires_at"],
                                      envelope["nonce"])
    envelope["value"] = base64.b64encode(ML_DSA_87.sign(secret, signed.encode(), deterministic=True)).decode()
    block = ',"signature":' + json.dumps(envelope, separators=(",", ":"))
    return text[:at + 97] + block + text[at + 97:]


def with_receipt(document):
    """The wire body of a document: its receipt inserted before the closing brace."""
    return document[:-1] + ',"receipt_sha384":"%s"}' % hashlib.sha384(document.encode()).hexdigest()


def read(name, folder=ANSWERS):
    with open(os.path.join(folder, name), encoding="utf-8") as handle:
        return handle.read()


def lines(out):
    fields = {}
    for line in out.splitlines():
        name, _, value = line.partition(": ")
        fields.setdefault(name.strip(), value.strip())
    return fields


def causes(out):
    """Every signature_cause line, by its place: {"": cause} or {"links[0].": cause, ...}."""
    found = {}
    for line in out.splitlines():
        name, _, value = line.partition(": ")
        if name.endswith("signature_cause"):
            found[name[:-len("signature_cause")]] = value.strip()
    return found


def python(script, *arguments):
    done = subprocess.run([sys.executable, os.path.join(ROOT, script), *arguments], capture_output=True, text=True)
    return done.returncode, done.stdout


def program(*arguments):
    done = subprocess.run([PROGRAM, *arguments], capture_output=True, text=True)
    return done.returncode, done.stdout


class V2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.mkdtemp(prefix="ztp_test_v2_")
        cls.engine = test_key("engine")
        cls.other = test_key("two")
        cls.signed_run = read("run_signed.json")
        cls.key_file = os.path.join(ANSWERS, "test_key.pub")
        cls.other_file = cls.write("other.pub", base64.b64encode(cls.other[0]).decode())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.scratch, ignore_errors=True)

    @classmethod
    def write(cls, name, text, binary=False):
        path = os.path.join(cls.scratch, name)
        with open(path, "wb" if binary else "w") as handle:
            handle.write(text)
        return path

    def both(self, script, command, files, options, code, cause, place=""):
        """Run the script and genesis_seal on the same files with the same options; both must exit with
        code and name cause (None: no cause) at place, and agree on every signature_cause line."""
        mine, out = python(script, *files, *options)
        self.assertEqual(mine, code, out)
        self.assertEqual(causes(out).get(place), cause, out)
        if PROGRAM is None:
            print("  (genesis_seal not compared: set GENESIS_SEAL)", file=sys.stderr)
            return out
        theirs, their_out = program(command, *files, *options)
        self.assertEqual(theirs, code, their_out)
        self.assertEqual(causes(their_out), causes(out), their_out)
        return out

    # ---- What holds ----

    def test_a_v2_run_holds(self):
        out = self.both("verify_run.py", "verify-run", [os.path.join(ANSWERS, "run.json")], [], 0, None)
        self.assertIn("result: every proof holds", out)
        self.assertNotIn("signature", out)

    def test_a_v2_chain_holds_as_two_answers_and_as_links(self):
        code, out = python("verify_chain.py", os.path.join(ANSWERS, "chain_1.json"), os.path.join(ANSWERS, "chain_2.json"))
        self.assertEqual(code, 0, out)
        body = self.write("chain.json", '{"links":[%s,%s]}' % (read("chain_1.json"), read("chain_2.json")))
        out = self.both("verify_chain.py", "verify-chain", [body], [], 0, None)
        if PROGRAM:
            _, theirs = program("verify-chain", body)
            self.assertIn(lines(theirs)["chain_seal"], out)

    def test_a_signed_chain_holds_link_by_link(self):
        first = sign_text(read("chain_1.json"), self.engine, ISSUED, 3600, bytes([1]) * 32)
        second = sign_text(read("chain_2.json"), self.engine, ISSUED, 3600, bytes([2]) * 32)
        body = self.write("signed_chain.json", '{"links":[%s,%s]}' % (first, second))
        key = self.write("engine.pub", base64.b64encode(self.engine[0]).decode())
        out = self.both("verify_chain.py", "verify-chain", [body], ["--public-key", key, "--now", "2026-10-18T21:30:00Z"], 0, None)
        self.assertIn("links[1].signature: holds", out)
        # The second link's value changed after signing: that link's receipt no longer matches.
        self.assertIn('"record_every":100', second)
        changed = self.write("signed_chain_changed.json", '{"links":[%s,%s]}' % (
            first, second.replace('"record_every":100', '"record_every":100 ', 1)))
        self.both("verify_chain.py", "verify-chain", [changed], ["--public-key", key, "--now", "2026-10-18T21:30:00Z"],
                  5, "ReceiptDoesNotMatch", "links[1].")

    def test_a_v2_dataset_holds_inline_and_as_files(self):
        code, out = python("verify_dataset.py", os.path.join(ANSWERS, "dataset.json"))
        self.assertEqual(code, 0, out)
        folder = self.inline_to_folder(read("dataset.json"), "inline_dataset")
        self.dataset_both(folder, [], 0, None)

    def test_a_signed_head_holds_and_expires(self):
        folder = self.inline_to_folder(read("dataset.json"), "signed_dataset")
        head_path = os.path.join(folder, "head.json")
        with open(head_path) as handle:
            head = handle.read()
        with open(head_path, "w") as handle:
            handle.write(sign_text(head, self.engine, ISSUED, 3600, bytes([3]) * 32))
        key = self.write("engine.pub", base64.b64encode(self.engine[0]).decode())
        out = self.dataset_both(folder, ["--public-key", key, "--now", "2026-10-18T21:30:00Z"], 0, None)
        self.assertIn("signature: holds", out)
        self.dataset_both(folder, ["--public-key", key, "--now", "2026-10-18T22:04:06Z"], 5, "SignatureExpired")

    def test_a_dataset_built_from_two_saved_runs_holds(self):
        if not (VECTORS and RUNS):
            self.skipTest("set GENESIS_SEAL_VECTORS and ZERO_TRUST_PHYSICS_RUNS to build a dataset from saved runs")
        sys.path.insert(0, VECTORS)
        import outside_check_v2
        folder = os.path.join(RUNS, "satellite_lageos1_validation")
        tapes = []
        for name in ("sealed_lageos1_260912_d6_1356_steps.json", "sealed_lageos1_260919_d6_1356_steps.json"):
            with open(os.path.join(folder, name), "rb") as handle:
                tapes.append(json.loads(handle.read()))
        made = outside_check_v2.build_dataset(tapes, True)
        out_folder = os.path.join(self.scratch, "lageos1_two_rows")
        os.makedirs(out_folder, exist_ok=True)
        for part, name in (("head", "head.json"), ("rows", "rows.jsonl"), ("frames", "frames.bin")):
            with open(os.path.join(out_folder, name), "wb") as handle:
                handle.write(made[part])
        out = self.dataset_both(out_folder, [], 0, None)
        self.assertIn(made["seal"], out)
        self.assertIn(made["root"], out)
        if PROGRAM:
            _, theirs = program("verify-dataset", *self.dataset_files(out_folder))
            self.assertEqual(lines(theirs)["dataset_seal"], made["seal"])
        # One byte of a frame changed: both name the chain of row 1.
        frames = bytearray(made["frames"])
        frames[80 + 64 * (len(frames[80:]) // 128) + 5] ^= 1
        with open(os.path.join(out_folder, "frames.bin"), "wb") as handle:
            handle.write(bytes(frames))
        code, out = python("verify_dataset.py", out_folder)
        self.assertEqual(code, 1, out)
        self.assertIn("row 1: chain", out)
        if PROGRAM:
            theirs, their_out = program("verify-dataset", *self.dataset_files(out_folder))
            self.assertEqual((theirs, lines(their_out)["cause"], lines(their_out)["row"]), (1, "chain", "1"), their_out)

    # ---- The signature ----

    def test_the_signed_run_holds_with_its_key_inside_its_window(self):
        key_id = hashlib.sha384(base64.b64decode(read("test_key.pub"))).hexdigest()
        self.assertIn('"key_id":"%s"' % key_id, self.signed_run)
        out = self.both("verify_run.py", "verify-run", [os.path.join(ANSWERS, "run_signed.json")],
                        ["--public-key", self.key_file, "--now", INSIDE], 0, None)
        self.assertIn("signature: holds", out)
        self.assertIn("key_id: " + key_id, out)
        self.both("verify_signature.py", "verify-signature", [os.path.join(ANSWERS, "run_signed.json")],
                  ["--public-key", self.key_file, "--now", INSIDE], 0, None)

    def test_a_signed_answer_with_no_key_is_reported_not_checked(self):
        out = self.both("verify_run.py", "verify-run", [os.path.join(ANSWERS, "run_signed.json")], [], 0, None)
        self.assertIn("signature: not checked", out)

    def test_a_forged_signature_does_not_verify(self):
        unsigned = read("run.json")
        by_other = sign_text(unsigned, self.other, ISSUED, 3600, bytes([7]) * 32)
        other_value = answer_signature.split(by_other)["envelope"]["value"]
        mine = answer_signature.split(self.signed_run)["envelope"]["value"]
        forged = self.write("forged.json", self.signed_run.replace(mine, other_value))
        self.both("verify_run.py", "verify-run", [forged], ["--public-key", self.key_file, "--now", INSIDE],
                  5, "SignatureDoesNotVerify")
        self.both("verify_signature.py", "verify-signature", [forged], ["--public-key", self.key_file, "--now", INSIDE],
                  5, "SignatureDoesNotVerify")

    def test_an_expired_signature_is_named(self):
        self.both("verify_run.py", "verify-run", [os.path.join(ANSWERS, "run_signed.json")],
                  ["--public-key", self.key_file, "--now", AFTER], 5, "SignatureExpired")

    def test_a_signature_issued_ahead_of_the_clock_is_named(self):
        self.both("verify_run.py", "verify-run", [os.path.join(ANSWERS, "run_signed.json")],
                  ["--public-key", self.key_file, "--now", BEFORE], 5, "SignatureNotYetValid")

    def test_a_replayed_nonce_is_named_through_the_ledger(self):
        for ledger_of in ("python", "program"):
            ledger = os.path.join(self.scratch, "ledger_%s.txt" % ledger_of)
            if os.path.exists(ledger):
                os.remove(ledger)
            run = python if ledger_of == "python" else program
            if run is program and PROGRAM is None:
                continue
            first = ("verify_run.py",) if run is python else ("verify-run",)
            options = [os.path.join(ANSWERS, "run_signed.json"), "--public-key", self.key_file, "--now", INSIDE,
                       "--nonce-ledger", ledger]
            code, out = run(*first, *options)
            self.assertEqual(code, 0, out)
            with open(ledger) as handle:
                nonce = answer_signature.split(self.signed_run)["envelope"]["nonce"]
                self.assertEqual(handle.read(), nonce + "\n")
        # A ledger that holds the nonce: both name it replayed.
        ledger = self.write("ledger_seen.txt", answer_signature.split(self.signed_run)["envelope"]["nonce"] + "\n")
        self.both("verify_run.py", "verify-run", [os.path.join(ANSWERS, "run_signed.json")],
                  ["--public-key", self.key_file, "--now", INSIDE, "--nonce-ledger", ledger], 5, "SignatureNonceReplayed")

    def test_a_decimal_changed_after_signing_breaks_the_receipt_then_the_signature(self):
        decimal = '"temperature_k":2.9315169240523e2'
        self.assertEqual(self.signed_run.count(decimal), 1)
        tampered_text = self.signed_run.replace(decimal, '"temperature_k":2.9315169240524e2')
        tampered = self.write("tampered.json", tampered_text)
        self.both("verify_run.py", "verify-run", [tampered], ["--public-key", self.key_file, "--now", INSIDE],
                  5, "ReceiptDoesNotMatch")
        # The receipt made again over the changed bytes: the signature is over the old receipt.
        found = answer_signature.split(tampered_text)
        unsigned = found["unsigned"]
        document = unsigned[:unsigned.rindex(',"receipt_sha384":"')] + "}"
        rewritten_unsigned = with_receipt(document)
        envelope = json.dumps(found["envelope"], separators=(",", ":"))
        rewritten = self.write("rewritten.json", rewritten_unsigned[:-1] + ',"signature":' + envelope + "}")
        out = self.both("verify_run.py", "verify-run", [rewritten], ["--public-key", self.key_file, "--now", INSIDE],
                        5, "SignatureDoesNotVerify")
        self.assertIn("receipt:       holds", out)

    def test_the_wrong_key_is_named(self):
        self.both("verify_run.py", "verify-run", [os.path.join(ANSWERS, "run_signed.json")],
                  ["--public-key", self.other_file, "--now", INSIDE], 5, "SignatureKeyMismatch")

    def test_an_unsigned_answer_checked_with_a_key_is_absent(self):
        out = self.both("verify_run.py", "verify-run", [os.path.join(ANSWERS, "run.json")],
                        ["--public-key", self.key_file, "--now", INSIDE], 5, "SignatureAbsent")
        self.assertIn("signature: absent", out)
        self.both("verify_signature.py", "verify-signature", [os.path.join(ANSWERS, "run.json")],
                  ["--public-key", self.key_file, "--now", INSIDE], 5, "SignatureAbsent")

    def test_a_signature_not_of_the_form_and_another_algorithm_are_named(self):
        malformed = self.write("malformed.json", self.signed_run.replace('"alg":"ML-DSA-87",', ""))
        self.both("verify_run.py", "verify-run", [malformed], ["--public-key", self.key_file, "--now", INSIDE],
                  5, "SignatureMalformed")
        other_alg = self.write("other_alg.json", self.signed_run.replace('"alg":"ML-DSA-87"', '"alg":"ML-DSA-65"'))
        self.both("verify_run.py", "verify-run", [other_alg], ["--public-key", self.key_file, "--now", INSIDE],
                  5, "SignatureAlgorithmNotServed")

    def test_the_engines_signature_verifies_under_dilithium_py_and_a_changed_byte_does_not(self):
        """The engine's ML-DSA-87 signature (RustCrypto ml-dsa 0.1.1) verifies here; one byte more does not."""
        seen = answer_signature.split(self.signed_run)
        public = base64.b64decode(read("test_key.pub"))
        self.assertEqual(len(public), 2592)
        envelope = seen["envelope"]
        signed = answer_signature.message(envelope["key_id"], seen["receipt"], envelope["issued_at"],
                                          envelope["expires_at"], envelope["nonce"])
        self.assertTrue(ML_DSA_87.verify(public, signed.encode(), base64.b64decode(envelope["value"])))
        self.assertFalse(ML_DSA_87.verify(public, signed.encode() + b" ", base64.b64decode(envelope["value"])))

    # ---- Seal rule v1 ----

    def test_a_v1_record_is_not_read(self):
        out = self.both("verify_run.py", "verify-run", [os.path.join(FIXTURES, "v1_run.json")], [], 2, None)
        self.assertIn("cause: SealRuleNotServed", out)
        self.assertIn(answer_signature.SEAL_RULE_V1_SENTENCE, out)
        out = self.both("verify_chain.py", "verify-chain", [os.path.join(FIXTURES, "v1_chain.json")], [], 2, None)
        self.assertIn("cause: SealRuleNotServed", out)
        if PROGRAM:
            _, theirs = program("verify-run", os.path.join(FIXTURES, "v1_run.json"))
            self.assertEqual(lines(theirs)["cause"], "SealRuleNotServed")

    def test_another_seal_rule_and_a_gkf2_frame_file_are_not_read(self):
        other = self.write("other_rule.json", read("run.json").replace("zero-trust-physics/seal/v2", "zero-trust-physics/seal/v3"))
        out = self.both("verify_run.py", "verify-run", [other], [], 2, None)
        self.assertIn("cause: SealRuleNotServed", out)
        folder = self.inline_to_folder(read("dataset.json"), "gkf2")
        path = os.path.join(folder, "frames.bin")
        with open(path, "rb") as handle:
            frames = handle.read()
        with open(path, "wb") as handle:
            handle.write(b"GKF2" + frames[4:])
        code, out = python("verify_dataset.py", folder)
        self.assertEqual(code, 2, out)
        self.assertIn("cause: SealRuleNotServed", out)

    # ---- Helpers ----

    def inline_to_folder(self, text, name):
        """The three files of an inline dataset answer, cut from its text as they stand."""
        sys.path.insert(0, ROOT)
        import verify_dataset
        path = self.write(name + ".json", text)
        head, rows, frames = verify_dataset.read_answer(path)
        folder = os.path.join(self.scratch, name)
        os.makedirs(folder, exist_ok=True)
        for file_name, data in (("head.json", head.encode()), ("rows.jsonl", rows), ("frames.bin", frames)):
            with open(os.path.join(folder, file_name), "wb") as handle:
                handle.write(data)
        return folder

    @staticmethod
    def dataset_files(folder):
        return [os.path.join(folder, name) for name in ("head.json", "rows.jsonl", "frames.bin")]

    def dataset_both(self, folder, options, code, cause):
        mine, out = python("verify_dataset.py", folder, *options)
        self.assertEqual(mine, code, out)
        self.assertEqual(causes(out).get(""), cause, out)
        if PROGRAM:
            theirs, their_out = program("verify-dataset", *self.dataset_files(folder), *options)
            self.assertEqual(theirs, code, their_out)
            self.assertEqual(causes(their_out), causes(out), their_out)
        return out


if __name__ == "__main__":
    unittest.main()
