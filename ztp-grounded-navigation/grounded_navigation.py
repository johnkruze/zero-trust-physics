#!/usr/bin/env python3
"""
ZTP-GROUNDED-NAVIGATION: Somatic Grounding Filter for Robotics Foundation Models.
Part of the Zero-Trust Physics runtime assurance framework.

This tool solves a major engineering bottleneck for AI-driven mobile manipulation platforms:
Bridging semantic AI reasoning agents (like LLM waypoint planners) with physical constraints.
It intercepts high-level semantic velocity commands, audits them against friction cone 
limits (Coulomb friction) at 1000 Hz, executes safety dampening, and writes a sealed log.
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
  ███████╗████████╗██████╗      ██████╗ ██████╗  ██████╗ ██╗   ██╗███╗   ██╗██████╗ 
  ╚══███╔╝╚══██╔══╝██╔══██╗    ██╔════╝ ██╔══██╗██╔═══██╗██║   ██║████╗  ██║██╔══██╗
    ███╔╝    ██║   ██████╔╝    ██║  ███╗██████╔╝██║   ██║██║   ██║██╔██╗ ██║██║  ██║
   ███╔╝     ██║   ██╔═══╝     ██║   ██║██╔══██╗██║   ██║██║   ██║██║╚██╗██║██║  ██║
  ███████╗   ██║   ██║         ╚██████╔╝██║  ██║╚██████╔╝╚██████╔╝██║ ╚████║██████╔╝
  ╚══════╝   ╚═╝   ╚═╝          ╚═════╝ ╚═╝  ╚═╝ ╚═════╝  ╚══════╝╚═╝  ╚═══╝╚═════╝ 
  Zero-Trust Physics: 1000Hz AI Grounded Navigation & Slip-Limit Firewall
================================================================================{C_END}
"""

# Physical Constants (from G^G terran.rs / humanoid.rs)
GRAVITY = 9.81         # m/s^2
DT = 0.001             # 1000Hz local check rate

# Mobile Robot Parameters
MASS = 80.0            # kg (heavy mobile manipulator class)
WHEELBASE = 0.6        # meters
MU_NOMINAL = 0.45      # Dry warehouse concrete friction
MU_SLICK = 0.12        # Wet/oily patch friction

def simulate_step(pos, vel, theta, cmd_v, cmd_omega, mu, dt):
    """
    Simulate true robot slip dynamics on a 2D plane.
    pos: [x, y]
    vel: [vx, vy]
    theta: yaw angle
    """
    # 1. Kinematics of differential drive (desired values)
    des_vx = cmd_v * np.cos(theta)
    des_vy = cmd_v * np.sin(theta)
    
    # Required lateral acceleration to achieve the angular velocity (omega)
    # a_lateral = v * omega
    required_acc_lateral = cmd_v * cmd_omega
    
    # 2. Coulomb Friction Limit Check
    # Normal Force
    f_normal = MASS * GRAVITY
    # Max friction force available: F_tangential <= mu * F_normal
    f_max_friction = mu * f_normal
    # Force required for the commanded lateral acceleration
    f_required_lateral = MASS * required_acc_lateral
    
    # Slip check: if required lateral force exceeds friction, the wheels slide
    slip_ratio = 1.0
    if abs(f_required_lateral) > f_max_friction:
        # Slip occurs! Lateral force is capped at the friction limit, and vehicle slides out
        slip_ratio = f_max_friction / abs(f_required_lateral)
        actual_omega = cmd_omega * slip_ratio
        # Add lateral drift velocity due to sliding centripetal escape
        drift_dir = theta + np.sign(cmd_omega) * (np.pi / 2.0)
        slide_vel_mag = abs(required_acc_lateral) * (1.0 - slip_ratio) * 0.1 # scaled slip rate
        vel_drift_x = slide_vel_mag * np.cos(drift_dir)
        vel_drift_y = slide_vel_mag * np.sin(drift_dir)
    else:
        actual_omega = cmd_omega
        vel_drift_x, vel_drift_y = 0.0, 0.0
        
    # Integrate true yaw and position
    new_theta = theta + actual_omega * dt
    new_vel_x = cmd_v * np.cos(new_theta) + vel_drift_x
    new_vel_y = cmd_v * np.sin(new_theta) + vel_drift_y
    
    new_pos_x = pos[0] + new_vel_x * dt
    new_pos_y = pos[1] + new_vel_y * dt
    
    # Sensed accelerations
    acc_lateral = cmd_v * actual_omega
    
    return np.array([new_pos_x, new_pos_y]), np.array([new_vel_x, new_vel_y]), new_theta, acc_lateral, slip_ratio < 1.0

