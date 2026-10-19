#!/usr/bin/env python3
"""The engine's signature on an answer, and the receipt it signs: the rules shared by the verifiers here.

A computed answer of seal rule v2 ends with its receipt, "receipt_sha384":"<96 hex>",
the SHA-384 of every byte before it. An engine given an answer key writes its
signature right after the receipt, in the same object:

    ...,"seal_rule":"zero-trust-physics/seal/v2","receipt_sha384":"<96 hex>","signature":{"alg":"ML-DSA-87","key_id":"<96 hex>","issued_at":"2026-10-18T21:04:05Z","expires_at":"2026-10-18T22:04:05Z","nonce":"<64 hex>","value":"<base64>"}}

The answer with ,"signature":{...} taken out is the unsigned answer, byte for
byte, and its receipt covers every byte of it. The signed message is these six
lines, each ended by a line break:

    zero-trust-physics/answer-signature/v1
    key_id:<96 hex>
    receipt_sha384:<96 hex>
    issued_at:<YYYY-MM-DDTHH:MM:SSZ>
    expires_at:<YYYY-MM-DDTHH:MM:SSZ>
    nonce:<64 hex>

signed by ML-DSA-87 (FIPS 204) with an empty context string. key_id is the
SHA-384 of the 2,592-byte public key.

check() runs the checks in this order and names the first that does not hold:
SignatureMalformed, SignatureAlgorithmNotServed, SignatureKeyNotGiven,
SignatureKeyMismatch, ReceiptDoesNotMatch, SignatureDoesNotVerify,
SignatureNotYetValid (issued_at later than the verifier's clock by more than 60 s),
SignatureExpired (the clock past expires_at), SignatureNonceReplayed (a nonce in
the verifier's ledger). An unsigned answer checked with a key is SignatureAbsent;
with no key it is not checked. These are the names and the order of
genesis_seal::answer_signature::check, the engine's own.

SHA-384 is Python's hashlib. The ML-DSA-87 equation is dilithium-py 1.5.1
(pip install dilithium-py==1.5.1): pure Python, written to FIPS 204 final, not
validated under FIPS 140-3; here it only verifies public data. It is imported
only when a public key is given.

Released under Apache-2.0.
"""
import base64
import hashlib
import os

SEAL_RULE = "zero-trust-physics/seal/v2"
ALGORITHM = "ML-DSA-87"
MESSAGE_TAG = "zero-trust-physics/answer-signature/v1"
PUBLIC_KEY_LEN = 2592
SIGNATURE_LEN = 4627
NONCE_LEN = 32
CLOCK_ALLOWANCE_S = 60
RECEIPT_KEY = "receipt_sha384"
SIGNATURE_KEY = "signature"
FIELDS = ("alg", "key_id", "issued_at", "expires_at", "nonce", "value")
HEX = set("0123456789abcdef")
LIBRARY = "dilithium-py==1.5.1"

SENTENCES = {
    "SignatureAbsent": "The answer carries no signature, and a public key was given to check one with.",
    "SignatureMalformed": "The signature is not of the form: alg, key_id (96 hex digits), issued_at and expires_at (YYYY-MM-DDTHH:MM:SSZ), nonce (64 hex digits) and value (the base64 of 4,627 bytes), in that order, right after the receipt.",
    "SignatureAlgorithmNotServed": "The signature names an algorithm other than ML-DSA-87, the one the engine signs with.",
    "SignatureKeyNotGiven": "No public key was given to check the signature with.",
    "SignatureKeyMismatch": "The signature's key_id is not the SHA-384 of the public key given: it was made by another key, or claims to be.",
    "ReceiptDoesNotMatch": "The bytes before the receipt do not hash to it: the answer was changed after it was signed.",
    "SignatureDoesNotVerify": "The ML-DSA-87 signature does not verify over the receipt, the times and the nonce under the public key given.",
    "SignatureNotYetValid": "The signature's issue time is later than the verifier's clock.",
    "SignatureExpired": "The signature has expired: the verifier's clock is past its expires_at.",
    "SignatureNonceReplayed": "The signature's nonce is one the verifier has already seen: the answer was delivered before.",
}


