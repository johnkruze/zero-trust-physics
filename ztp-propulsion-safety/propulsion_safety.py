#!/usr/bin/env python3
"""
ZTP-PROPULSION-SAFETY: Real-Time embedded Rocket Propulsion Valve Auditor.
Part of the Zero-Trust Physics runtime assurance framework.

This tool solves a critical hardware-reliability bottleneck for space and defense propulsion
systems: Propellant control valve mechanical seizure (sticking open)
during hot-fire or flight operations. It implements a 1000Hz real-time physical state auditor 
to detect actuator mismatches and execute emergency isolation before chamber over-pressure explosion.
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
  ███████╗████████╗██████╗     ██████╗ ██████╗  ██████╗ ██████╗ 
  ╚══███╔╝╚══██╔══╝██╔══██╗    ██╔══██╗██╔══██╗██╔═══██╗██╔══██╗
    ███╔╝    ██║   ██████╔╝    ██████╔╝██████╔╝██║   ██║██████╔╝
   ███╔╝     ██║   ██╔═══╝     ██╔═══╝ ██╔══██╗██║   ██║██╔═══╝ 
  ███████╗   ██║   ██║         ██║     ██║  ██║╚██████╔╝██║     
  ╚══════╝   ╚═╝   ╚═╝         ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝     
  Zero-Trust Physics: Rocket Propulsion Safety & Valve Auditor
================================================================================{C_END}
"""

# Simulation Constants
HZ = 1000.0             # 1 kHz control loop cycle
DT = 1.0 / HZ
TOTAL_TIME = 2.0        # 2.0 seconds total simulation time
TOTAL_STEPS = int(TOTAL_TIME * HZ)

# Physical Rocket Thruster Parameters
V_TARGET = 50.0         # 50 bar operating chamber pressure
BURST_LIMIT = 60.0      # 60 bar structural burst threshold
TAU_VALVE = 0.05        # 50ms valve actuator time constant

