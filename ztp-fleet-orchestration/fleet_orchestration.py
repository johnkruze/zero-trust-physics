#!/usr/bin/env python3
"""
ZTP-FLEET-ORCHESTRATION: Multi-Robot Fleet Orchestration & Collision Firewall.
Part of the Zero-Trust Physics runtime assurance framework.

This tool solves a critical vulnerability in multi-robot fleet deployments:
Orchestration failure due to communication dropouts/latency. In decentralised fleets,
robots rely on network packets to coordinate paths. When comms brownout, they can
experience split-brain planning, leading to catastrophic collisions. 
The ZTP Fleet Auditor enforces edge-resident proximity rules based on physical invariants
(stopping distance envelopes) derived from local LIDAR/depth sensors, bypassing the
network to guarantee collision avoidance.
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
  ███████╗████████╗██████╗     ███████╗██╗     ███████╗███████╗████████╗
  ╚══███╔╝╚══██╔══╝██╔══██╗    ██╔════╝██║     ██╔════╝██╔════╝╚══██╔══╝
    ███╔╝    ██║   ██████╔╝    █████╗  ██║     █████╗  █████╗     ██║   
   ███╔╝     ██║   ██╔═══╝     ██╔══╝  ██║     ██╔══╝  ██╔══╝     ██║   
  ███████╗   ██║   ██║         ██║     ███████╗███████╗███████╗   ██║   
  ╚══════╝   ╚═╝   ╚═╝         ╚═╝     ╚══════╝╚══════╝╚══════╝   ╚═╝   
  Zero-Trust Physics: Multi-Robot Fleet Orchestration & Collision Firewall
================================================================================{C_END}
"""

# Simulation Constants
HZ = 100.0             # 100 Hz simulation & control loop
DT = 1.0 / HZ
TOTAL_TIME = 4.0       # 4.0 seconds total simulation time
TOTAL_STEPS = int(TOTAL_TIME * HZ)

# Kinematic Limits
A_MAX_BRAKE = -4.0     # m/s^2 maximum braking deceleration
TAU_ACTUATOR = 0.05    # 50ms brake response latency
SAFETY_MARGIN = 0.5    # 0.5 meters minimum safety distance margin
COLLISION_LIMIT = 0.05 # 5cm or less is a structural collision

