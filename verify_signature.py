#!/usr/bin/env python3
"""Verify the engine's signature on any answer, and its receipt, with no engine.

    python3 verify_signature.py answer.json --public-key <file> [--now <time>] [--nonce-ledger <file>]

answer.json is the text an answer of Zero-Trust Physics was sent as, kept byte
for byte: a run, a step, a solve, a dataset (the signature is inside its head),
a comparison or a design. It may also be the whole JSON-RPC message of that
call. --public-key is the engine's public key, the base64 text of its 2,592
bytes; --now is the verifier's clock, YYYY-MM-DDTHH:MM:SSZ (default: this
machine's, UTC); --nonce-ledger is the file of nonces this verifier has seen,
one per line, to which a signature that holds adds its own.

It verifies, in this order, and names the first that does not hold: the form of
the signature (SignatureMalformed), its algorithm, ML-DSA-87
(SignatureAlgorithmNotServed), its key_id against the SHA-384 of the key given
(SignatureKeyMismatch), the receipt over the bytes before it
(ReceiptDoesNotMatch), the ML-DSA-87 equation over the receipt, the times and
the nonce (SignatureDoesNotVerify), the issue time against the clock, 60 s
allowed (SignatureNotYetValid), the expiry (SignatureExpired) and the nonce
against the ledger (SignatureNonceReplayed). An answer with no signature is
SignatureAbsent. It prints the receipt line and the signature lines as
genesis_seal verify-signature prints them. It verifies no seal other than the
receipt: verify_run.py, verify_chain.py and verify_dataset.py verify those, and
take the same options.

Exit code 0: the signature holds. 2: an input was not read. 5: the signature
does not hold, or the answer carries none.

Needs dilithium-py 1.5.1 (pip install dilithium-py==1.5.1), pure Python,
written to FIPS 204 final. Uses answer_signature.py beside it. Released under Apache-2.0.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from answer_signature import NotRead, OPTIONS_HELP, receipt_check, take_options  # noqa: E402


def read_text(path):
    with open(path, "rb") as handle:
        raw = handle.read().decode("utf-8")
    try:
        outer = json.loads(raw)
    except ValueError:
        return raw
    if isinstance(outer, dict) and "jsonrpc" in outer:
        return outer["result"]["content"][0]["text"]
    return raw


def main(arguments):
    try:
        arguments, given = take_options(arguments)
        if len(arguments) != 1 or given.key is None:
            print(__doc__ + "\n" + OPTIONS_HELP)
            return 2
        text = read_text(arguments[0])
    except NotRead as e:
        print("not read:", e)
        return 2
    except (OSError, UnicodeDecodeError, KeyError, IndexError, TypeError) as e:
        print("not read:", e)
        return 2
    report = given.check(text)
    print("receipt: %s" % receipt_check(text))
    try:
        fails = given.show(report)
    except NotRead as e:
        print("not read:", e)
        return 2
    return 5 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
