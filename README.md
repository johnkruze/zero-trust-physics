# Zero-Trust Physics

Zero-Trust Physics is a physics verifier for Super Intelligence (SI). SI agents ask it questions about real hardware, and every answer comes with a cryptographic proof, so any agent can run it again and get the same thing. Past what a model was compared with, it keeps going with the same equations and flags every step. It stops only at a physical limit, or where its equations, constants or tables no longer hold, and it names the reason. The range it was compared on, and how it did there, is in its description.

```
https://mcp.zerotrustphysics.com/mcp
```

Open to any agent.

## Hand it to your agent.

> Connect to https://mcp.zerotrustphysics.com/mcp and read what is there. Then tell me what it is, and why it might matter to me.

## What is in this repository

Four small programs that check a cryptographic proof with no engine, and examples of asking. They read seal rule v2 (`"seal_rule":"zero-trust-physics/seal/v2"`): every hash is SHA-384, written as 96 hex digits, the row tree is RFC 6962 with SHA-384, and a dataset's frame file starts with an 80-byte header (`GKF3`, layout 2).

- `verify_run.py` recomputes a run's proof: `link_0` from the request, the chain of frames, the state digest, the run seal and the receipt.
- `verify_chain.py` does that for each run of a chain, then checks each link against the run before it and every chain seal.
- `verify_dataset.py` checks a dataset: the plan hash, every row's chain, state digest, run seal and leaf, the row tree, the dataset seal, the hashes of the rows and the frames, the frame file's header and the head's receipt.
- `verify_signature.py` checks the engine's signature on any answer, and its receipt.

The seals need Python's standard library and nothing else. Checking the engine's signature (ML-DSA-87, FIPS 204) needs one package, dilithium-py 1.5.1: pure Python, written to FIPS 204 final, not validated under FIPS 140-3, used here only to verify public data. It is imported only when a public key is given.

```sh
pip install dilithium-py==1.5.1
```

Ask a question, keep the answer, and check its proof:

```sh
python3 examples/ask.py answer.json
python3 verify_run.py answer.json
```

Or begin with the answers already saved in `examples/answers/`: one run, a chain of two runs, and a small dataset, each answered by engine 0.15.0 under seal rule v2.

```sh
python3 verify_run.py examples/answers/run.json
python3 verify_chain.py examples/answers/chain_1.json examples/answers/chain_2.json
python3 verify_dataset.py examples/answers/dataset.json
```

Each prints one line for every part of the proof. `examples/ask.sh` asks the same address with curl.

## One revolution of LAGEOS-1, from the open address

LAGEOS-1 is a laser-ranging satellite. The engine's model of it (`satellite_lageos1`) flies it from a published position and velocity under the Earth's field to degree and order 12, the Sun and the Moon, the solid tide, sunlight pressure and relativity, and holds the energy and the angular momentum about the Earth's axis at every step. After one revolution it was within 0.65 m of the published orbit; after one day 3.8 m, after seven days 32 m.

`examples/lageos.json` asks for one revolution: 1,356 steps of 10 s from the model's worked start (5 September 1996), one frame recorded. Fetch the engine's public key, ask, and check the answer:

```sh
curl -sS https://mcp.zerotrustphysics.com/answer-key -o answer_key.json
python3 -c 'import json; d = json.load(open("answer_key.json")); print(d["key_id"]); open("answer_key.pub", "w").write(d["public_key"])'
curl -sS https://mcp.zerotrustphysics.com/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d @examples/lageos.json -o lageos.json
python3 verify_run.py lageos.json --public-key answer_key.pub --nonce-ledger seen.txt
```

The `key_id` printed is the SHA-384 of the engine's public key (ML-DSA-87, 2,592 bytes). The engine's key is:

```
ca06027a972c81c8630fed9f4ea2d4e91596b9434a88a03b7eb325b24e40645b7090cb705927745e73ee8b272eb1be38
```

Engine 0.15.0 answered this on 19 October 2026 at 19:38:41 UTC, and `verify_run.py` printed:

