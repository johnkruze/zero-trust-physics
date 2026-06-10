# ZTP-MARINE-FIREWALL: 3D Hydrodynamic Force-Balance AUV Navigation Auditor

A CLI tool and UUV simulator that solves a mission-critical safety vulnerability in deep-ocean uncrewed underwater vessels (UUVs/AUVs) like heavy-class long-range AUVs: **Doppler Velocity Log (DVL) bottom-lock loss and resulting EKF navigation drift.**

This tool simulates an AUV performing a deep seabed transit, calculates the 3D hydrodynamic force-balance (Archimedes buoyancy, gravity, thrust, and drag) at 10 Hz, audits the navigation filter's velocity state against physical invariants, executes an emergency ballast-drop override when drift is detected, and writes a cryptographically sealed flight telemetry record.

---

## The Maritime Autonomy Pain Point

Deep-ocean AUVs operate in the ultimate "Dark Window." Radio waves attenuate immediately, and GPS is unavailable. The vehicle must navigate using:
1. **DVL (Doppler Velocity Log):** Measures relative ground speed by bouncing acoustic pings off the seabed.
2. **IMU (Inertial Measurement Unit):** Integrates accelerations and gyroscopic rotations.

### The Failure Cascade: Bottom-Lock Loss
If the AUV traverses a steep underwater trench or encounters dynamic silt, the acoustic pings fail to return, resulting in **DVL bottom-lock loss**. The navigation filter is forced to dead-reckon using the IMU alone. Due to accelerometer bias, the estimated position drifts quadratically over time. 

To maintain its "believed" horizontal cruising velocity and depth profile, the autopilot will command aggressive pitch-down angles and throttle increases. In reality, the vehicle is pitching straight down toward its structural **crush depth** or an underwater seamount.

---

## The Solution: Hydrodynamic Force Auditing

The **ZTP Marine Firewall** models the vehicle's physical characteristics (dry mass, displacement volume, drag cross-section, and thrust maps) locally on edge silicon. It continuously calculates the expected forces:
$$\Sigma F_{\text{expected}} = F_{\text{buoyancy}} + F_{\text{gravity}} + F_{\text{thrust}}(\text{throttle}, \theta) + F_{\text{drag}}(v_{\text{nav}})$$

It compares this expected force vector against the actual contact acceleration measured by the IMU:
$$\mathcal{I}(t) = \left\| \frac{\Sigma F_{\text{expected}}}{M} - a_{\text{imu}} \right\| \le \varepsilon$$

When the DVL fails and the navigation filter's velocity state drifts, the calculated drag force $F_{\text{drag}}(v_{\text{nav}})$ diverges from reality. The residual $\mathcal{I}(t)$ spikes immediately. 

The firewall intercepts this physical violation, rejects the drifted navigation state, and triggers an **Emergency Ballast Drop** (increasing buoyancy displacement, reducing dry mass, and locking pitch-up) to force the vehicle back to surface safety.

---

## Features

- **3D AUV Flight Simulator:** Models 3D vertical plane kinematics, ocean current shear, and battery depletion curves matching your Rust `marine.rs` library.
- **Hydrodynamic Force Auditor:** Compares thrust, drag, and buoyancy profiles against IMU inputs at 10 Hz.
- **Emergency Ballast Override:** Simulates water expulsion (200kg dry weight reduction) and buoyancy expansion.
- **SHA-256 Marine Telemetry Seal:** Seals the audited telemetry stream upon successful recovery.

---

## Usage

Run the simulation to see both the drift dive and the protected override recovery:

```bash
python3 marine_firewall.py
```

### Simulation Phases

1. **Nominal Cruise ($t=0.0\text{s} - 20.0\text{s}$):** UUV cruises at 1500m depth, maintaining stable speed (1.5 m/s).
2. **DVL Bottom-Lock Loss ($t=20.0\text{s}$):** DVL loses bottom-lock. The navigation filter begins drifting.
3. **ZTP Protected Audit:** At $t=20.0\text{s}$, the firewall flags a force violation of $\mathcal{I}(t) = 1.064\text{ g} > 0.15\text{ g}$. It switches to emergency ballast override, expels water, pitches up, and safely ascends to $492\text{m}$.