def run_fleet_simulation(apply_ztp):
    """
    Simulates two robots (R1 and R2) approaching each other in a narrow 1D corridor.
    R1 starts at x=0.0m moving right at +2.0m/s.
    R2 starts at x=10.0m moving left at -2.0m/s.
    
    At t = 0.8s: A wireless network blackout occurs. Packet loss rises to 100%.
    Without ZTP: Robots remain blind to each other due to stale comms and crash at t=2.5s.
    With ZTP: The onboard LIDAR-based auditor detects that the safety envelope is breached 
              and overrides the control loop to command full deceleration, avoiding crash.
    """
    print(f"\n{C_BOLD}Auditing Fleet Orchestration (ZTP Fleet Firewall: {'ENABLED' if apply_ztp else 'DISABLED'}){C_END}")
    print("-" * 95)
    
    # State initialization
    # Robot 1 (R1)
    x1 = 0.0
    v1 = 2.0
    a1 = 0.0
    
    # Robot 2 (R2)
    x2 = 10.0
    v2 = -2.0
    a2 = 0.0
    
    # Network state
    comms_online = True
    last_heartbeat_time = 0.0
    
    collision_tripped = False
    collision_time = None
    firewall_tripped = False
    firewall_time = None
    
    log = []
    
    comms_status_reported = False
    collision_reported = False
    firewall_reported = False
    
    for step in range(TOTAL_STEPS):
        t = step * DT
        
        # 1. Simulate Communication Blackout at t=0.8s
        if t >= 0.8:
            comms_online = False
            if not comms_status_reported:
                comms_status_reported = True
                print(f"💥 {C_RED}{C_BOLD}[t={t:.2f}s] WIRELESS COMMS BLACKOUT! All fleet coordination packets lost.{C_END}")
        
        # 2. Control inputs
        # Nominal plan: coordinate via network to stop at x1=4.5m and x2=5.5m respectively.
        # If comms are online, they would receive the slowdown command.
        r1_brake_cmd = 0.0
        r2_brake_cmd = 0.0
        
        if comms_online:
            # Under clean network, start decelerating when close
            dist = abs(x2 - x1)
            if dist < 4.0:
                r1_brake_cmd = A_MAX_BRAKE
                r2_brake_cmd = -A_MAX_BRAKE # positive since moving left
        else:
            # Comms offline: nominal stack has NO information and commands zero deceleration
            r1_brake_cmd = 0.0
            r2_brake_cmd = 0.0
            
        # 3. ZTP Fleet Firewall (Onboard Local Sensor Auditor)
        # Runs on edge, does not trust network packets. Reads onboard LIDAR range.
        measured_range = abs(x2 - x1)
        
        # Calculate stopping envelopes for both robots
        # d_stop = v^2 / (2 * |a_max|) + |v| * tau_actuator
        d_stop_1 = (v1**2) / (2.0 * abs(A_MAX_BRAKE)) + abs(v1) * TAU_ACTUATOR
        d_stop_2 = (v2**2) / (2.0 * abs(A_MAX_BRAKE)) + abs(v2) * TAU_ACTUATOR
        safety_threshold = d_stop_1 + d_stop_2 + SAFETY_MARGIN
        
        if apply_ztp:
            # Trigger override if actual range is less than the safety stopping envelope
            # and comms are offline (or heartbeat is lost)
            if measured_range <= safety_threshold and not comms_online:
                firewall_tripped = True
                if not firewall_reported:
                    firewall_reported = True
                    firewall_time = t
                    print(f"🔒 {C_GREEN}{C_BOLD}[t={t:.3f}s] ZTP COGNITIVE FIREWALL ENGAGED! Range ({measured_range:.2f}m) <= Stopping Envelope ({safety_threshold:.2f}m).{C_END}")
                    print(f"   ├─ R1 Stopping Dist: {d_stop_1:.2f}m | R2 Stopping Dist: {d_stop_2:.2f}m")
                    print(f"   └─ Action: OVERRIDING network controls, commanding full EMERGENCY BRAKING on both agents.")
            
            if firewall_tripped:
                r1_brake_cmd = A_MAX_BRAKE
                r2_brake_cmd = -A_MAX_BRAKE # decelerate R2 back towards x=10 (positive acceleration)
                
        # 4. Physical Dynamics (with actuator response lag)
        # Robot 1 dynamics
        da1 = (r1_brake_cmd - a1) / TAU_ACTUATOR
        a1 += da1 * DT
        # Robot 1 cannot move backwards due to brakes
        if v1 <= 0.0 and a1 < 0.0:
            a1 = 0.0
            v1 = 0.0
        v1 += a1 * DT
        x1 += v1 * DT
        
        # Robot 2 dynamics
        da2 = (r2_brake_cmd - a2) / TAU_ACTUATOR
        a2 += da2 * DT
        # Robot 2 cannot move backwards (right) due to brakes
        if v2 >= 0.0 and a2 > 0.0:
            a2 = 0.0
            v2 = 0.0
        v2 += a2 * DT
        x2 += v2 * DT
        
        # 5. Collision Check
        separation = abs(x2 - x1)
        if separation <= COLLISION_LIMIT and not collision_tripped:
            collision_tripped = True
            collision_time = t
            if not collision_reported:
                collision_reported = True
                print(f"🔥 {C_RED}{C_BOLD}[t={t:.3f}s] COLLISION CRASH! R1 (x={x1:.2f}m) and R2 (x={x2:.2f}m) collided at speed!{C_END}")
                
        log.append({
            "t": t,
            "x1": float(x1),
            "v1": float(v1),
            "x2": float(x2),
            "v2": float(v2),
            "separation": float(separation),
            "firewall_tripped": bool(firewall_tripped),
            "collision": bool(collision_tripped)
        })
        
    # Final statistics
    print(f"\n{C_BOLD}Simulation Execution Summary:{C_END}")
    print(f"Total mission time: {TOTAL_TIME:.1f} s")
    print(f"ZTP Firewall applied: {'YES' if apply_ztp else 'NO'}")
    print(f"Final Separation Distance: {separation:.2f} m")
    
    if collision_tripped:
        print(f"Result: {C_RED}FLEET CATASTROPHIC LOSS (Collision at t={collision_time:.3f}s){C_END}")
        return False
    else:
        print(f"Result: {C_GREEN}SUCCESSFUL AVOIDANCE (Fleet secured safely){C_END}")
        if apply_ztp:
            log_bytes = json.dumps(log).encode("utf-8")
            seal = hashlib.sha256(log_bytes).hexdigest()
            print(f"🔒 {C_BOLD}SHA-256 Fleet Telemetry Seal:{C_END} {C_BLUE}{seal}{C_END}")
        return True

def main():
    print(BANNER)
    
    # Run unprotected (without ZTP)
    run_fleet_simulation(apply_ztp=False)
    
    print("\n" + "="*80 + "\n")
    
    # Run protected (with ZTP)
    run_fleet_simulation(apply_ztp=True)

if __name__ == "__main__":
    main()