class NotRead(Exception):
    """An input that is not read: a key, a time or a ledger that is not of the form."""


def sha384_hex(data: bytes) -> str:
    return hashlib.sha384(data).hexdigest()


def is_lower_hex(text, digits):
    return isinstance(text, str) and len(text) == digits and set(text) <= HEX


# ---- Times, YYYY-MM-DDTHH:MM:SSZ ----

def _days_from_civil(year, month, day):
    year = year - 1 if month <= 2 else year
    era = year // 400
    yoe = year - era * 400
    mp = (month + 9) % 12
    doy = (153 * mp + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _civil_from_days(days):
    z = days + 719468
    era = z // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    day = doy - (153 * mp + 2) // 5 + 1
    month = mp + 3 if mp < 10 else mp - 9
    return yoe + era * 400 + (1 if month <= 2 else 0), month, day


def format_time(seconds):
    days, rest = divmod(seconds, 86400)
    year, month, day = _civil_from_days(days)
    return "%04d-%02d-%02dT%02d:%02d:%02dZ" % (year, month, day, rest // 3600, (rest % 3600) // 60, rest % 60)


def parse_time(text):
    """Seconds since 1970-01-01T00:00:00Z of a time written YYYY-MM-DDTHH:MM:SSZ, or None."""
    if not isinstance(text, str) or len(text) != 20:
        return None
    for at, mark in ((4, "-"), (7, "-"), (10, "T"), (13, ":"), (16, ":"), (19, "Z")):
        if text[at] != mark:
            return None
    parts = [text[0:4], text[5:7], text[8:10], text[11:13], text[14:16], text[17:19]]
    if not all(part.isascii() and part.isdigit() for part in parts):
        return None
    year, month, day, hour, minute, second = (int(part) for part in parts)
    if year < 1970 or not 1 <= month <= 12 or day < 1 or hour > 23 or minute > 59 or second > 59:
        return None
    seconds = _days_from_civil(year, month, day) * 86400 + hour * 3600 + minute * 60 + second
    return seconds if format_time(seconds) == text else None


# ---- The receipt ----

def _canonical_base64(text):
    """The bytes of standard padded base64, or None for any other text (as the engine's decoder reads it)."""
    try:
        data = base64.b64decode(text, validate=True)
    except (ValueError, TypeError):
        return None
    return data if base64.b64encode(data).decode("ascii") == text else None


def _read_unsigned(text):
    """(stated, recomputed) of a text ending ,"receipt_sha384":"<96 hex>"}, or None."""
    mark = ',"%s":"' % RECEIPT_KEY
    tail_len = len(mark) + 96 + 2
    data = text.encode("utf-8")
    if len(data) < tail_len + 1:
        return None
    head, tail = data[:-tail_len], data[-tail_len:]
    if not tail.startswith(mark.encode()) or not tail.endswith(b'"}'):
        return None
    stated = tail[len(mark):-2].decode("ascii", "replace")
    if not is_lower_hex(stated, 96):
        return None
    return stated, sha384_hex(head + b"}")


def read_receipt(text):
    """The receipt the text states and the receipt its bytes make, a signature after it split off
    first: (stated, recomputed), or None when the text does not end with a receipt."""
    if '","signature":{' in text:
        try:
            found = split(text)
        except Malformed:
            found = None
        if found is not None:
            return _read_unsigned(found["unsigned"])
    return _read_unsigned(text)


def receipt_check(text):
    """matches, does not match or absent, as genesis_seal prints it."""
    read = read_receipt(text)
    if read is None:
        return "absent"
    return "matches" if read[0] == read[1] else "does not match"


# ---- The signature ----

class Malformed(Exception):
    pass


def message(key_id, receipt, issued_at, expires_at, nonce):
    return "%s\nkey_id:%s\n%s:%s\nissued_at:%s\nexpires_at:%s\nnonce:%s\n" % (
        MESSAGE_TAG, key_id, RECEIPT_KEY, receipt, issued_at, expires_at, nonce)


def _read_envelope(obj):
    """The six fields of a signature object written as the engine writes it, or None."""
    if not (obj.startswith("{") and obj.endswith("}")):
        return None
    rest = obj[1:-1]
    values = {}
    for index, key in enumerate(FIELDS):
        if index > 0:
            if not rest.startswith(","):
                return None
            rest = rest[1:]
        lead = '"%s":"' % key
        if not rest.startswith(lead):
            return None
        rest = rest[len(lead):]
        close = rest.find('"')
        if close < 0 or "\\" in rest[:close]:
            return None
        values[key] = rest[:close]
        rest = rest[close + 1:]
    if rest:
        return None
    form = (is_lower_hex(values["key_id"], 96) and is_lower_hex(values["nonce"], 2 * NONCE_LEN)
            and parse_time(values["issued_at"]) is not None and parse_time(values["expires_at"]) is not None
            and values["alg"] != "")
    return values if form else None


def split(text):
    """The text split at its signature: {"unsigned", "envelope" (None when not of the form), "receipt"},
    or None when it carries none. Raises Malformed when "signature" follows a receipt in a form that
    is not the engine's, or follows more than one receipt."""
    mark = '"%s":"' % RECEIPT_KEY
    follow = '","%s":' % SIGNATURE_KEY
    found = None
    at = text.find(mark)
    while at >= 0:
        start = at + len(mark)
        at = text.find(mark, start)
        receipt = text[start:start + 96]
        if not is_lower_hex(receipt, 96):
            continue
        after = start + 96
        if not text.startswith(follow, after):
            continue
        if found is not None:
            raise Malformed()
        block_at = after + 1
        object_at = after + len(follow)
        close = text.find("}", object_at)
        if close < 0:
            raise Malformed()
        found = {"unsigned": text[:block_at] + text[close + 1:],
                 "envelope": _read_envelope(text[object_at:close + 1]),
                 "receipt": receipt}
    if found is None and ('"%s":{"alg"' % SIGNATURE_KEY) in text:
        raise Malformed()
    return found


def _opening_brace(text, at):
    stack, in_string, escaped = [], False, False
    for index, char in enumerate(text[:at]):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append((char, index))
        elif char in "}]":
            if stack:
                stack.pop()
    for char, index in reversed(stack):
        if char == "{":
            return index
    return None


def _receipt_holds_inside(unsigned, receipt):
    """A receipt inside a larger text, as a dataset's head carries one inside an inline answer."""
    tail = ',"%s":"%s"}' % (RECEIPT_KEY, receipt)
    at = unsigned.find(tail)
    if at < 0:
        return False
    start = _opening_brace(unsigned, at)
    if start is None:
        return False
    read = read_receipt(unsigned[start:at + len(tail)])
    return read is not None and read[0] == read[1]


def _ml_dsa_87():
    try:
        from dilithium_py.ml_dsa import ML_DSA_87
    except ImportError:
        raise NotRead("checking the signature needs dilithium-py 1.5.1, the ML-DSA-87 of FIPS 204 in pure Python: "
                      "pip install %s" % LIBRARY)
    return ML_DSA_87


class Report:
    def __init__(self, present, cause, envelope, unsigned):
        self.present, self.cause, self.envelope, self.unsigned = present, cause, envelope, unsigned

    def holds(self):
        return self.present and self.cause is None


def check(text, public_key, now_s, seen_nonces=()):
    """Check the signature of text, the object whose receipt is signed (a whole answer, or a dataset's
    head). public_key: the 2,592 bytes, or None. Returns a Report; its cause is the first name that
    does not hold, None when every check holds or when nothing was checked."""
    try:
        found = split(text)
    except Malformed:
        return Report(True, "SignatureMalformed", None, text)
    if found is None:
        return Report(False, "SignatureAbsent" if public_key is not None else None, None, text)
    envelope, unsigned = found["envelope"], found["unsigned"]
    if envelope is None:
        return Report(True, "SignatureMalformed", None, unsigned)
    signature = _canonical_base64(envelope["value"])
    if signature is None or len(signature) != SIGNATURE_LEN:
        return Report(True, "SignatureMalformed", envelope, unsigned)
    if envelope["alg"] != ALGORITHM:
        return Report(True, "SignatureAlgorithmNotServed", envelope, unsigned)
    if public_key is None:
        return Report(True, "SignatureKeyNotGiven", envelope, unsigned)
    if envelope["key_id"] != sha384_hex(public_key):
        return Report(True, "SignatureKeyMismatch", envelope, unsigned)
    read = read_receipt(unsigned)
    if not (read is not None and read[0] == read[1] and read[0] == found["receipt"]):
        if not _receipt_holds_inside(unsigned, found["receipt"]):
            return Report(True, "ReceiptDoesNotMatch", envelope, unsigned)
    signed = message(envelope["key_id"], found["receipt"], envelope["issued_at"], envelope["expires_at"], envelope["nonce"])
    if not _ml_dsa_87().verify(public_key, signed.encode("utf-8"), signature):
        return Report(True, "SignatureDoesNotVerify", envelope, unsigned)
    issued, expires = parse_time(envelope["issued_at"]), parse_time(envelope["expires_at"])
    if issued > now_s + CLOCK_ALLOWANCE_S:
        return Report(True, "SignatureNotYetValid", envelope, unsigned)
    if now_s > expires:
        return Report(True, "SignatureExpired", envelope, unsigned)
    if envelope["nonce"] in seen_nonces:
        return Report(True, "SignatureNonceReplayed", envelope, unsigned)
    return Report(True, None, envelope, unsigned)


# ---- What the verifier brings: --public-key, --now, --nonce-ledger ----

OPTIONS_HELP = """signature options:
  --public-key <file>    the engine's public key: the base64 text of its 2,592 bytes
  --now <time>           the verifier's clock, YYYY-MM-DDTHH:MM:SSZ (default: this machine's clock, UTC)
  --nonce-ledger <file>  the nonces this verifier has seen, one per line: a nonce found there is
                         SignatureNonceReplayed, and a signature that holds has its nonce added"""


def read_public_key(path):
    try:
        with open(path, "rb") as handle:
            text = handle.read().decode("ascii").strip()
    except (OSError, UnicodeDecodeError) as error:
        raise NotRead("the public key '%s' could not be read: %s" % (path, error))
    key = _canonical_base64(text)
    if key is None or len(key) != PUBLIC_KEY_LEN:
        raise NotRead("the public key '%s' is not the base64 of an ML-DSA-87 public key (2,592 bytes)." % path)
    return key


class Given:
    """The key, the clock and the ledger the verifier brings."""

    def __init__(self, key=None, now_s=None, ledger=None):
        import time
        self.key = key
        self.now_s = int(time.time()) if now_s is None else now_s
        self.ledger = ledger
        self.seen = []
        if ledger is not None and os.path.exists(ledger):
            try:
                with open(ledger, encoding="utf-8") as handle:
                    self.seen = [line.strip() for line in handle if line.strip()]
            except (OSError, UnicodeDecodeError) as error:
                raise NotRead("the nonce ledger '%s' could not be read: %s" % (ledger, error))

    def check(self, text):
        return check(text, self.key, self.now_s, self.seen)

    def show(self, report, label=None):
        """Print the signature lines of one answer, as genesis_seal prints them, when it carries a
        signature or a key was given; add its nonce to the ledger when it holds. True when a key was
        given and the signature does not hold."""
        if not report.present and self.key is None:
            return False
        prefix = label + "." if label else ""
        if not report.present:
            said = "absent"
        elif report.cause == "SignatureKeyNotGiven":
            said = "not checked"
        elif report.cause is None:
            said = "holds"
        else:
            said = "does not hold"
        print("%ssignature: %s" % (prefix, said))
        if report.cause == "SignatureKeyNotGiven":
            print("%ssignature_note: no --public-key was given, so the signature was not checked." % prefix)
        elif report.cause is not None:
            print("%ssignature_cause: %s" % (prefix, report.cause))
            print("%ssignature_fault: %s" % (prefix, SENTENCES[report.cause]))
        if report.envelope is not None:
            for key in ("key_id", "issued_at", "expires_at", "nonce"):
                print("%s%s: %s" % (prefix, key, report.envelope[key]))
        if report.holds() and self.ledger is not None:
            try:
                with open(self.ledger, "a", encoding="utf-8") as handle:
                    handle.write(report.envelope["nonce"] + "\n")
            except OSError as error:
                raise NotRead("the nonce ledger '%s' could not be written: %s" % (self.ledger, error))
            self.seen.append(report.envelope["nonce"])
        return self.key is not None and not report.holds()


def take_options(arguments):
    """Take --public-key, --now and --nonce-ledger, each at most once, out of the arguments.
    Returns (the other arguments, Given). Raises NotRead for a value not of the form."""
    rest, values = [], {}
    names = ("--public-key", "--now", "--nonce-ledger")
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument in names:
            if argument in values or index + 1 >= len(arguments):
                raise NotRead("%s is given once, followed by its value" % argument)
            values[argument] = arguments[index + 1]
            index += 2
            continue
        rest.append(argument)
        index += 1
    now_s = None
    if "--now" in values:
        now_s = parse_time(values["--now"])
        if now_s is None:
            raise NotRead("'--now %s' is not a time written YYYY-MM-DDTHH:MM:SSZ." % values["--now"])
    key = None
    if "--public-key" in values:
        key = read_public_key(values["--public-key"])
        _ml_dsa_87()
    return rest, Given(key, now_s, values.get("--nonce-ledger"))


# ---- A record of seal rule v1 ----

SEAL_RULE_NOT_SERVED = "SealRuleNotServed"
SEAL_RULE_V1_SENTENCE = ("This record was made by seal rule v1 (SHA-256), engine 0.14.3 and earlier; this verifier "
                         "reads zero-trust-physics/seal/v2 (SHA-384). genesis_seal 0.6.0, kept whole in "
                         "evidence/verification/engine_0.14.3_served/, verifies it.")
V1_KEYS = ("receipt_sha256", "sha256_seal", "plan_sha256", "rows_sha256", "frames_sha256", "field_sha256",
           "measurements_sha256", "request_sha256", "reject_detail_sha256")
SEALS = ("run_seal", "dataset_seal", "solution_seal", "validation_seal", "chain_seal", "design_seal", "merkle_root")


class SealRuleNotServed(Exception):
    """A record of seal rule v1, or of a rule other than v2: not read."""


def refuse_other_rule(obj):
    """Raise SealRuleNotServed for a record of seal rule v1 or another rule, as genesis_seal does, before any
    of its fields is read: a key only v1 writes, a seal_rule other than v2, or a seal of 64 hex digits.
    A record that names no rule and whose seals are 96 hex digits is read as v2."""
    if not isinstance(obj, dict):
        return
    for key in V1_KEYS:
        if key in obj:
            raise SealRuleNotServed("it carries '%s'" % key)
    rule = obj.get("seal_rule")
    if "seal_rule" in obj and rule != SEAL_RULE:
        raise SealRuleNotServed("it names seal_rule %s" % (("'%s'" % rule) if isinstance(rule, str) else "that is not a string"))
    for key in SEALS:
        if is_lower_hex(obj.get(key), 64):
            raise SealRuleNotServed("its '%s' is 64 hex digits" % key)


def say_not_served(error):
    print("cause: %s" % SEAL_RULE_NOT_SERVED)
    print("not read: %s (%s)" % (SEAL_RULE_V1_SENTENCE, error))
    return 2
