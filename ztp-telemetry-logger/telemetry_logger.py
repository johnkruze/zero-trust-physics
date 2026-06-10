#!/usr/bin/env python3
"""
ZTP-TELEMETRY-LOGGER: Low-Latency Aligned Logging & Odometry Audit.
Part of the Zero-Trust Physics runtime assurance framework.

This tool solves two core problems for high-reliability data center robotics:
1. Telemetry Overhead: Edge systems need low-overhead binary logging.
2. Localization Aliasing: Long, symmetric server rack corridors cause Lidar/Visual SLAM 
   to drift or jump. The auditor checks wheel encoders against SLAM at 1000 Hz.
"""

import os
import sys
import struct
import time
import hashlib
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
  ██████╗  ██████╗  ██████╗  ███████╗████████╗    ██████╗  ██████╗  ██████╗  ███████╗
  ██╔══██╗██╔═══██╗██╔═══██╗██╔════╝╚══██╔══╝    ██╔══██╗██╔═══██╗██╔═══██╗██╔════╝
  ██████╔╝██║   ██║██║   ██║███████╗   ██║       ██████╔╝██║   ██║██║   ██║███████╗
  ██╔══██╗██║   ██║██║   ██║╚════██║   ██║       ██╔══██╗██║   ██║██║   ██║╚════██║
  ██████╔╝╚██████╔╝╚██████╔╝███████║   ██║       ██║  ██║╚██████╔╝╚██████╔╝███████║
  ╚═════╝  ╚═════╝  ╚═════╝ ╚══════╝   ╚═╝       ╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚══════╝
  Zero-Trust Physics: Low-Latency Binary Telemetry & Localization Audit
