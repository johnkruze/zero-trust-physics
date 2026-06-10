# ZTP-VSLAM-FIREWALL: 1000Hz Visual-Inertial Dynamics Consistency Filter

A CLI tool and flight telemetry simulation that solves a critical vulnerability in tactical military UAS/C-UAS platforms: **Visual-SLAM (VSLAM) and optical flow algorithms locking onto moving dynamic particulates (smoke, dust plumes, sand, snow) rather than static structural geometry.**

This tool simulates a quadrotor entering a tactical smoke plume, calculates the physical inconsistency of the resulting VSLAM velocity vector relative to IMU/motor commands at 1000 Hz, executes a safety-critical override to IMU dead-reckoning, and writes a cryptographically sealed flight telemetry record.

---

## The C-UAS / Tactical UAS Pain Point

Vision-based target tracking and visual simultaneous localization and mapping (VSLAM) rely on matching high-contrast visual features between camera frames. In battlefield conditions (dust from armored vehicles, shell smoke, or fog):
1. **Feature Scrambling:** Static features (walls, ground landmarks) are occluded exponentially as particulate density rises.
2. **Optical Flow Hallucination:** The vision algorithm locks onto moving smoke tendrils or dust clouds, extracting they are "static points." 
3. **Control Loop Divergence:** If smoke is drifting to the right, the VSLAM concludes the vehicle is drifting left. The autopilot’s PID loop attempts to correct this by pitching violently to the right, accelerating the vehicle directly into the nearest wall or ground target.

---

## The Solution: Visual-Inertial Consistency Filtering

The **ZTP Visual-Inertial Consistency Filter** sits as a Layer 0 monitor between the vision engine and the autopilot. Because the vehicle's structural mass and inertia are invariant, the vision engine's reported motion *must* reconcile with the physical forces acting on the vehicle body.

### The Mathematics of Consistency
Let $v_{\text{vslam}}(t)$ be the velocity vector reported by the vision system. The implied acceleration is:
$$a_{\text{vslam}}(t) = \frac{v_{\text{vslam}}(t) - v_{\text{vslam}}(t-\Delta t)}{\Delta t}$$

We compare this to the actual acceleration measured by the onboard accelerometer (IMU), adjusted for gravity:
$$a_{\text{imu}}(t) = \text{IMU\_accel} - g$$

Under consistent, honest flight conditions (static visual features):
$$\mathcal{I}(t) = \|a_{\text{vslam}}(t) - a_{\text{imu}}(t)\| \le \varepsilon$$
where $\varepsilon$ represents the sensor noise floor. 

When the drone enters a smoke plume and the VSLAM locks onto the advection velocity of the smoke, the reported velocity drifts sharply, but the physical accelerometer detects no thrust deviation. The residual $\mathcal{I}(t)$ diverges immediately:
$$\mathcal{I}(t) > \varepsilon$$

The firewall catches this divergence within milliseconds, suppresses the visual velocity vector, and switches the autopilot to dead-reckoning/hover-hold using raw IMU integration.

---

## Features

- **1000Hz Quadrotor Simulator:** Integrates 2D rigid body dynamics (gravity, thrust, drag) under thermal smoke advection.
- **Visual-Inertial Residual Auditor:** Computes acceleration residuals to distinguish real maneuvers from visual drift.
- **Autonomous Control Override:** Simulates autopilot correction and safety-critical override transitions.
- **SHA-256 Telemetry Seal:** Computes a cryptographic hash of the entire flight telemetry log upon successful recovery, making the record retroactively tamper-evident.

---

## Usage

Run the simulation to see both the unprotected flight crash and the protected ZTP override recovery:

```bash
python3 vslam_firewall.py
```

### Simulation Phases

1. **Nominal Flight ($t=0.0\text{s} - 5.0\text{s}$):** Drone hovers statically. VSLAM features track static geometry successfully.
2. **Smoke Entry ($t=5.0\text{s}$):** Drone enters smoke. Static features drop, and moving smoke plumes dominate the visual field.
3. **Unprotected Audit:** Auto-pilot blindly trusts VSLAM. Drone pitches violently forward and crashes at $t=6.53\text{s}$ (1.5 seconds after entering smoke).
4. **ZTP Protected Audit:** At $t=5.012\text{s}$ (12ms after entering smoke), the firewall flags a physical residual violation of $\mathcal{I}(t) = 39.77 > 2.0$. It switches to IMU dead-reckoning, holds stable hover, survives the duration of the flight, and seals the verified telemetry record.
