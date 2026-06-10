#!/usr/bin/env python3
"""
ZTP Haptic Dataset Generator: Generates a large-scale, domain-randomized haptic trajectory
dataset by running thousands of monte-carlo simulations calling the FFI Rust solver.
"""

import os
import sys
import ctypes
import json
import time
import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

# Load native runtime structures
try:
    from dexterous_grasp import (
        C_Taxel, C_TactileArray, C_GraspState, C_GraspResult,
        load_ztp_library, distribute_tactile_forces
    )
    _lib = load_ztp_library()
    _lib.ztp_dexterous_evaluate_grasp.argtypes = [
        ctypes.POINTER(C_TactileArray),
        ctypes.POINTER(C_GraspState),
        ctypes.c_float
    ]
    _lib.ztp_dexterous_evaluate_grasp.restype = C_GraspResult
    HAS_ZTP_LIB = True
except Exception as e:
    print(f"❌ Failed to load ZTP library: {e}")
    HAS_ZTP_LIB = False

def run_single_episode(episode_id, mass, mu_s, initial_force, a_max, friction_drop_t, friction_drop_factor, torque_t, torque_max):
    # Initialize structures
    state = C_GraspState()
    state.normal_force = initial_force
    state.slip_velocity = 0.0
    state.slip_angular_velocity = 0.0
    state.object_mass = mass
    state.static_friction_coeff = mu_s
    state.dynamic_friction_coeff = mu_s * 0.8
    state.reflex_active = False

    sensor = C_TactileArray()

    # Kinematics
    y_h, v_h, y_o, v_o = 0.0, 0.0, 0.0, 0.0
    theta_h, omega_h, theta_o, omega_o = 0.0, 0.0, 0.0, 0.0
    I_moment = 0.015
    R_eff = 0.025

    dt = 0.001
    gravity = 9.81
    tau_actuator = 0.0015
    actual_force = initial_force

    episode_rows = []
    dropped = False

    # Run for 1.2 seconds (1200 steps)
    for step in range(1200):
        t = step * dt

        # Acceleration ramp
        if t >= 0.2:
            a_h = a_max * min((t - 0.2) / 0.05, 1.0)
        else:
            a_h = 0.0

        # Friction drop (oil patch)
        if friction_drop_t and t >= friction_drop_t:
            drop_factor = 1.0 - (1.0 - friction_drop_factor) * min((t - friction_drop_t) / 0.05, 1.0)
            current_mu_s = mu_s * drop_factor
        else:
            current_mu_s = mu_s

        # Torque load
        if torque_t and t >= torque_t:
            torque_load = torque_max * min((t - torque_t) / 0.05, 1.0)
        else:
            torque_load = 0.0

        state.static_friction_coeff = current_mu_s
        state.dynamic_friction_coeff = current_mu_s * 0.8
        
        total_load = mass * (gravity + a_h)
        friction_limit = 2.0 * actual_force * state.static_friction_coeff
        torque_limit = friction_limit * R_eff

        v_slip = v_h - v_o
        state.slip_velocity = v_slip
        
        omega_slip = omega_h - omega_o
        state.slip_angular_velocity = omega_slip

        is_sliding = (abs(v_slip) > 0.001) or (total_load > friction_limit)
        is_rotating = (abs(omega_slip) > 0.005) or (torque_load > torque_limit)

        if is_sliding:
            shear_force = 2.0 * actual_force * state.dynamic_friction_coeff
            a_o = (shear_force / mass) - gravity
        else:
            shear_force = total_load
            a_o = a_h
            v_o = v_h

        if is_rotating:
            torque_shear = torque_limit * 0.8
            a_rot_o = (torque_load - torque_shear) / I_moment
        else:
            torque_shear = torque_load
            a_rot_o = 0.0
            omega_o = omega_h

        distribute_tactile_forces(actual_force, shear_force, torque_shear, sensor)
        state.normal_force = actual_force

        # Call Rust Solver
        res = _lib.ztp_dexterous_evaluate_grasp(ctypes.byref(sensor), ctypes.byref(state), dt)

        # Update actuator
        dF = (res.commanded_force - actual_force) / tau_actuator
        actual_force += dF * dt

        # Integrate kinematics
        v_h += a_h * dt
        y_h += v_h * dt
        v_o += a_o * dt
        y_o += v_o * dt

        omega_o += a_rot_o * dt
        theta_o += omega_o * dt

        slip_dist = abs(y_h - y_o)
        rot_slip_deg = abs(theta_h - theta_o) * 180.0 / 3.14159265

        # Save cycle step
        row = {
            "episode_id": episode_id,
            "timestamp_sec": float(t),
            "mass_kg": float(mass),
            "true_static_mu": float(current_mu_s),
            "actual_normal_force_n": float(actual_force),
            "slip_velocity_mps": float(v_slip),
            "slip_angular_velocity_radps": float(omega_slip),
            "slip_displacement_mm": float(slip_dist * 1000.0),
            "rot_slip_displacement_deg": float(rot_slip_deg),
            "action_commanded_force_n": float(res.commanded_force),
            "estimated_mu": float(res.estimated_mu),
            "safety_margin": float(res.margin),
            "micro_slip_detected": bool(res.micro_slip_detected),
            "macro_slip_detected": bool(res.macro_slip_detected),
            "rotational_slip_detected": bool(res.rotational_slip_detected),
        }
        
        # Pack 4x4 taxels
        for idx in range(16):
            row[f"taxel_{idx}_normal_n"] = float(sensor.taxels[idx].normal)
            row[f"taxel_{idx}_shear_x_n"] = float(sensor.taxels[idx].shear_x)
            row[f"taxel_{idx}_shear_y_n"] = float(sensor.taxels[idx].shear_y)

        episode_rows.append(row)

        # Drop criteria
        if slip_dist >= 0.10 or rot_slip_deg >= 60.0:
            dropped = True
            break

    return episode_rows, dropped