def run_propulsion_mission(apply_ztp):
    """
    Simulates a rocket engine hot-fire test.
    At t = 1.0s: The primary propellant valve experiences mechanical seizure and jams wide open.
    Without ZTP: The chamber pressure surges past 60 bar, leading to structural explosion.
    With ZTP: The physical validator detects the valve feedback anomaly and isolates propellant flow.
    """
    print(f"\n{C_BOLD}Auditing Rocket Chamber pressure Loop (ZTP Safety Auditor: {'ENABLED' if apply_ztp else 'DISABLED'}){C_END}")
    print("-" * 95)
    
    P_c = V_TARGET
    A_valve = 0.9 # nominal open position for 50 bar
    A_valve_expected = 0.9
    
    # PI Controller gains
    Kp = 0.05
    Ki = 0.5
    integral_err = 0.0
    
    explosion_tripped = False
    explosion_time = None
    max_pressure = P_c
    
    is_safe_shutdown = False
    shutdown_time = None
    
    P_c_history = [P_c]
    log = []
    
    failure_reported = False
    shutdown_reported = False
    
    for step in range(TOTAL_STEPS):
        t = step * DT
        
        # 1. Failure Event (t >= 1.0s)
        is_failure = (t >= 1.0)
        if is_failure and not failure_reported:
            failure_reported = True
            print(f"💥 {C_RED}{C_BOLD}[t={t:.2f}s] VALVE MECHANICAL SEIZURE! Actuator stuck open at A_valve = 1.2.{C_END}")
            
        # PI Control Loop
        err = V_TARGET - P_c
        integral_err += err * DT
        u = 0.9 + Kp * err + Ki * integral_err
        u = np.clip(u, 0.0, 1.0)
        
        # Upstream isolation check
        if is_safe_shutdown:
            u = 0.0
            
        # Physical valve dynamics
        if is_failure and not is_safe_shutdown:
            # Physical valve jammed at 1.2
            A_valve = 1.2
        else:
            # Normal valve response with first-order lag
            dA_valve = (u - A_valve) / TAU_VALVE
            A_valve += dA_valve * DT
            
        # Expected valve position (software model)
        dA_valve_exp = (u - A_valve_expected) / TAU_VALVE
        A_valve_expected += dA_valve_exp * DT
        
        # 2. Chamber Pressure Physics
        # dPc/dt = 120 * A_valve - 2.16 * Pc
        dP_c = 120.0 * A_valve - 2.16 * P_c
        P_c += dP_c * DT
        P_c_history.append(P_c)
        
        max_pressure = max(max_pressure, P_c)
        
        # 3. Check structural burst limit
        if P_c > BURST_LIMIT and not explosion_tripped:
            explosion_tripped = True
            explosion_time = t
            print(f"🔥 {C_RED}{C_BOLD}[t={t:.3f}s] CHAMBER STRUCTURAL EXPLOSION! Pressure {P_c:.2f} bar exceeds burst limit ({BURST_LIMIT} bar).{C_END}")
            
        # 4. ZTP Real-Time Embedded Physics Audit
        if apply_ztp and step > 1 and not is_safe_shutdown:
            # Reconstruct expected dPc/dt from sensor telemetry
            dP_c_est = (P_c_history[-1] - P_c_history[-2]) / DT
            
            # Reconstruct physical valve opening using the physical invariant:
            # A_valve = (dPc/dt + 2.16 * Pc) / 120.0
            A_valve_observed = (dP_c_est + 2.16 * P_c) / 120.0
            
            # Check for mismatch against command-derived expectation
            mismatch = abs(A_valve_observed - A_valve_expected)
            
            if mismatch > 0.2:
                is_safe_shutdown = True
                shutdown_time = t
                if not shutdown_reported:
                    shutdown_reported = True
                    print(f"🔒 {C_GREEN}{C_BOLD}[t={t:.3f}s] VALVE MISMATCH DETECTED! Observed ({A_valve_observed:.2f}) != Expected ({A_valve_expected:.2f}).{C_END}")
                    print(f"   ├─ Action: TRIPPING UPSTREAM OXIDIZER ISOLATION VALVE (Automatic containment).")
                    print(f"   └─ Status: Venting chamber pressure safely.")
                    
        log.append({
            "t": t,
            "P_c": float(P_c),
            "A_valve": float(A_valve),
            "A_valve_expected": float(A_valve_expected),
            "safe_shutdown": bool(is_safe_shutdown),
            "exploded": bool(explosion_tripped)
        })
        
    print(f"\n{C_BOLD}Propulsion System Summary:{C_END}")
    print(f"Total test time: {TOTAL_TIME:.1f} s")
    print(f"ZTP Safety Auditor: {'ENABLED' if apply_ztp else 'DISABLED'}")
    print(f"Peak Chamber Pressure: {max_pressure:.2f} bar")
    print(f"Result: {C_GREEN}ENGINE SAFE (Containment Successful){C_END}" if is_safe_shutdown and not explosion_tripped else f"{C_RED}CATASTROPHIC ENGINE FAILURE (Explosion){C_END}")
    
    if apply_ztp and is_safe_shutdown:
        log_bytes = json.dumps(log).encode("utf-8")
        seal = hashlib.sha256(log_bytes).hexdigest()
        print(f"🔒 {C_BOLD}SHA-256 Safety Telemetry Seal:{C_END} {C_BLUE}{seal}{C_END}")
        
    return is_safe_shutdown

def main():
    print(BANNER)
    
    # 1. Run simulation WITHOUT ZTP (explodes at t=1.42s)
    run_propulsion_mission(apply_ztp=False)
    
    print("\n" + "="*80 + "\n")
    
    # 2. Run simulation WITH ZTP (isolates at t=1.00s)
    run_propulsion_mission(apply_ztp=True)

if __name__ == "__main__":
    main()
