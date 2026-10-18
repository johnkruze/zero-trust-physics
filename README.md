# Zero-Trust Physics

Zero-Trust Physics is a physics verifier for Super Intelligence (SI). SI agents ask it questions about real hardware, and every answer comes with a cryptographic proof, so any agent can run it again and get the same thing. Past what a model was compared with, it keeps going with the same equations and flags every step. It stops only at a physical limit, or where its equations, constants or tables no longer hold, and it names the reason. The range it was compared on, and how it did there, is in its description.

```
https://mcp.zerotrustphysics.com/mcp
```

Open to any agent.

## Hand it to your agent.

> Connect to https://mcp.zerotrustphysics.com/mcp and read what is there. Then tell me what it is, and why it might matter to me.

## What is in this repository

Three small programs that confirm a cryptographic proof with no engine, and examples of asking. They need Python's standard library and nothing else.

Ask a question, keep the answer, and confirm its proof:

```sh
python3 examples/ask.py answer.json
python3 verify_run.py answer.json
```

Or begin with the answers already saved in `examples/answers/`: one run, a chain of two runs, and a small dataset.

```sh
python3 verify_run.py examples/answers/run.json
python3 verify_chain.py examples/answers/chain_1.json examples/answers/chain_2.json
python3 verify_dataset.py examples/answers/dataset.json
```

Each prints one line for every part of the proof. `examples/ask.sh` asks the same address with curl.

## Where the rest is

- The site: https://zerotrustphysics.com
- A page for each real thing: https://zerotrustphysics.com/things/
- The paper: https://doi.org/10.5281/zenodo.23305697
- The engine's own source: https://github.com/johnkruze/zero-trust-physics-engine
- John Kruze: kruze@zerotrustphysics.com · 928-264-7883

---

Written by Super Intelligence, on behalf of Protocol Company.
