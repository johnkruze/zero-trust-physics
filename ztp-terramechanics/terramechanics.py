#!/usr/bin/env python3
"""
ZTP-TERRAMECHANICS: Lunar Rover Terramechanics & Traction Control Auditor.
Part of the Zero-Trust Physics runtime assurance framework.

This tool solves a critical hardware-reliability bottleneck for space exploration rovers:
Wheel slippage and axle sinkage (burial) on loose lunar regolith. It implements a 500Hz real-time 
terramechanics auditor that monitors wheel slip and overrides motor torque to regulate slip to the 
optimal traction peak, preventing the rover from digging itself into a permanent grave.
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
  ███████╗████████╗██████╗     ████████╗███████╗██████╗  ██████╗  █████╗ 
  ╚══███╔╝╚══██╔══╝██╔══██╗    ╚══██╔══╝██╔════╝██╔══██╗██╔═══██╗██╔══██╗
    ███╔╝    ██║   ██████╔╝       ██║   █████╗  ██████╔╝██║   ██║███████║
   ███╔╝     ██║   ██╔═══╝        ██║   ██╔══╝  ██╔══██╗██║   ██║██╔══██║
  ███████╗   ██║   ██║            ██║   ███████╗██║  ██║╚██████╔╝██║  ██║
  ╚══════╝   ╚═╝   ╚═╝            ╚═╝   ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝
  Zero-Trust Physics: Lunar Rover Terramechanics & Traction Control Auditor
================================================================================{C_END}
"""

# Simulation Constants
HZ = 500.0              # 500 Hz control loop cycle
DT = 1.0 / HZ
TOTAL_TIME = 3.0        # 3.0 seconds total simulation time
TOTAL_STEPS = int(TOTAL_TIME * HZ)

# Physical Rover and Wheel Parameters
I_WHEEL = 0.1           # kg*m^2 wheel rotational inertia
R_WHEEL = 0.15          # meters wheel radius (30 cm diameter)
M_ROVER = 20.0          # kg rover mass supported by this wheel
F_NORMAL = 80.0         # N normal load on the wheel (80 N)
GRAVITY_LUNAR = 1.62    # m/s^2 lunar gravity acceleration
SLOPE_DEG = 12.0        # 12 degrees slope incline
SLOPE_RAD = np.radians(SLOPE_DEG)

SINKAGE_STUCK_LIMIT = 0.08 # 8 cm sinkage threshold (axle buried, rover immobilized)

