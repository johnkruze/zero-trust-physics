# ZTP-HYPERSONIC-GNC: Hypersonic Blackout Aerodynamic Speed Estimator

A CLI tool and missile performance simulator that solves a critical, high-end guidance bottleneck in hypersonic weapons (like tactical HGVs): **GPS and RF signal blackout due to radome plasma sheath ionization during high-Mach terminal dives.**

This tool simulates a Mach 5+ terminal dive on a moving naval carrier, calculates the EKF tracking covariance, implements an **Aerodynamic Speedometer (ZTP Firewall)** utilizing longitudinal drag force to bound INS velocity drift during GPS blackout, and writes a cryptographically sealed GNC telemetry record.

---

## The Hypersonic Guidance Pain Point

During a terminal strike at Mach 5+, atmospheric friction superheats and ionizes the air surrounding the missile nose cone, wrapping it in a **plasma sheath**. 
- **RF/GPS Blackout:** This ionized gas completely absorbs and reflects RF signals, blocking GPS updates for the final 12+ seconds of flight.
- **INS Covariance Expansion:** Without absolute positioning updates, the Inertial Navigation System (INS) Kalman Filter covariance grows.
- **Covariance Panic:** Autopilots are programmed with strict covariance limits to avoid collateral damage from blind strikes. If positional uncertainty exceeds a threshold (e.g. 50 $m^2$), the AI locks the steering fins in a neutral glide. The weapon becomes a dumb ballistic dart, missing a maneuvering aircraft carrier by over 100 meters.

---

## The Solution: Aerodynamic Force Balance Speedometer

The **ZTP Aerodynamic Firewall** uses the vehicle's dry mass ($M$), cross-sectional drag area ($A$), and supersonic drag coefficient ($C_d$) to audit motion. 

The drag deceleration $a_{\text{drag}}$ is measured directly by the longitudinal accelerometer on the IMU. Since the air density $\rho(z)$ is known at any altitude $z$, the physical airspeed $v$ can be solved algebraically at 100 Hz from the drag equation:
$$a_{\text{drag}}(t) = \frac{1}{2 M} \rho(z) v^2 C_d A \implies v_{\text{aero}} = \sqrt{\frac{2 M a_{\text{drag}}(t)}{\rho(z) C_d A}}$$

By feeding this physical speed estimate into the EKF, the INS velocity drift error is mathematically bounded. The positional covariance remains extremely low (under 6.0 $m^2$) throughout the blackout period, allowing the proportional navigation loop to lead the target and strike the deck.

---

## Features

- **Supersonic Flight Dynamics Simulator:** Integrates altitude-dependent air density profiles (US Standard Atmosphere) and Mach-5 aerodynamic forces at 100 Hz.
- **Aerodynamic Speedometer Auditor:** Resolves airspeed from IMU deceleration to bound INS drift.
- **Moving Target Trajectory Estimator:** Predicts evasive maneuvers of a naval carrier deck.
- **SHA-256 Telemetry Seal:** Seals the GNC telemetry logs upon successful strike.

---

## Usage

Run the simulation to see both the blind splash and the protected target strike:

```bash
python3 hypersonic_gnc.py
```

### Simulation Phases

1. **Nominal Glide ($t=0.0\text{s} - 10.0\text{s}$):** Missile dives at Mach 5. GPS is active; covariance is nominal (1.0 $m^2$).
2. **Plasma Blackout Entry ($t=10.0\text{s}$):** Missile descends below 16km. Air ionizes, and GPS goes blind.
3. **Unprotected Audit:** EKF covariance grows at 10 $m^2/\text{s}$. At $t=13.0\text{s}$ it exceeds 50 $m^2$. The AI panics, locks the steering fins, and splashes in the ocean (miss distance: 10,104m).
4. **ZTP Protected Audit:** The aerodynamic speedometer bounds INS drift. Covariance stays at a stable $5.60\text{ }m^2$. Autopilot continues tracking, scoring a **direct hit** (miss distance: 0.12m) with a sealed telemetry path.