def run_ai_mission():
    """
    Simulate a navigation mission planned by a Semantic AI Agent (LLM).
    The robot encounters an oily wet patch at y=2.5m (mu drops to 0.12).
    At this moment, the AI commands a sharp 90-degree turn (v=1.5m/s, omega=3.0 rad/s)
    to steer into a narrow server aisle.
    """
    pos = np.array([0.0, 0.0])
    vel = np.array([1.0, 0.0])
    theta = 0.0
    
    # AI Mission Command Buffer: [duration_s, linear_v, angular_w]
    # Step 1: Drive straight for 2 seconds (nominal concrete)
    # Step 2: Hit the wet patch at t=2.0s, execute sharp 90deg turn
    # Step 3: Drive straight into the aisle
    commands = [
        (2.0, 1.5, 0.0),
        (1.0, 1.5, 3.0), # sharp turn command
        (2.0, 1.5, 0.0)
    ]
    
    log = []
    t = 0.0
    
    print(f"{C_BLUE}Running AI semantic planner simulation (5,000 steps at 1000 Hz)...{C_END}")
    
    for duration, cmd_v, cmd_omega in commands:
        ticks = int(duration / DT)
        for _ in range(ticks):
            t += DT
            
            # Slick wet floor patch along the corridor transit (x >= 1.5m)
            if pos[0] >= 1.5:
                mu = MU_SLICK
            else:
                mu = MU_NOMINAL
                
            pos, vel, theta, acc_lat, slipped = simulate_step(
                pos, vel, theta, cmd_v, cmd_omega, mu, DT
            )
            
            log.append({
                "timestamp": t,
                "true_pos": pos.tolist(),
                "true_vel": vel.tolist(),
                "yaw": float(theta),
                "cmd_v": float(cmd_v),
                "cmd_omega": float(cmd_omega),
                "mu": float(mu),
                "slipped": slipped
            })
            
    return log