def run_rover_mission(apply_ztp):
    """
    Simulates a lunar rover climbing a 12-degree regolith slope.
    At t = 1.0s to 2.2s: The rover enters a loose, low-cohesion dust pocket (cohesion drops by 90%).
    Without ZTP: The velocity controller spins the wheel to maintain speed, burying the axle.
    With ZTP: The Traction Control System overrides torque, maintaining optimal 15% slip and driving out.
    """
    print(f"\n{C_BOLD}Auditing Rover Mobility Loop (ZTP Traction Control System: {'ENABLED' if apply_ztp else 'DISABLED'}){C_END}")
    print("-" * 95)
    
    # Initial states
    v = 1.0       # m/s initial linear speed
    omega = 8.0   # rad/s initial wheel angular velocity
    
    # PI velocity controller (nominal target v = 1.0 m/s)
    v_ref = 1.0
    Kp_v = 100.0
    Ki_v = 20.0
    integral_err = 0.0
    
    max_sinkage = 0.0
    stuck_tripped = False
    stuck_time = None
    
    tcs_engaged = False
    tcs_time = None
    
    log = []
    pocket_entered_reported = False
    stuck_reported = False
    tcs_reported = False
    
    for step in range(TOTAL_STEPS):
        t = step * DT
        
        # 1. Terramechanics Profile
        is_dust_pocket = (1.0 <= t < 2.2)
        if is_dust_pocket and not pocket_entered_reported:
            pocket_entered_reported = True
            print(f"💥 {C_RED}{C_BOLD}[t={t:.2f}s] ENTERING LOW-COHESION REGOLITH! Maximum friction coefficient drops to 0.04.{C_END}")
            
        mu_max = 0.04 if is_dust_pocket else 0.50
        
        # Calculate wheel slip ratio: s = (w*r - v) / (w*r)
        v_wheel = omega * R_WHEEL
        if v_wheel > 0.001:
            slip = (v_wheel - v) / v_wheel
        else:
            slip = 0.0
        slip = np.clip(slip, 0.0, 0.99)
        
        # Sinkage modeling: z = z_0 + z_slip * slip^2
        z_0 = 0.01 # 1 cm nominal sinkage
        z_slip = 0.12 # slip-sinkage coupling coefficient
        sinkage = z_0 + z_slip * (slip ** 2)
        
        max_sinkage = max(max_sinkage, sinkage)
        
        # Compaction resistance: R_roll = K_comp * sinkage
        K_comp = 100.0 # N/m compaction coefficient
        R_roll = K_comp * sinkage
        if sinkage > 0.05:
            # Axle bulldozing resistance penalty
            R_roll += 150.0 * (sinkage - 0.05)
            
        # Slope gravity drag
        F_gravity_drag = M_ROVER * GRAVITY_LUNAR * np.sin(SLOPE_RAD)
        
        # Tractive effort (Janosi-Hanamoto)
        mu_soil = mu_max * (1.0 - np.exp(-15.0 * slip))
        F_tractive = F_NORMAL * mu_soil
        
        # Check stuck threshold (axle buried)
        if sinkage >= SINKAGE_STUCK_LIMIT and not stuck_tripped:
            stuck_tripped = True
            stuck_time = t
            if not stuck_reported:
                stuck_reported = True
                print(f"🔥 {C_RED}{C_BOLD}[t={t:.3f}s] ROVER IMMOBILIZED! Wheel sinkage ({sinkage*100:.1f} cm) exceeds axle height limit ({SINKAGE_STUCK_LIMIT*100} cm).{C_END}")
                
        # 2. PI Speed Controller
        err_v = v_ref - v
        integral_err += err_v * DT
        tau_cmd = Kp_v * err_v + Ki_v * integral_err
        tau_cmd = np.clip(tau_cmd, 0.0, 30.0) # 30 Nm motor limit
        
        # 3. ZTP Real-Time Traction Control Override
        if apply_ztp:
            # If wheel slip exceeds 25%, override motor torque to regulate slip to optimal 15%
            if slip > 0.25:
                tcs_engaged = True
                if not tcs_reported:
                    tcs_reported = True
                    tcs_time = t
                    print(f"🔒 {C_GREEN}{C_BOLD}[t={t:.3f}s] TRACTION CONTROL ENGAGED! Wheel slip ({slip*100:.1f}%) exceeds safety envelope (>25%).{C_END}")
                    print(f"   ├─ Action: OVERRIDING VELOCITY LOOP (Clipping motor torque to prevent wheel spin-out).")
                    print(f"   └─ Status: Regulating slip ratio to optimal tractive peak (15% slip).")
                    
                # Regulate angular velocity to target 15% slip
                omega_target = v / (R_WHEEL * 0.85)
                tau_cmd = 15.0 * (omega_target - omega)
                tau_cmd = np.clip(tau_cmd, 0.0, 4.0) # limit torque to prevent spinning
                
        # 4. Integrate physical dynamics
        if stuck_tripped:
            v = 0.0
            omega += (tau_cmd / I_WHEEL) * DT
        else:
            # Wheel rotational dynamics: dw/dt = (tau - r * F_tractive) / I
            domega = (tau_cmd - R_WHEEL * F_tractive) / I_WHEEL
            omega += domega * DT
            if omega < 0.0:
                omega = 0.0
                
            # Rover forward translation: dv/dt = (F_tractive - R_roll - F_drag) / M
            dv = (F_tractive - R_roll - F_gravity_drag) / M_ROVER
            v += dv * DT
            if v < 0.0:
                v = 0.0
                
        log.append({
            "t": t,
            "v": float(v),
            "omega": float(omega),
            "slip": float(slip),
            "sinkage": float(sinkage),
            "tcs_engaged": bool(tcs_engaged),
            "stuck": bool(stuck_tripped)
        })
        
    print(f"\n{C_BOLD}Rover Mobility Summary:{C_END}")
    print(f"Total test time: {TOTAL_TIME:.1f} s")
    print(f"ZTP Safety Auditor: {'ENABLED' if apply_ztp else 'DISABLED'}")
    print(f"Maximum Axle Sinkage: {max_sinkage*100:.2f} cm")
    print(f"Final Forward Velocity: {v:.3f} m/s")
    print(f"Result: {C_GREEN}CLIMB SUCCESSFUL (Exited dust pocket safely){C_END}" if not stuck_tripped else f"{C_RED}MISSION FAILURE (Rover grounded in dust pocket){C_END}")
    
    if apply_ztp and not stuck_tripped:
        log_bytes = json.dumps(log).encode("utf-8")
        seal = hashlib.sha256(log_bytes).hexdigest()
        print(f"🔒 {C_BOLD}SHA-256 Terramechanical Seal:{C_END} {C_BLUE}{seal}{C_END}")
        
    return not stuck_tripped

def main():
    print(BANNER)
    
    # 1. Run simulation WITHOUT ZTP (rover gets stuck at t=1.31s)
    run_rover_mission(apply_ztp=False)
    
    print("\n" + "="*80 + "\n")
    
    # 2. Run simulation WITH ZTP (rover climbs out successfully)
    run_rover_mission(apply_ztp=True)

if __name__ == "__main__":
    main()
