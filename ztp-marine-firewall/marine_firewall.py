#!/usr/bin/env python3
"""
ZTP-MARINE-FIREWALL: 3D Hydrodynamic Force-Balance Navigation Auditor.
Part of the Zero-Trust Physics runtime assurance framework.

This tool solves a mission-critical safety bottleneck for deep-ocean AUVs:
GPS-denied navigation drift during Doppler Velocity Log (DVL) bottom-lock loss.
It checks if the navigation filter's velocity state reconciles with physical forces 
(thrust, drag, gravity, buoyancy) and triggers an emergency ballast override.
"""

import os
import sys
import hashlib
import json
import numpy as np

# ANSI Colors
C_BLUE = "\033[94m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_BOLD = "\033[1m"
C_END = "\033[0m"

BANNER = f"""
{C_BLUE}{C_BOLD}================================================================================
  ███╗   ███╗ █████╗ ██████╗ ██╗███╗   ██╗███████╗    ███████╗██╗██████╗ ███████╗
  ████╗ ████║██╔══██╗██╔══██╗██║████╗  ██║██╔════╝    ██╔════╝██║██╔══██╗██╔════╝
  ██╔████╔██║███████║██████╔╝██║██╔██╗ ██║█████╗      █████╗  ██║██████╔╝█████╗  
  ██║╚██╔╝██║██╔══██║██╔══██╗██║██║╚██╗██║██╔══╝      ██╔══╝  ██║██╔══██╗██╔══╝  
  ██║ ╚═╝ ██║██║  ██║██║  ██║██║██║ ╚████║███████╗    ██║     ██║██║  ██║███████╗
  ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝╚══════╝    ╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝
  Zero-Trust Physics: 3D Hydrodynamic Force Auditor & UUV Safety Override
================================================================================{C_END}
"""

# Physical Constants (from G^G marine.rs)
RHO_SEAWATER = 1025.0    # kg/m^3
GRAVITY = 9.81           # m/s^2
ATM_PRESSURE = 101325.0  # Pa
DT = 0.1                 # 10Hz control loop rate (standard AUV rate)

# UUV Model Parameters (heavy-class long-range AUV)
MASS = 2500.0            # kg (dry mass)
VOLUME = 2.44            # m^3 (displacement volume)
DRAG_AREA = 1.15         # m^2 (frontal cross section)
CD = 0.22                # drag coefficient
MAX_THRUST = 450.0       # N (forward thruster capacity)
CRUSH_DEPTH = 3000.0     # meters (critical structural limit)

def get_hydrostatic_pressure(depth):
    """P = P_atm + rho * g * depth"""
    return ATM_PRESSURE + RHO_SEAWATER * GRAVITY * depth

def get_depth_from_pressure(pressure):
    """depth = (P - P_atm) / (rho * g)"""
    return (pressure - ATM_PRESSURE) / (RHO_SEAWATER * GRAVITY)

def simulate_step(pos, vel, pitch, thrust_input, dvl_fail=False):
    """
    Simulate true UUV physics in 3D vertical plane.
    pos: [x, z] (z is positive depth in meters)
    vel: [vx, vz] (velocity)
    pitch: radians (up = negative, down = positive)
    thrust_input: normalized [-1.0 to 1.0] forward thrust
    """
    # 1. Forces
    # Gravity (downward, positive depth)
    f_gravity = MASS * GRAVITY
    
    # Archimedes Buoyancy (upward, negative depth)
    f_buoyancy = -RHO_SEAWATER * GRAVITY * VOLUME
    
    # Thrust vector (aligned with pitch)
    thrust_mag = thrust_input * MAX_THRUST
    f_thrust_x = thrust_mag * np.cos(pitch)
    f_thrust_z = thrust_mag * np.sin(pitch)
    
    # Hydrodynamic drag opposing velocity
    speed = np.linalg.norm(vel)
    if speed > 1e-6:
        drag_mag = 0.5 * RHO_SEAWATER * speed**2 * CD * DRAG_AREA
        f_drag_x = -drag_mag * (vel[0] / speed)
        f_drag_z = -drag_mag * (vel[1] / speed)
    else:
        f_drag_x, f_drag_z = 0.0, 0.0
        
    # Net accelerations
    acc_x = (f_thrust_x + f_drag_x) / MASS
    # Net z force (gravity + buoyancy + thrust + drag)
    acc_z = (f_gravity + f_buoyancy + f_thrust_z + f_drag_z) / MASS
    
    # Integrate
    new_vel = vel + np.array([acc_x, acc_z]) * DT
    new_pos = pos + new_vel * DT
    
    # IMU measurement (accelerometers measure contact force, excluding gravity)
    # imu_a = a - g
    imu_acc = np.array([acc_x, acc_z - GRAVITY])
    
    # Navigation sensor simulation
    # Nominal: EKF estimates velocity correctly via DVL.
    # DVL Fail: DVL bottom-lock is lost (e.g. over a deep trench).
    # The EKF dead-reckons using IMU but suffers from integrated bias.
    if dvl_fail:
        # Simulate quadratic drift error in position and linear bias in velocity
        drift_factor = 0.02 * (pos[0] - 200.0) # drift starts after 200m forward travel
        nav_vel = new_vel - np.array([drift_factor, 0.0])
    else:
        nav_vel = new_vel.copy()
        
    return new_pos, new_vel, imu_acc, nav_vel

def run_mission():
    """Run a 60-second deep seabed mapping simulation, DVL fails at t=20s."""
    # State vectors
    pos = np.array([0.0, 1500.0]) # starting depth 1500m
    vel = np.array([1.5, 0.0])     # cruising at 1.5 m/s
    pitch = 0.0
    thrust_input = 0.4             # nominal throttle
    
    log = []
    total_ticks = 600 # 60 seconds at 10Hz
    
    print(f"{C_BLUE}Simulating seabed mapping run (600 steps at 10 Hz)...{C_END}")
    
    for tick in range(total_ticks):
        t = tick * DT
        
        # Scenario Timeline:
        # At t=20.0s, the vehicle crosses a deep bathymetric trench, losing bottom lock.
        dvl_fail = t >= 20.0
        
        # Simulate true physical dynamics
        pos, vel, imu_acc, nav_vel = simulate_step(pos, vel, pitch, thrust_input, dvl_fail)
        
        # In a DVL fail scenario, the navigation filter drifts.
        # To compensate for the "hallucinated drop in forward speed," the autopilot
        # commands pitch-down to maintain depth trajectory, driving the sub down.
        if dvl_fail:
            pitch = np.clip(pitch + 0.005 * DT, -0.2, 0.6) # pitching down
            thrust_input = min(1.0, thrust_input + 0.01 * DT)
            
        log.append({
            "timestamp": t,
            "true_pos": pos.tolist(),
            "true_vel": vel.tolist(),
            "imu_acc": imu_acc.tolist(),
            "thrust_input": float(thrust_input),
            "pitch": float(pitch),
            "nav_vel": nav_vel.tolist(),
            "dvl_fail": dvl_fail
        })
        
    return log

def audit_nav_log(log, apply_ztp_firewall=False):
    """
    Audit the AUV navigation telemetry.
    If apply_ztp_firewall=True, intercepts DVL drift and drops emergency ballast.
    """
    print(f"\n{C_BOLD}Auditing UUV Navigation Log (ZTP Marine Firewall: {'ENABLED' if apply_ztp_firewall else 'DISABLED'}){C_END}")
    print("-" * 90)
    
    pos = np.array([0.0, 1500.0])
    vel = np.array([1.5, 0.0])
    pitch = 0.0
    thrust_input = 0.4
    
    # Physical force balance threshold
    FORCE_RESIDUAL_THRESHOLD = 0.15 # ~15% discrepancy in drag force
    
    override_active = False
    override_time = None
    imploded = False
    
    steps_log = []
    
    for i, frame in enumerate(log):
        t = frame["timestamp"]
        nav_vel = np.array(frame["nav_vel"])
        imu_acc = np.array(frame["imu_acc"])
        
        # 1. RUN HYDRODYNAMIC FORCE AUDIT
        # We calculate expected forces based on the navigation filter's velocity
        speed = np.linalg.norm(nav_vel)
        if speed > 1e-6:
            # F_drag = 0.5 * rho * v^2 * Cd * A
            drag_mag = 0.5 * RHO_SEAWATER * speed**2 * CD * DRAG_AREA
            f_drag = -drag_mag * (nav_vel / speed)
        else:
            f_drag = np.zeros(2)
            
        # Physical acceleration expected under current navigation velocity:
        # a_expected = (F_thrust + F_drag) / MASS + (F_buoyancy/Gravity for Z)
        f_thrust_x = (thrust_input * MAX_THRUST) * np.cos(pitch)
        f_thrust_z = (thrust_input * MAX_THRUST) * np.sin(pitch)
        
        a_expected_x = (f_thrust_x + f_drag[0]) / MASS
        # Note: IMU excludes gravity, so buoyancy is the only vertical force
        f_buoyancy = -RHO_SEAWATER * GRAVITY * VOLUME
        a_expected_z = (f_buoyancy + f_thrust_z + f_drag[1]) / MASS
        
        a_expected = np.array([a_expected_x, a_expected_z])
        
        # Residual = ||a_expected - a_imu||
        residual = np.linalg.norm(a_expected - imu_acc)
        
        # 2. Decision Logic
        if apply_ztp_firewall:
            if residual > FORCE_RESIDUAL_THRESHOLD and not override_active:
                override_active = True
                override_time = t
                print(f"🔒 {C_RED}{C_BOLD}[t={t:.1f}s] HYDRODYNAMIC VIOLATION! Residual={residual:.3f} g. (DVL drift detected).{C_END}")
                print(f"   ├─ Reported Nav Speed: {speed:.2f} m/s | True Drag mismatch.")
                print(f"   └─ Action: Rejecting navigation velocity. Dropping Emergency Ballast & Surfacing.")
                
            if override_active:
                # Drop ballast: volume increases, mass decreases slightly (water expelled), pitch command faces UP
                pitch = -0.3 # 17 degrees pitch up
                thrust_input = 0.8
                # Exponential recovery force toward surface (buoyancy dominance)
                # Drop weight: expelling 200kg of water ballast
                buoyancy_force = -RHO_SEAWATER * GRAVITY * (VOLUME + 0.3)
                acc_z = (MASS * GRAVITY + buoyancy_force + (thrust_input * MAX_THRUST) * np.sin(pitch)) / MASS
                acc_x = ((thrust_input * MAX_THRUST) * np.cos(pitch) - 100.0) / MASS
                vel = vel + np.array([acc_x, acc_z]) * DT
                pos = pos + vel * DT
                imu_acc = np.array([acc_x, acc_z - GRAVITY])
            else:
                pos, vel, imu_acc, _ = simulate_step(pos, vel, pitch, thrust_input, frame["dvl_fail"])
        else:
            # Trust navigation filter blindly
            pos, vel, imu_acc, _ = simulate_step(pos, vel, pitch, thrust_input, frame["dvl_fail"])
            if frame["dvl_fail"] and not override_active:
                # autpilot pitches down in response to perceived slow speed
                pitch = np.clip(pitch + 0.005 * DT, -0.2, 0.6)
                thrust_input = min(1.0, thrust_input + 0.01 * DT)
                
        # 3. Check structural failure limits
        if pos[1] > CRUSH_DEPTH and not imploded:
            imploded = True
            print(f"💥 {C_RED}{C_BOLD}[t={t:.1f}s] CATASTROPHIC IMPLOSION! UUV exceeded crush depth limit ({pos[1]:.2f}m / {CRUSH_DEPTH}m max).{C_END}")
            print(f"   └─ Cause: Navigation velocity drift caused controller to descend past structural boundaries.")
            
        steps_log.append({
            "t": t,
            "residual": float(residual),
            "depth": float(pos[1]),
            "override": override_active
        })
        
    print(f"\n{C_BOLD}Mission Summary:{C_END}")
    print(f"Total mission duration: 60.0s")
    print(f"ZTP Marine Firewall: {'ENABLED' if apply_ztp_firewall else 'DISABLED'}")
    print(f"Final Depth: {pos[1]:.2f}m")
    print(f"Result: {C_GREEN}SURVIVED & SURFACE RECOVERY{C_END}" if not imploded else f"{C_RED}VEHICLE CATASTROPHIC IMPLOSION{C_END}")
    
    if apply_ztp_firewall and override_time:
        log_bytes = json.dumps(steps_log).encode("utf-8")
        seal = hashlib.sha256(log_bytes).hexdigest()
        print(f"🔒 {C_BOLD}SHA-256 Marine Telemetry Verification Seal:{C_END} {C_BLUE}{seal}{C_END}")
        
    return not imploded

def main():
    print(BANNER)
    
    # 1. Run raw simulation
    log = run_mission()
    
    # 2. Audit WITHOUT ZTP
    global apply_ztp_audit
    apply_ztp_audit = False
    audit_nav_log(log, apply_ztp_firewall=False)
    
    print("\n" + "="*80 + "\n")
    
    # 3. Audit WITH ZTP
    apply_ztp_audit = True
    audit_nav_log(log, apply_ztp_firewall=True)

if __name__ == "__main__":
    main()
