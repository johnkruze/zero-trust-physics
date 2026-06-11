# zero-trust-physics

**13 edge-resident physics auditors for autonomous systems.**

[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![ZTP Kernel](https://img.shields.io/badge/Kernel-ztp--runtime-555555?style=flat-square)](https://github.com/johnkruze/ztp-runtime)
[![Physics Engine](https://img.shields.io/badge/Engine-genesis--core-black?style=flat-square)](https://github.com/johnkruze/genesis-core)

Zero-Trust Physics (ZTP) auditors intercept commands to autonomous systems and verify physical invariants before actuation — energy conservation, friction cone limits, stopping envelopes, momentum bounds. Resilient against perception hallucinations, network blackouts, and sensor drift.

Each auditor bridges to the Rust ZTP kernel ([ztp-runtime](https://github.com/johnkruze/ztp-runtime)) via C FFI. Physics runs in Rust at 1000Hz; Python handles scenario setup, visualization, and Aegis manifest sealing.

---

## The 13 Auditors

| Directory | Auditor | What it guards |
|-----------|---------|---------------|
| `ztp-cad-integrity/` | CAD Integrity | Moment-of-inertia validation, URDF manifold repair |
| `ztp-vslam-firewall/` | VSLAM Firewall | 1000Hz drift/hallucination detection, IMU fallback |
| `ztp-telemetry-logger/` | Telemetry Logger | Binary log serialization, SLAM aliasing detection |
| `ztp-marine-firewall/` | Marine Firewall | 3D hydrodynamic drag audit, UUV emergency ballast |
| `ztp-hypersonic-gnc/` | Hypersonic GNC | EKF covariance divergence, fin damping under plasma blackout |
| `ztp-grounded-navigation/` | Grounded Navigation | Surface traction safety limiter for mobile AI planners |
| `ztp-power-integrity/` | Power Integrity | 100kHz SMPS voltage PID auto-tuner under capacitor degradation |
| `ztp-directed-energy/` | Directed Energy | Gimbal Kalman filter, covariance latch-up prevention |
| `ztp-propulsion-safety/` | Propulsion Safety | Chamber pressure monitoring, automatic oxidizer isolation |
| `ztp-terramechanics/` | Terramechanics | Lunar rover wheel slip control (15% target) |
| `ztp-rocket-gnc/` | Rocket GNC | TVC landing stabilization, auxiliary RCS allocation |
| `ztp-dexterous-hand/` | Dexterous Hand | Tactile slip auditor — 45N grip limit, 2ms reflex |
| `ztp-fleet-orchestration/` | Fleet Orchestration | Multi-robot stopping envelope, collision e-brake under comms loss |

---

## Architecture

```
Python auditor script
  └── ctypes FFI
        └── libztp_runtime.dylib  (ztp-runtime Rust kernel)
              └── 1000Hz physics integration
                    └── ZTP invariant check
                          └── anomaly flag / override command
                                └── Aegis OS manifest seal
```

---

## Running an Auditor

```bash
# Build the Rust kernel first
cd ../ztp-runtime && cargo build --release

# Run any auditor
python3 ztp-dexterous-hand/dexterous_grasp.py
python3 ztp-directed-energy/directed_energy.py
python3 ztp-marine-firewall/marine_firewall.py
```

Each run produces:
- Telemetry dashboard (PNG)
- Dataset export (Parquet, HuggingFace-ready)
- Sealed Aegis OS manifest (SHA-256)

---

## Datasets

Telemetry from these auditors is published on HuggingFace:
- [humanoid-tactile-slip-reflex-1000hz](https://huggingface.co/datasets/spiderpilot89/humanoid-tactile-slip-reflex-1000hz)
- [directed-energy-gimbal-1000hz](https://huggingface.co/datasets/spiderpilot89/directed-energy-gimbal-1000hz)

---

## Related

- [ztp-runtime](https://github.com/johnkruze/ztp-runtime) — Rust bare-metal kernel (C FFI)
- [genesis-core](https://github.com/johnkruze/genesis-core) — Full physics engine
- [aegis-os](https://github.com/johnkruze/aegis-os) — Per-body OS that runs these auditors
- [datasets](https://github.com/johnkruze/datasets) — All published datasets

---

John Kruze · [ZeroTrustPhysics.com](https://ZeroTrustPhysics.com) · kruze@zerotrustphysics.com