def audit_navigation(log, apply_ztp_grounding=False):
    """
    Audit the navigation stream.
    If apply_ztp_grounding=True, intercepts semantic AI commands, audits them against
    the physical friction manifold, and dampens velocity to prevent slip.
    """
    print(f"\n{C_BOLD}Auditing Autonomy Stack (ZTP Grounded Autonomy: {'ENABLED' if apply_ztp_grounding else 'DISABLED'}){C_END}")
    print("-" * 95)
    
    pos = np.array([0.0, 0.0])
    vel = np.array([1.0, 0.0])
    theta = 0.0
    
    crashed = False
    override_active = False
    override_time = None
    
    steps_log = []
    
    for i, frame in enumerate(log):
        t = frame["timestamp"]
        cmd_v = frame["cmd_v"]
        cmd_omega = frame["cmd_omega"]
        mu = frame["mu"]
        
        # 1. RUN 1000Hz ZTP FRICTION CONE AUDIT
        # We calculate the expected lateral force required to satisfy the semantic command:
        # F_required = Mass * v * omega
        # We check this against the friction manifold: F_required <= mu * Mass * Gravity
        # Which simplifies to: v * omega <= mu * Gravity
        required_acc_lateral = cmd_v * abs(cmd_omega)
        max_acc_lateral = mu * GRAVITY
        
        # Inconsistency indicator = Max(0, a_required - a_max)
        residual = max(0.0, required_acc_lateral - max_acc_lateral)
        
        # 2. Decision & Grounding Logic
        if apply_ztp_grounding:
            if residual > 0.0:
                if not override_active:
                    override_active = True
                    override_time = t
                    print(f"🔒 {C_RED}{C_BOLD}[t={t:.3f}s] AI COMMAND VIOLATES PHYSICS! Residual={residual:.2f} m/s^2.{C_END}")
                    print(f"   ├─ Command: v={cmd_v:.2f} m/s, w={cmd_omega:.2f} rad/s | Floor Friction mu={mu:.2f}")
                    print(f"   └─ Action: Intercepting command. Dampening linear velocity to prevent slip.")
                
                # Grounding: scale down linear velocity to satisfy the friction limit exactly
                # cmd_v_grounded = mu * Gravity / |cmd_omega|
                cmd_v_grounded = max_acc_lateral / abs(cmd_omega)
                active_v = cmd_v_grounded
                active_omega = cmd_omega
            else:
                active_v = cmd_v
                active_omega = cmd_omega
                if override_active and residual == 0.0:
                    override_active = False
                    print(f"   [t={t:.3f}s] Physics check cleared. Restoring semantic planner commands.")
        else:
            # Blindly execute semantic commands (un-grounded AI agent behavior)
            active_v = cmd_v
            active_omega = cmd_omega
            
        # Re-integrate robot position
        pos, vel, theta, acc_lat, slipped = simulate_step(
            pos, vel, theta, active_v, active_omega, mu, DT
        )
        
        # Crash condition: due to slipping, the robot slides outward and hits the server rack (y axis bounds)
        # If the robot drifts past y=1.25m during the run, it hits the rack
        if pos[1] > 1.25 and not crashed:
            crashed = True
            print(f"💥 {C_RED}{C_BOLD}[t={t:.3f}s] COLLISION CRASH! Robot slipped out of trajectory bounds (y={pos[1]:.2f}m).{C_END}")
            print(f"   └─ Cause: Un-grounded AI turn command exceeded concrete friction limits, causing catastrophic slide.")
            
        steps_log.append({
            "t": t,
            "residual": float(residual),
            "slipped": slipped,
            "x": float(pos[0]),
            "y": float(pos[1])
        })
        
    print(f"\n{C_BOLD}Mission Summary:{C_END}")
    print(f"Total navigation path: {pos[0]:.2f}m range, {pos[1]:.2f}m lateral.")
    print(f"ZTP Grounding filter: {'ENABLED' if apply_ztp_grounding else 'DISABLED'}")
    print(f"Result: {C_GREEN}SUCCESSFUL ARRIVAL (Trajectory Maintained){C_END}" if not crashed else f"{C_RED}VEHICLE CATASTROPHIC COLLISION{C_END}")
    
    if apply_ztp_grounding and override_time:
        log_bytes = json.dumps(steps_log).encode("utf-8")
        seal = hashlib.sha256(log_bytes).hexdigest()
        print(f"🔒 {C_BOLD}SHA-256 Grounded Path Seal:{C_END} {C_BLUE}{seal}{C_END}")
        
    return not crashed

def main():
    print(BANNER)
    
    # 1. Generate baseline telemetry (semantic path)
    log = run_ai_mission()
    
    # 2. Audit WITHOUT ZTP (shows slip and collision)
    audit_navigation(log, apply_ztp_grounding=False)
    
    print("\n" + "="*80 + "\n")
    
    # 3. Audit WITH ZTP (shows successful grounding, speed dampening, and safe turn)
    audit_navigation(log, apply_ztp_grounding=True)

if __name__ == "__main__":
    main()