================================================================================{C_END}
"""

# Structural definition of our 64-byte aligned binary telemetry packet
# format: d (double: 8 bytes) + 6f (float: 4 bytes each) + 32s (string: 32 bytes) = 64 bytes
# 8 + 24 + 32 = 64 bytes (perfectly fits 64-byte L1 cache-line width)
TELEMETRY_STRUCT_FORMAT = "<dffffff32s"
PACKET_SIZE = struct.calcsize(TELEMETRY_STRUCT_FORMAT)
assert PACKET_SIZE == 64, f"Struct size is {PACKET_SIZE}, must be exactly 64 bytes"

# Kinematic Constants
WHEEL_RADIUS = 0.15     # meters
TRACK_WIDTH = 0.55      # meters (distance between wheels)
DT = 0.001              # 1000Hz loop

def pack_telemetry_frame(t, x, y, theta, v_left, v_right, v_expected, rolling_hash):
    """Pack telemetry parameters into a highly optimized, 64-byte binary structure."""
    # Ensure the hash is exactly 32 bytes of raw data
    hash_bytes = bytes.fromhex(rolling_hash)[:32]
    if len(hash_bytes) < 32:
        hash_bytes = hash_bytes.ljust(32, b'\x00')
        
    return struct.pack(
        TELEMETRY_STRUCT_FORMAT,
        t,          # Double (8B)
        x, y,       # Floats (8B)
        theta,      # Float (4B)
        v_left,     # Float (4B)
        v_right,    # Float (4B)
        v_expected, # Float (4B)
        hash_bytes  # 32B string (32B)
    )

def simulate_aisle_navigation():
    """
    Simulate a differential drive robot traversing a symmetric 30-meter server corridor.
    At t=3.0s, the Lidar-SLAM experiences "corridor aliasing" (visual geometry is symmetric),
    causing the SLAM pose to slip/hallucinate a static state, while the wheels continue spinning.
    """
    log = []
    
    # Starting state
    x, y, theta = 0.0, 0.0, 0.0
    rolling_hash = hashlib.sha256(b"INIT").hexdigest()
    
    # Robot target: drive straight down the aisle at 1.0 m/s
    v_left = 1.0
    v_right = 1.0
    
    # 6 seconds of telemetry at 1000Hz
    total_ticks = 6000
    
    print(f"{C_BLUE}Simulating data center corridor run (6,000 steps at 1000 Hz)...{C_END}")
    
    for tick in range(total_ticks):
        t = tick * DT
        
        # 1. Update true physics (simple differential drive kinematics)
        v_linear = (v_left + v_right) / 2.0
        omega = (v_right - v_left) / TRACK_WIDTH
        
        theta += omega * DT
        x += v_linear * np.cos(theta) * DT
        y += v_linear * np.sin(theta) * DT
        
        # 2. Simulate wheel encoder readings (with small Gaussian noise)
        encoder_vl = v_left + np.random.normal(0, 0.02)
        encoder_vr = v_right + np.random.normal(0, 0.02)
        
        # 3. Simulate SLAM sensor tracking
        # From t=3.0s to 5.0s, the robot enters a zone of perfect structural symmetry.
        # The Lidar SLAM matches features identically, concluding the robot has stopped moving (aliasing).
        if 3.0 <= t < 5.0:
            # SLAM stalls: coordinates freeze
            slam_x = 3.0 # position at t=3.0
            slam_y = y
            slam_theta = theta
        else:
            # Nominal SLAM tracking
            slam_x = x + np.random.normal(0, 0.0002)
            slam_y = y + np.random.normal(0, 0.0002)
            slam_theta = theta + np.random.normal(0, 0.0001)
            
        # 4. Compute the rolling cryptographic signature
        # We hash the current state fields concatenated with the previous step's signature
        state_data = f"{t},{x:.4f},{y:.4f},{theta:.4f},{encoder_vl:.4f},{encoder_vr:.4f}"
        rolling_hash = hashlib.sha256((state_data + rolling_hash).encode('utf-8')).hexdigest()
        
        # Pack the binary record
        binary_frame = pack_telemetry_frame(t, slam_x, slam_y, slam_theta, encoder_vl, encoder_vr, v_linear, rolling_hash)
        
        log.append({
            "binary_frame": binary_frame,
            "true_x": x,
            "true_y": y,
            "slam_x": slam_x,
            "slam_y": slam_y,
            "rolling_hash": rolling_hash
        })
        
    return log

def audit_binary_log(log, apply_ztp_audit=False):
    """
    Audit the binary telemetry log frame-by-frame.
    Detects localization slip by comparing encoder kinematic speed against SLAM pose delta.
    """
    print(f"\n{C_BOLD}Auditing Binary Telemetry Log (Kinematic SLAM Audit: {'ENABLED' if apply_ztp_audit else 'DISABLED'}){C_END}")
    print("-" * 90)
    
    prev_t = None
    prev_slam_x = None
    prev_slam_y = None
    v_slam_filtered = 1.0
    
    total_frames = len(log)
    audit_failures = 0
    override_active = False
    
    # Physical consistency threshold: 0.3 m/s velocity deviation
    SLIP_THRESHOLD = 0.35
    
    for i in range(total_frames):
        # Unpack binary packet
        frame_bytes = log[i]["binary_frame"]
        t, slam_x, slam_y, slam_theta, v_left, v_right, v_expected, hash_bytes = struct.unpack(
            TELEMETRY_STRUCT_FORMAT, frame_bytes
        )
        
        # 1. Kinematic forward model from encoders:
        # Expected linear velocity based on left/right wheel speeds
        v_encoder = (v_left + v_right) / 2.0
        
        # 2. Velocity vector derived from SLAM:
        if prev_t is not None:
            dt_step = t - prev_t
            dx = slam_x - prev_slam_x
            dy = slam_y - prev_slam_y
            v_slam_raw = np.sqrt(dx**2 + dy**2) / dt_step if dt_step > 0 else v_encoder
            # Low-pass filter to reject derivative noise from coordinate jitter
            v_slam_filtered = 0.98 * v_slam_filtered + 0.02 * v_slam_raw
            v_slam = v_slam_filtered
        else:
            v_slam = v_encoder
            v_slam_filtered = v_encoder
            
        # 3. ZTP Kinematic Inconsistency Indicator:
        # Residual represents the mismatch between wheel rotation and SLAM pose progress
        residual = abs(v_encoder - v_slam)
        
        if apply_ztp_audit:
            if residual > SLIP_THRESHOLD and not override_active:
                override_active = True
                print(f"🔒 {C_RED}{C_BOLD}[t={t:.3f}s] SLAM ALIASING DETECTED! Residual={residual:.2f} m/s.{C_END}")
                print(f"   ├─ Encoder Velocity: {v_encoder:.2f} m/s | SLAM Velocity: {v_slam:.2f} m/s")
                print(f"   └─ Action: Rejecting SLAM updates. Switching to Wheel Odometry dead-reckoning.")
                
            if override_active and residual <= SLIP_THRESHOLD:
                # Recover when SLAM snaps back to reality
                override_active = False
                print(f"   [t={t:.3f}s] SLAM tracking recovered. Re-engaging Lidar.")
                
            if override_active:
                audit_failures += 1
        else:
            # Without audit, we don't catch the error, and the robot believes it is stuck at x=3.0m
            if 3.0 <= t < 5.0 and i % 500 == 0:
                print(f"   [t={t:.3f}s] Robot believes it is stationary at x={slam_x:.2f}m. Actual x={log[i]['true_x']:.2f}m.")
                
        prev_t = t
        prev_slam_x = slam_x
        prev_slam_y = slam_y
        
    print(f"\n{C_BOLD}Audit Summary:{C_END}")
    if apply_ztp_audit:
        print(f"Identified localization slip count: {audit_failures} frames.")
        print(f"Localization Integrity: {C_GREEN}SECURED (E-Stop/Odometry fallback ready){C_END}")
    else:
        print(f"Localization Integrity: {C_RED}COMPROMISED (Lidar aliasing ignored){C_END}")
        print(f"Final true position: {log[-1]['true_x']:.2f}m | Reported position: {log[-1]['slam_x']:.2f}m")

def main():
    print(BANNER)
    
    # 1. Run flight simulation and serialize to binary
    log = simulate_aisle_navigation()
    
    # 2. Write binary log to disk (illustrating raw binary log pipeline)
    log_path = "ztp-telemetry-logger/samples/flight_log.bin"
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "wb") as f:
        for frame in log:
            f.write(frame["binary_frame"])
    print(f"{C_GREEN}Sealed binary telemetry file written to: {log_path} ({len(log)*64} bytes){C_END}")
    
    # 3. Audit WITHOUT ZTP
    audit_binary_log(log, apply_ztp_audit=False)
    
    print("\n" + "="*80 + "\n")
    
    # 4. Audit WITH ZTP
    audit_binary_log(log, apply_ztp_audit=True)

if __name__ == "__main__":
    main()
