# Zero-Trust Physics: Deep-Water Robotics Substrate Dossier
**Layer 0 Hardened Runtime Assurance for Autonomous Surface & Subsurface Vessels**

Autonomous Underwater Vehicles (UUVs) and Extra Large UUVs (XLUUVs) operate in the most hostile, communication-silent, and GPS-denied environments on Earth. In these abyssal zones, a single sensor failure, acoustic refraction, or actuator lag results in the immediate loss of a multi-million-dollar asset.

Traditional navigation filters (Extended Kalman Filters, or EKFs) trust sensory input to construct state estimations. If sensor data drifts (e.g., Doppler Velocity Log lock-loss) or is spoofed, the autopilot will steer the vessel into structural collapse or seafloor impact.

Zero-Trust Physics (ZTP) implements a **deterministic, non-bypassable safety floor**. By executing physical conservation laws directly on-die, ZTP audits reported states against physical reality in real time. If a state estimate violates the laws of hydrodynamics, ZTP overrides the autopilot, dropping physical ballast to save the machine.

---

## 1. Core Physics Substrate: Seawater Dynamics

The core physics model is implemented in [`marine.rs`](https://github.com/johnkruze/genesis-core/blob/main/src/physics/marine.rs). It represents the environmental and physical forces acting on the rigid body of the UUV.

### Archimedes Buoyancy

$$F_{\text{buoyancy}} = \rho_{\text{seawater}} \cdot g \cdot V$$

Where $\rho_{\text{seawater}} = 1025.0 \text{ kg/m}^3$ and $g = 9.81 \text{ m/s}^2$.

### Hydrodynamic Drag

$$F_{\text{drag}} = -\frac{1}{2} \rho_{\text{seawater}} \cdot |v_{\text{rel}}|^2 \cdot C_d \cdot A \cdot \frac{v_{\text{rel}}}{|v_{\text{rel}}|}$$

### 3D Ocean Current Field & Shear

$$v_{\text{current}}(z, t) = v_{\text{surface}} \cdot e^{-\gamma z} \cdot \left(1 + A_{\text{tidal}} \sin\!\left(\frac{2\pi t}{T_{\text{tidal}}}\right)\right) + \eta_{\text{turbulence}}$$

---

## 2. Abyssal & Littoral Vulnerability Audits

Four high-fidelity edge cases where standard autopilot AI and traditional control loops experience catastrophic failure.

### A. Acoustic Shadow Refraction Collision

**Source:** [`uuv_sonar_thermocline_refraction.rs`](https://github.com/johnkruze/genesis-core/blob/main/src/bin/uuv_sonar_thermocline_refraction.rs)

A UUV mapping its path with forward-looking sonar crosses a thermocline (sharp thermal gradient). Sound speed drops in colder water, bending acoustic waves downward away from objects at cruising depth. The AI assumes linear propagation, misses the obstacle, and impacts the seafloor mount or naval mine.

```
       AUV Cruise Depth [Warm Layer]  ~~~ (c_upper ≈ 1540 m/s) ~~~
       ─────────────────────────────────────────────────────────── [Thermocline]
                                      ─── (c_lower ≈ 1470 m/s) ───
                                           \
                                            \  Bent Sonar Beam (Snell's Law)
                                             \
                                              ▼
                                           [Reef / Sea Mount]
```

Radius of curvature of bent acoustic ray:

$$R = -\frac{c_{\text{upper}}}{\partial c / \partial z}$$

Vertical drop of the ray at lookahead distance $x$:

$$z(x) = R - \sqrt{R^2 - x^2}$$

The ZTP engine sweeps this gradient across 1.2 million trajectories to map the refraction-induced acoustic shadow zone where collision is mathematically unavoidable.

---

### B. Propeller Cavitation Self-Deafening

**Source:** [`propeller_cavitation_noise_floor.rs`](https://github.com/johnkruze/genesis-core/blob/main/src/bin/propeller_cavitation_noise_floor.rs)

At high shaft RPMs in shallow water, propeller tip speed drives local pressure below the vapor pressure of seawater (1228 Pa). Water boils into vapor bubbles; their implosion creates broadband acoustic noise above 180 dB, blinding the vehicle's own passive sonar hydrophones.

Minimum local pressure at propeller tip:

$$P_{\text{min}} = P_{\text{hydrostatic}} - \frac{1}{2} \rho \cdot V_{\text{tip}}^2 \cdot C_L$$

When $P_{\text{min}} \le P_{\text{vapor}}$:

$$\text{Noise Floor (dB)} = 140.0 + 2.5 \cdot \left(\frac{P_{\text{vapor}} - P_{\text{min}}}{1000}\right)$$

---

### C. Abyssal Seal Stiction Windup Tumble

**Source:** [`uuv_pressure_stiction.rs`](https://github.com/johnkruze/genesis-core/blob/main/src/bin/uuv_pressure_stiction.rs)

At 3000m (4300 PSI), hydrostatic pressure compresses dynamic rubber seals against control fin shafts, increasing static breakaway friction (stiction) by 800%. The autopilot commands a minor correction; the fin stays stuck. The PID integral term winds up. When stiction finally breaks, the fin snaps violently — hydrodynamic stall, unrecoverable tumble.

$$\tau_{\text{stiction}} = \tau_{\text{nominal}} + P_{\text{hydrostatic, psi}} \cdot \mu_{\text{crush}}$$

If pitch error exceeds 25°, the vehicle enters hydrodynamic stall.

---

### D. AI-Induced Hydrofoil Nose-Dive

**Source:** [`usv_hull_slam_hydrodynamics.rs`](https://github.com/johnkruze/genesis-core/blob/main/src/bin/usv_hull_slam_hydrodynamics.rs)

A high-speed USV in Sea State 5 experiences massive upward acceleration from wave-slamming. The AI trim-controller misinterprets this as pitch-up and commands the bow foils down. Due to hydraulic slew rate limits, the flaps reach maximum down-trim exactly as the vessel crests the wave — forcing a nose-dive directly into the next trough.

Encounter frequency steaming head-on:

$$\omega_e = \frac{2\pi}{T_{\text{wave}}} \cdot \left(1 + \frac{U}{C_{\text{wave}}}\right)$$

Hydrofoil moment lag:

$$\dot{\tau}_{\text{foil}} = \text{clamp}\!\left(\frac{\tau_{\text{command}} - \tau_{\text{foil}}}{\Delta t},\ -\text{slew}_{\text{max}},\ \text{slew}_{\text{max}}\right)$$

---

## 3. Real-Time Active Defense: The 3D Hydrodynamic Force Auditor

**Source:** [`marine_firewall.py`](marine_firewall.py)

```
[Doppler Velocity Log (DVL)]
         │ Lock-Loss / Spoofing
         ▼
[Navigation Filter (EKF)] ──> Hallucinating velocity
         │
         ▼
[Autopilot Commands] ──────────────────┐
         │                             │
         ▼                             ▼
[Propellers & Actuators]        [ZTP Marine Firewall]
         │                             │
         ▼ (true physics)              ▼ (force-balance)
   Actual Motion                F_thrust + F_drag + F_buoy
         │                             │
         ▼                             ▼
    Raw IMU ◄─────────── Residual = ||a_expected - a_imu||
                                       │
                    ┌──────────────────┴──────────────────┐
                    ▼                                      ▼
         Residual ≤ 0.15g                       Residual > 0.15g
              [OK]                               [VIOLATION]
         Trust EKF state                  1. Reject EKF velocity
                                          2. Command pitch-up
                                          3. Drop emergency ballast
                                          4. Surface safely
```

The audit computes expected acceleration from the EKF's claimed velocity state and compares against the raw IMU reading. A residual above 0.15g means the navigation filter's velocity is physically incompatible with what the accelerometer is measuring — sensor compromise declared, emergency ascent triggered.

---

## 4. Monte Carlo Coverage

- [`marine_monte_carlo.rs`](https://github.com/johnkruze/genesis-core/blob/main/src/bin/marine_monte_carlo.rs) — Dead-reckoning error under varying current and drift profiles
- [`submarine_monte_carlo.rs`](https://github.com/johnkruze/genesis-core/blob/main/src/bin/submarine_monte_carlo.rs) — Structural integrity across Midnight, Abyssal, and Hadal zones (1000m–9000m)

Every run is SHA-256 sealed:

$$\text{Run Hash} = \text{SHA256}(\text{Trajectory Results})$$

---

Part of the [Zero-Trust Physics](https://github.com/johnkruze/zero-trust-physics) suite · [ZeroTrustPhysics.com](https://ZeroTrustPhysics.com)
