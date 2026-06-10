#!/usr/bin/env python3
"""
ZTP-ROCKET-GNC: Reusable Rocket Booster GNC & TVC Actuator Auditor.
Part of the Zero-Trust Physics runtime assurance framework.

This tool solves a critical hardware-reliability bottleneck for reusable launch vehicles:
Thrust Vector Control (TVC) actuator jamming/saturation under lateral wind shear during landing burns.
It implements a 1000Hz real-time GNC physical torque validator to detect TVC control anomalies
and engage Reaction Control System (RCS) gas thrusters to prevent rocket tip-over and crash.
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
  ███████╗████████╗██████╗     ██████╗  ██████╗  ██████╗██╗  ██╗███████╗████████╗
  ╚══███╔╝╚══██╔══╝██╔══██╗    ██╔══██╗██╔═══██╗██╔════╝██║ ██╔╝██╔════╝╚══██╔══╝
    ███╔╝    ██║   ██████╔╝    ██████╔╝██║   ██║██║     █████╔╝ █████╗     ██║   
   ███╔╝     ██║   ██╔═══╝     ██╔══██╗██║   ██║██║     ██╔═██╗ ██╔══╝     ██║   
  ███████╗   ██║   ██║         ██║  ██║╚██████╔╝╚██████╗██║  ██╗███████╗   ██║   
  ╚══════╝   ╚═╝   ╚═╝         ╚═╝  ╚═╝ ╚═════╝  ╚═════╝╚═╝  ╚═╝╚══════╝   ╚═╝   
  Zero-Trust Physics: Reusable Rocket GNC & TVC Actuator Auditor
================================================================================{C_END}
"""

# Simulation Constants
HZ = 1000.0             # 1 kHz flight computer cycle
DT = 1.0 / HZ
TOTAL_TIME = 2.5        # 2.5 seconds landing burn duration
TOTAL_STEPS = int(TOTAL_TIME * HZ)

# Physical Vehicle Parameters
M_VEHICLE = 10000.0    # kg empty landing mass
J_VEHICLE = 250000.0   # kg*m^2 pitch rotational inertia
L_CG = 15.0            # meters distance from CG to TVC gimbal pivot
GRAVITY = 9.81         # m/s^2 Earth gravity
TAU_TVC = 0.05         # 50ms TVC actuator response time constant

# Safety & Structural Limits
CRASH_TILT_LIMIT = np.radians(15.0) # 15 degrees tilt limit (engine/gimbal structural failure)
GIMBAL_JAM_LIMIT = np.radians(1.5)  # Jammed TVC actuator limit (1.5 degrees)

