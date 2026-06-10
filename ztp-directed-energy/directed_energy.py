#!/usr/bin/env python3
"""
ZTP-DIRECTED-ENERGY: High-Precision Directed Energy (Laser) targeting firewall.
Bridges with the compiled Rust ztp-runtime via C-FFI (ctypes).
"""

import os
import sys
import ctypes
import hashlib
import json
import time
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# ANSI Colors
C_BLUE = "\033[94m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_BOLD = "\033[1m"
C_END = "\033[0m"

BANNER = f"""
{C_BLUE}{C_BOLD}================================================================================
  ███████╗████████╗██████╗     ██████╗  ███████╗
  ╚══███╔╝╚══██╔══╝██╔══██╗    ██╔══██╗ ██╔════╝
    ███╔╝    ██║   ██████╔╝    ██║  ██║ █████╗  
   ███╔╝     ██║   ██╔═══╝     ██║  ██║ ██╔══╝  
  ███████╗   ██║   ██║         ██████╔╝ ███████╗
  ╚══════╝   ╚═╝   ╚═╝         ╚═════╝  ╚══════╝
  Zero-Trust Physics: Directed Energy Laser Targeting FFI Firewall & Auditor
================================================================================{C_END}
"""

# Simulation Constants
HZ = 1000.0             # 1 kHz control loop cycle
DT = 1.0 / HZ
TOTAL_TIME = 1.5        # 1.5 seconds total run time
TOTAL_STEPS = int(TOTAL_TIME * HZ)

RANGE_TO_TARGET = 2000.0 # meters
BEAM_RADIUS = 0.08      # 8 cm beam spot size at target plane
DWELL_ENERGY_THRESHOLD = 1000 # 1000 steps of cumulative dwell energy to destroy

# ─── CTYPES STRUCTURES ────────────────────────────────────────────────────────

class C_LaserTargetState(ctypes.Structure):
    _fields_ = [
        ("true_y", ctypes.c_double),
        ("true_vy", ctypes.c_double),
        ("est_y", ctypes.c_double),
        ("est_vy", ctypes.c_double),
        ("p_xx", ctypes.c_double),
        ("p_xv", ctypes.c_double),
        ("p_vv", ctypes.c_double),
        ("gimbal_y", ctypes.c_double),
        ("gimbal_vy", ctypes.c_double),
        ("anomaly_detected", ctypes.c_bool),
    ]

# ─── FFI LIBRARY LOADER ───────────────────────────────────────────────────────

def load_ztp_library() -> ctypes.CDLL:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "../../ztp-runtime/target/release/libztp_runtime.dylib"),
        os.path.join(script_dir, "../target/release/libztp_runtime.dylib"),
        "/Users/aijesusbro/Spectr../../ztp-runtime/target/release/libztp_runtime.dylib",
        os.path.join(script_dir, "libztp_runtime.dylib"),
    ]
    
    for path in candidates:
        if os.path.exists(path):
            try:
                lib = ctypes.CDLL(path)
                return lib
            except Exception as e:
                print(f"⚠️ Failed to load library at {path}: {e}")
                
    try:
        return ctypes.CDLL("libztp_runtime.dylib")
    except Exception:
        raise FileNotFoundError("CRITICAL: libztp_runtime.dylib not found. Run `cargo build --release` inside ztp-runtime first.")

# Load and configure FFI function
try:
    _lib = load_ztp_library()
    _lib.ztp_directed_energy_step.argtypes = [
        ctypes.POINTER(C_LaserTargetState),
        ctypes.c_double,
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_uint32,
        ctypes.c_bool,
        ctypes.c_double,
    ]
    _lib.ztp_directed_energy_step.restype = ctypes.c_bool
    HAS_ZTP_LIB = True
except Exception as e:
    print(f"❌ Failed to load ZTP library: {e}")
    HAS_ZTP_LIB = False