```
link_0:        7eb99951036942e9e3b8f704914b4378a7f787e13d2b25bcf95cd703837a21c715ec0faa307f9d3a867ee34bcee19403
chain:         holds  1 frames, last link 48316119f99c5979086bb611afc1244f4c181eaf2ffe79124ba954a4eeafb8307aa5c9625a18ec25884df36502ae42f1
state_digest:  holds  ba5916ad6dc6c1ebb92e3d7ecd501cf251f1ccea0be6419be7ae7de8abdd7dac86700e7fecd66d414c05d6fbd98fd57b
run_seal:      holds  d59d9fb0611bdd9d52ce836688b046f20420b9877236e8f093f26618721f498ed04fa783af956c71173ac53d17edec7e
receipt:       holds  25ca9777b56b156dc3905454ce2cc47ad90220e557e68643c819d88d94a5c13c746e0611aa678d454eb574bb8f49322d
signature: holds
key_id: ca06027a972c81c8630fed9f4ea2d4e91596b9434a88a03b7eb325b24e40645b7090cb705927745e73ee8b272eb1be38
issued_at: 2026-10-19T19:38:41Z
expires_at: 2026-10-19T20:38:41Z
nonce: 0f58c9be769b67ce3d1e32325fd6a0ad3e4af1c2327c3fdbbd8e64c4542fe5a8
result: every proof holds
```

The run completed all 1,356 steps, 13,560 s of flight, and ended at radius 12,223,045.3 m, semi-major axis 12,265,877.1 m, with the largest conservation residual of any step 4.4e-12. The engine computes the same question the same way every time, so your `run_seal` is the one above, and so are `link_0`, `chain`, `state_digest` and `receipt`. The signature is new on every answer: your `issued_at`, `expires_at` and `nonce` are your own, and your answer expires an hour after it is issued. Run `verify_run.py` again with the same ledger and the nonce is named, `SignatureNonceReplayed`; with a clock past the expiry, `SignatureExpired`. Both exit 5: the seals still hold. Without `--public-key`, `verify_run.py` needs only Python's standard library, checks every seal and reports the signature without checking it.

### The engine's signature

An engine given an answer key signs the receipt of every computed answer, with an issue time, an expiry and a nonce, and writes the signature right after the receipt. `run_signed.json` is the run of `run.json` signed by a test key, never an operator's (its seed is the first 32 bytes of the SHA-384 of "a test answer key, never an operator's: engine"); `test_key.pub` is its public key. A signature is checked against a key you give, at a time you give (by default your clock), and against the nonces you have seen:

```sh
python3 verify_run.py examples/answers/run_signed.json --public-key examples/answers/test_key.pub --now 2026-10-19T20:00:00Z --nonce-ledger seen.txt
python3 verify_signature.py examples/answers/run_signed.json --public-key examples/answers/test_key.pub --now 2026-10-19T20:00:00Z
```

The lines `signature`, `signature_cause`, `key_id`, `issued_at`, `expires_at` and `nonce` say what was found. The checks run in this order, and the first that does not hold is named: `SignatureMalformed`, `SignatureAlgorithmNotServed`, `SignatureKeyNotGiven`, `SignatureKeyMismatch`, `ReceiptDoesNotMatch` (a value changed after signing), `SignatureDoesNotVerify` (a forged signature, or a receipt made again), `SignatureNotYetValid`, `SignatureExpired`, `SignatureNonceReplayed` (a nonce already in the ledger; a signature that holds adds its nonce). An answer with no signature checked with a key is `SignatureAbsent`; with no key given, a signature is reported and not checked. Exit code 5: every seal holds and the signature does not.

A record of seal rule v1 (SHA-256, engine 0.14.3 and earlier) is not read: it is named `SealRuleNotServed`, exit code 2.

`tests/test_v2.py` holds each of these to the engine's own verifier, `genesis_seal`.

## Where the rest is

- The site: https://zerotrustphysics.com
- A page for each real thing: https://zerotrustphysics.com/things/
- The paper: https://doi.org/10.5281/zenodo.23305697
- The engine's own source: https://github.com/johnkruze/zero-trust-physics-engine
- John Kruze: kruze@zerotrustphysics.com · 928-264-7883

---

Written by Super Intelligence, on behalf of Protocol Company.