def generate_large_scale_dataset(num_episodes=500):
    if not HAS_ZTP_LIB:
        print("❌ Cannot generate dataset without native Rust FFI library compiled.")
        return

    np.random.seed(42)
    print(f"\n🚀 STARTING LARGE-SCALE MONTE-CARLO HAPTIC GENERATOR ({num_episodes} EPISODES)...")
    
    all_data = []
    success_count = 0
    drop_count = 0
    
    start_time = time.time()

    for ep in range(num_episodes):
        # Domain Randomization
        mass = np.random.uniform(0.15, 2.2)  # Mass from 150g to 2.2kg
        mu_s = np.random.uniform(0.15, 0.75) # Surface friction from slick plastic to rubber
        
        # Calculate nominal load and initial force (randomized safety factor)
        nominal_load = mass * 9.81
        min_required_force = nominal_load / (2.0 * mu_s)
        
        # 15% of the time, start UNDER-grasped to trigger initial slips
        if np.random.rand() < 0.15:
            initial_force = min_required_force * np.random.uniform(0.6, 0.95)
        else:
            initial_force = min_required_force * np.random.uniform(1.05, 1.7)
            
        a_max = np.random.uniform(1.5, 14.0)  # Sudden upward acceleration
        
        # Sudden environment disturbance (oil patch) in 35% of episodes
        if np.random.rand() < 0.35:
            friction_drop_t = np.random.uniform(0.4, 0.6)
            friction_drop_factor = np.random.uniform(0.3, 0.7)
        else:
            friction_drop_t = None
            friction_drop_factor = 1.0
            
        # External torque disturbance in 50% of episodes
        if np.random.rand() < 0.50:
            torque_t = np.random.uniform(0.6, 0.8)
            torque_max = np.random.uniform(0.02, 0.22)
        else:
            torque_t = None
            torque_max = 0.0

        rows, dropped = run_single_episode(
            episode_id=ep,
            mass=mass,
            mu_s=mu_s,
            initial_force=initial_force,
            a_max=a_max,
            friction_drop_t=friction_drop_t,
            friction_drop_factor=friction_drop_factor,
            torque_t=torque_t,
            torque_max=torque_max
        )
        
        all_data.extend(rows)
        if dropped:
            drop_count += 1
        else:
            success_count += 1
            
        if (ep + 1) % 50 == 0:
            elapsed = time.time() - start_time
            print(f"  Processed {ep + 1}/{num_episodes} episodes | Success: {success_count} | Dropped: {drop_count} | Elapsed: {elapsed:.2f}s")

    elapsed_total = time.time() - start_time
    print(f"\n✨ Generation completed in {elapsed_total:.2f}s.")
    print(f"   • Secured Grasps: {success_count} ({success_count/num_episodes*100:.1f}%)")
    print(f"   • Dropped Objects: {drop_count} ({drop_count/num_episodes*100:.1f}%)")
    
    df = pd.DataFrame(all_data)
    print(f"📊 Total timesteps generated: {df.shape[0]}")
    
    # Save Parquet
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parquet_path = os.path.join(script_dir, "haptic_trajectories.parquet")
    aegis_path = os.path.join(script_dir, "../Aegis OS/manifests/haptic_trajectories.parquet")
    
    table = pa.Table.from_pandas(df)
    pq.write_table(table, parquet_path, compression='snappy')
    pq.write_table(table, aegis_path, compression='snappy')
    
    size_mb = os.path.getsize(parquet_path) / (1024 * 1024)
    print(f"💾 Parquet written to {parquet_path} ({size_mb:.2f} MB)")
    print(f"💾 Parquet written to {aegis_path}")

    # Write metadata info to JSON
    meta_path = os.path.join(script_dir, "dataset_metadata.json")
    metadata = {
        "dataset_name": "ztp-tactile-slip-reflex-large-v1",
        "num_episodes": num_episodes,
        "total_timesteps": df.shape[0],
        "secured_grasps": success_count,
        "dropped_objects": drop_count,
        "size_bytes": os.path.getsize(parquet_path),
        "columns": list(df.columns),
        "domain_randomization": {
            "mass_kg": [0.15, 2.2],
            "static_mu": [0.15, 0.75],
            "accel_max_mps2": [1.5, 14.0],
            "friction_drop_ratio": [0.3, 0.7],
            "disturbance_torque_nm": [0.02, 0.22]
        }
    }
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"📝 Metadata saved to {meta_path}")

if __name__ == "__main__":
    num_episodes = 500
    if len(sys.argv) > 1:
        num_episodes = int(sys.argv[1])
    generate_large_scale_dataset(num_episodes)