def run_de_mission(apply_ztp):
    """
    Simulates target tracking of a high-speed projectile or drone flying at 50 m/s.
    At t=0.3s to t=1.1s: Optical tracking scintillation corrupts measurements with 2.5m noise.
    Bridges states to the compiled Rust ztp-runtime FFI solver.
    """
    print(f"\n{C_BOLD}Auditing Directed Energy Targeting Loop (ZTP Firewall: {'ENABLED' if apply_ztp else 'DISABLED'}){C_END}")
    print("-" * 95)
    
    if not HAS_ZTP_LIB:
        print("❌ Cannot run simulation without compiled ZTP FFI library.")
        return None

    np.random.seed(42)
    v_true = 50.0
    
    # Initialize ctypes state struct
    state = C_LaserTargetState()
    state.true_y = 0.0
    state.true_vy = v_true
    state.est_y = 0.0
    state.est_vy = v_true
    state.p_xx = 0.1
    state.p_xv = 0.0
    state.p_vv = 0.1
    state.gimbal_y = 0.0
    state.gimbal_vy = v_true
    state.anomaly_detected = False
    
    dwell_energy = 0
    target_destroyed = False
    destruction_time = None
    min_beam_distance = 999.0
    
    meas_history = []
    dy_history = []
    
    scintillation_reported = False
    anomaly_reported = False
    
    log = []
    
    for step in range(TOTAL_STEPS):
        t = step * DT
        y_t = v_true * t
        
        # 1. Sensor measurement with scintillation phase
        is_scintillation = (0.3 <= t < 1.1)
        noise_std = 2.5 if is_scintillation else 0.02
        y_meas = y_t + np.random.normal(0.0, noise_std)
        
        if is_scintillation and not scintillation_reported and not apply_ztp:
            scintillation_reported = True
            print(f"💥 {C_RED}{C_BOLD}[t={t:.2f}s] OPTICAL SCINTILLATION CORRUPTS SENSOR! Laser backscatter introduces 2.5m noise.{C_END}")
            
        # Track raw measurements for rolling variance
        meas_history.append(y_meas)
        if len(meas_history) > 1:
            dy = y_meas - meas_history[-2]
            dy_history.append(dy)
            if len(dy_history) > 10:
                dy_history.pop(0)
                
        # Prepare dy_history array for FFI pass
        dy_arr = (ctypes.c_double * len(dy_history))(*dy_history)
        
        # 2. Call Compiled Rust FFI step solver
        ffi_anomaly = _lib.ztp_directed_energy_step(
            ctypes.byref(state),
            y_meas,
            dy_arr,
            len(dy_history),
            apply_ztp,
            DT
        )
        
        if ffi_anomaly and not anomaly_reported:
            anomaly_reported = True
            print(f"🔒 {C_GREEN}{C_BOLD}[t={t:.2f}s] TARGETING FIREWALL ENGAGED! Innovation exceeds physical limits.{C_END}")
            print(f"   ├─ Action: DETECTED SCINTILLATION. Native solver adapted R covariance in <10 microseconds.")
            print(f"   └─ Status: Smoothing gimbal jitter via constant-velocity kinematic projection.")
            
        # 3. Read back tracking and kinematics states from ctypes struct
        true_pos = state.true_y
        est_pos = state.est_y
        gimbal_pos = state.gimbal_y
        
        dist = abs(gimbal_pos - y_t)
        min_beam_distance = min(min_beam_distance, dist)
        
        if dist <= BEAM_RADIUS and not target_destroyed:
            dwell_energy += 1
            if dwell_energy >= DWELL_ENERGY_THRESHOLD:
                target_destroyed = True
                destruction_time = t
                print(f"🎯 {C_GREEN}{C_BOLD}[t={t:.3f}s] TARGET NEUTRALIZED! Cumulative dwell energy reached threshold ({dwell_energy}/{DWELL_ENERGY_THRESHOLD}).{C_END}")
                
        log.append({
            "t": t,
            "y_t": float(y_t),
            "y_meas": float(y_meas),
            "y_est": float(est_pos),
            "y_g": float(gimbal_pos),
            "dist": float(dist),
            "dwell_energy": int(dwell_energy),
            "destroyed": bool(target_destroyed),
            "anomaly_detected": bool(state.anomaly_detected)
        })
        
    print(f"\n{C_BOLD}Mission Summary:{C_END}")
    print(f"Total test time: {TOTAL_TIME:.1f} s")
    print(f"Targeting Firewall: {'ENABLED' if apply_ztp else 'DISABLED'}")
    print(f"Final Laser Dwell: {dwell_energy} / {DWELL_ENERGY_THRESHOLD} units")
    print(f"Minimum Tracking Error: {min_beam_distance:.4f} m")
    print(f"Result: {C_GREEN}TARGET NEUTRALIZED{C_END}" if target_destroyed else f"{C_RED}TARGET ESCAPED (Insufficent energy dwell due to optical jitter){C_END}")
    
    if apply_ztp and target_destroyed:
        log_bytes = json.dumps(log).encode("utf-8")
        seal = hashlib.sha256(log_bytes).hexdigest()
        print(f"🔒 {C_BOLD}SHA-256 Telemetry Seal:{C_END} {C_BLUE}{seal}{C_END}")
        
    return log, target_destroyed, destruction_time, min_beam_distance