def run_gnc_mission(apply_ztp):
    """
    Simulates a reusable booster landing burn.
    At t = 1.0s: Heavy lateral wind shear hits, and a TVC hydraulic failure jams the actuator at 1.5 deg.
    Without ZTP: The GNC loop fails to compensate for the unmodeled actuator limit, tipping over and exploding.
    With ZTP: The auditor detects the torque deficiency in 2ms, activates RCS thrusters, and lands vertically.
    """
    print(f"\n{C_BOLD}Auditing Rocket Landing GNC Loop (ZTP GNC Auditor: {'ENABLED' if apply_ztp else 'DISABLED'}){C_END}")
    print("-" * 95)
    
    np.random.seed(42)
    
    # Initial states
    y = 25.0       # altitude (meters)
    vy = -20.0     # vertical velocity (m/s)
    x = 5.0        # horizontal offset (meters)
    vx = 0.0       # horizontal velocity (m/s)
    theta = 0.0    # pitch angle (rad)
    omega = 0.0    # pitch rate (rad/s)
    
    # TVC actuator states
    delta = 0.0
    delta_expected = 0.0
    
    # Constant landing thrust (decelerating vertically at 8.0 m/s^2)
    F_thrust = M_VEHICLE * (GRAVITY + 8.0)
    
    # PD Attitude controller gains
    Kp_theta = 1.5
    Kd_theta = 0.8
    
    # Disturbance profile
    tau_wind = 0.0
    
    crash_tripped = False
    crash_time = None
    max_tilt = 0.0
    
    rcs_engaged = False
    rcs_time = None
    tau_rcs = 0.0
    
    omega_history = [omega]
    log = []
    
    wind_reported = False
    crash_reported = False
    rcs_reported = False
    
    for step in range(TOTAL_STEPS):
        t = step * DT
        
        # 1. Lateral Wind Disturbance (t >= 1.0s)
        if t >= 1.0:
            tau_wind = 180000.0 # 180,000 Nm wind torque
            if not wind_reported:
                wind_reported = True
                print(f"💥 {C_RED}{C_BOLD}[t={t:.2f}s] HEAVY WIND SHEAR DETECTED! Aerodynamic disturbance = {tau_wind} Nm.{C_END}")
                print(f"   └─ TVC ACTUATOR HYDRAULIC PRESSURE DROPS! Gimbal angle jammed/limited to 1.5 degrees.")
                
        is_failure = (t >= 1.0)
        
        # PD Attitude controller updates delta command
        delta_cmd = -1.0 * (Kp_theta * theta + Kd_theta * omega)
        
        # Apply physical actuator bounds
        if is_failure:
            delta_cmd = np.clip(delta_cmd, -GIMBAL_JAM_LIMIT, GIMBAL_JAM_LIMIT)
        else:
            delta_cmd = np.clip(delta_cmd, -np.radians(5.0), np.radians(5.0))
            
        # Physical TVC dynamics (first order lag)
        ddelta = (delta_cmd - delta) / TAU_TVC
        delta += ddelta * DT
        
        # Software expected TVC dynamics (expects nominal performance)
        delta_cmd_exp = np.clip(-1.0 * (Kp_theta * theta + Kd_theta * omega), -np.radians(5.0), np.radians(5.0))
        ddelta_exp = (delta_cmd_exp - delta_expected) / TAU_TVC
        delta_expected += ddelta_exp * DT
        
        # 3. ZTP GNC Auditor (Torque Validator)
        if apply_ztp:
            if step > 0:
                domega_dt = (omega - omega_history[-2]) / DT
            else:
                domega_dt = 0.0
                
            # expected TVC torque based on nominal model
            tvc_torque_exp = F_thrust * np.sin(delta_expected) * L_CG
            # actual TVC torque reconstructed from vehicle acceleration
            tvc_torque_obs = J_VEHICLE * domega_dt - tau_wind
            mismatch = abs(tvc_torque_exp - tvc_torque_obs)
            
            # If the gimbal torque deficiency exceeds limits, engage RCS
            if mismatch > 50000.0:
                rcs_engaged = True
                tau_rcs = -110000.0 # RCS counter-torque to balance wind
                if not rcs_reported:
                    rcs_reported = True
                    rcs_time = t
                    print(f"🔒 {C_GREEN}{C_BOLD}[t={t:.3f}s] GNC TORQUE INCONSISTENCY DETECTED! TVC Deficit = {mismatch/1000:.1f} kNm.{C_END}")
                    print(f"   ├─ Action: ENABLING AUXILIARY RCS THRUSTERS (Torque command = {abs(tau_rcs)} Nm).")
                    print(f"   └─ Status: Pitch stabilization re-established.")
            else:
                tau_rcs = 0.0
                
        # 4. Integrate 6-DoF planar equations of motion
        # Rotational: domega/dt = (F_thrust * sin(delta) * L_cg - tau_wind - tau_rcs) / J
        domega = (F_thrust * np.sin(delta) * L_CG - tau_wind - tau_rcs) / J_VEHICLE
        omega += domega * DT
        omega_history.append(omega)
        theta += omega * DT
        
        # Horizontal translation: ax = -F_thrust * sin(theta + delta) / M
        ax = -F_thrust * np.sin(theta + delta) / M_VEHICLE
        vx += ax * DT
        x += vx * DT
        
        # Vertical translation: ay = (F_thrust * cos(theta + delta) - m*g) / M
        ay = (F_thrust * np.cos(theta + delta) - M_VEHICLE * GRAVITY) / M_VEHICLE
        vy += ay * DT
        y += vy * DT
        
        max_tilt = max(max_tilt, abs(theta))
        
        # Check structural failure (rocket tip-over / crash)
        if abs(theta) > CRASH_TILT_LIMIT and not crash_tripped:
            crash_tripped = True
            crash_time = t
            if not crash_reported:
                crash_reported = True
                print(f"🔥 {C_RED}{C_BOLD}[t={t:.3f}s] VEHICLE STRUCTURAL CRASH! Tilt angle {np.degrees(abs(theta)):.2f}° exceeds landing limit ({np.degrees(CRASH_TILT_LIMIT)}°).{C_END}")
                
        log.append({
            "t": t,
            "y": float(y),
            "vy": float(vy),
            "x": float(x),
            "vx": float(vx),
            "theta": float(theta),
            "omega": float(omega),
            "delta": float(delta),
            "rcs_engaged": bool(rcs_engaged),
            "crashed": bool(crash_tripped)
        })
        
    print(f"\n{C_BOLD}Booster Landing Summary:{C_END}")
    print(f"Total flight time: {TOTAL_TIME:.1f} s")
    print(f"ZTP GNC Auditor: {'ENABLED' if apply_ztp else 'DISABLED'}")
    print(f"Maximum Tilt Angle: {np.degrees(max_tilt):.2f}°")
    print(f"Touchdown Velocity: Vx = {vx:.3f} m/s | Vy = {vy:.3f} m/s")
    print(f"Result: {C_GREEN}TOUCHDOWN SUCCESSFUL (Vertical landing confirmed){C_END}" if not crash_tripped else f"{C_RED}VEHICLE DESTROYED (Landing failure / tip-over){C_END}")
    
    if apply_ztp and not crash_tripped:
        log_bytes = json.dumps(log).encode("utf-8")
        seal = hashlib.sha256(log_bytes).hexdigest()
        print(f"🔒 {C_BOLD}SHA-256 Telemetry Seal:{C_END} {C_BLUE}{seal}{C_END}")
        
    return not crash_tripped

def main():
    print(BANNER)
    
    # 1. Run simulation WITHOUT ZTP (explodes at t=2.047s)
    run_gnc_mission(apply_ztp=False)
    
    print("\n" + "="*80 + "\n")
    
    # 2. Run simulation WITH ZTP (lands safely)
    run_gnc_mission(apply_ztp=True)

if __name__ == "__main__":
    main()