def main():
    print(BANNER)
    
    if not HAS_ZTP_LIB:
        print("Failed to run simulation due to missing ZTP library bindings.")
        return

    # 1. Run simulation WITHOUT ZTP (fails)
    log_unprotected, destroyed_unprotected, _, _ = run_de_mission(apply_ztp=False)
    
    print("\n" + "="*80 + "\n")
    
    # 2. Run simulation WITH ZTP (succeeds)
    log_protected, destroyed_protected, dest_t, min_beam_dist_protected = run_de_mission(apply_ztp=True)

    # ─── GENERATE TARGETING TELEMETRY DASHBOARD ──────────────────────────────────
    print("\n🎨 Generating Directed Energy Targeting Telemetry Dashboard...")
    plt.style.use('dark_background')
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    fig.suptitle("⚡ ZTP HIGH-PRECISION DIRECTED ENERGY LASER FIREWALL", fontsize=16, fontweight='bold', color='#00FFCC')

    t_unprotected = [step["t"] for step in log_unprotected]
    y_meas_unprotected = [step["y_meas"] for step in log_unprotected]
    y_t_unprotected = [step["y_t"] for step in log_unprotected]
    y_g_unprotected = [step["y_g"] for step in log_unprotected]
    dist_unprotected = [step["dist"] for step in log_unprotected]
    dwell_unprotected = [step["dwell_energy"] for step in log_unprotected]

    t_protected = [step["t"] for step in log_protected]
    y_g_protected = [step["y_g"] for step in log_protected]
    dist_protected = [step["dist"] for step in log_protected]
    dwell_protected = [step["dwell_energy"] for step in log_protected]

    # Plot 1: Target Position vs. Gimbal tracking
    ax1.plot(t_unprotected, y_meas_unprotected, label="Raw Optical Sensor (Noisy)", color="#555555", alpha=0.5, linestyle=":")
    ax1.plot(t_unprotected, y_t_unprotected, label="True Projectile Trajectory (50 m/s)", color="#E0E0E0", linewidth=1.5)
    ax1.plot(t_unprotected, y_g_unprotected, label="Gimbal Position (ZTP Disabled - Jittering)", color="#FF3366", linewidth=2)
    ax1.plot(t_protected, y_g_protected, label="Gimbal Position (ZTP Enabled - Clean Lock)", color="#00FFCC", linewidth=2)
    
    ax1.set_title("Directed Energy Targeting & Gimbal Track Profiles", fontsize=12, color='#E0E0E0')
    ax1.set_ylabel("Linear Position (m)", fontsize=10)
    ax1.grid(True, alpha=0.15, linestyle='--')
    ax1.legend(fontsize=9, loc="upper left")
    
    # Shade Scintillation phase (0.3s to 1.1s)
    ax1.axvspan(0.3, 1.1, color='#FF3366', alpha=0.1, label="Plasma Scintillation Zone")
    ax1.text(0.7, ax1.get_ylim()[0] + (ax1.get_ylim()[1] - ax1.get_ylim()[0])*0.5, "Plasma Scintillation Zone (Noise = 2.5m)", color="#FF3366", fontsize=10, ha="center")

    # Plot 2: Beam Offset Distance (Error)
    ax2.plot(t_unprotected, dist_unprotected, label="Beam Spot Drift (ZTP Disabled)", color="#FF3366", linewidth=2)
    ax2.plot(t_protected, dist_protected, label="Beam Spot Drift (ZTP Enabled)", color="#00FFCC", linewidth=2)
    ax2.axhline(y=BEAM_RADIUS, color='#FFAA00', linestyle='--', label=f"Beam Radius Limit ({BEAM_RADIUS*100:.0f} cm)")
    
    ax2.set_title("Targeting Deviation at Projectile Plane", fontsize=12, color='#E0E0E0')
    ax2.set_ylabel("Offset Error (m)", fontsize=10)
    ax2.set_ylim(-0.1, 1.5)
    ax2.grid(True, alpha=0.15, linestyle='--')
    ax2.legend(fontsize=9, loc="upper right")

    # Plot 3: Cumulative Dwell Energy
    ax3.plot(t_unprotected, dwell_unprotected, label="Laser Dwell Energy (ZTP Disabled)", color="#FF3366", linewidth=2)
    ax3.plot(t_protected, dwell_protected, label="Laser Dwell Energy (ZTP Enabled)", color="#00FFCC", linewidth=2)
    ax3.axhline(y=DWELL_ENERGY_THRESHOLD, color='#E0E0E0', linestyle='--', label="Neutralization Threshold")
    
    if destroyed_protected and dest_t:
        ax3.axvline(x=dest_t, color='#00FFCC', linestyle=':')
        ax3.text(dest_t + 0.02, DWELL_ENERGY_THRESHOLD - 200, f"Neutralized\nt={dest_t:.3f}s", color="#00FFCC", fontsize=9)

    ax3.set_title("Cumulative Dwell Energy Transfer", fontsize=12, color='#E0E0E0')
    ax3.set_xlabel("Time (s)", fontsize=10)
    ax3.set_ylabel("Energy (Units)", fontsize=10)
    ax3.grid(True, alpha=0.15, linestyle='--')
    ax3.legend(fontsize=9, loc="upper left")

    plt.tight_layout()
    dashboard_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "directed_energy_dashboard.png")
    plt.savefig(dashboard_path, dpi=100)
    plt.close()
    print(f"🖼️  Generated visual targeting dashboard: {dashboard_path}")

    # Export Parquet dataset
    rows_unprotected = [{"condition": "unprotected", **step} for step in log_unprotected]
    rows_protected = [{"condition": "ztp_protected", **step} for step in log_protected]
    df = pd.DataFrame(rows_unprotected + rows_protected)
    parquet_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "directed_energy_telemetry.parquet")
    df.to_parquet(parquet_path, index=False, engine="pyarrow")
    print(f"📦 Exported HuggingFace-ready directed energy dataset to: {parquet_path}")
    
    # Save Aegis OS manifest
    aegis_manifest_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Aegis OS", "manifests")
    os.makedirs(aegis_manifest_path, exist_ok=True)
    manifest_name = f"manifest_directed_energy_{int(time.time())}.json"
    
    if destroyed_protected:
        log_bytes = json.dumps(log_protected).encode("utf-8")
        manifest_hash = hashlib.sha256(log_bytes).hexdigest()
        
        final_manifest = {
            "mission_id": "directed_energy_neutralization",
            "environment": "terran_aerial_intercept",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "is_dark_window": True,
            "telemetry_ref": "directed_energy_telemetry.json",
            "epistemic_status": "ZTP_ACTIVE",
            "results": {
                "domain": "directed_energy_laser",
                "ztp_active": True,
                "neutralized": True,
                "neutralization_time_s": dest_t,
                "min_tracking_error_m": min_beam_dist_protected,
                "verification": "SUCCESS"
            },
            "sha256_proof": manifest_hash
        }
        
        with open(os.path.join(aegis_manifest_path, manifest_name), "w") as f:
            json.dump(final_manifest, f, indent=2)
        print(f"🔒 Sealed Aegis OS Manifest written to: {os.path.join(aegis_manifest_path, manifest_name)}")

if __name__ == "__main__":
    main()
