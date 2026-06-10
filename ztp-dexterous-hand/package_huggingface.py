#!/usr/bin/env python3
"""
ZTP Haptic Dataset Packager: Converts haptic telemetry JSON to flattened Parquet
optimized for Hugging Face Datasets and VLA model pretraining.
"""

import os
import json
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(script_dir, "../Aegis OS/manifests/grasp_telemetry.json")
    
    if not os.path.exists(json_path):
        print(f"❌ Source haptic dataset not found at {json_path}")
        return

    print(f"🔄 Loading raw haptic dataset: {json_path}...")
    with open(json_path, 'r') as f:
        data = json.load(f)

    trajectories = data.get("trajectories", {})
    rows = []

    print("⚡ Flattening 1000Hz trajectories into tabular structure...")
    for scenario, steps in trajectories.items():
        print(f"  • Processing scenario '{scenario}' ({len(steps)} control cycles)...")
        for step in steps:
            t = step["t"]
            state = step["state"]
            sensor = step["sensor"]
            reflex = step["reflex"]

            # Base features
            row = {
                "timestamp_sec": float(t),
                "scenario": scenario,
                "mass_kg": float(state["mass"]),
                "actual_normal_force_n": float(state["actual_normal_force"]),
                "slip_velocity_mps": float(state["slip_velocity"]),
                "slip_angular_velocity_radps": float(state["slip_angular_velocity"]),
                "slip_displacement_mm": float(state["slip_displacement_mm"]),
                "rot_slip_displacement_deg": float(state["rot_slip_displacement_deg"]),
                "static_friction_coeff": float(state["static_friction_coeff"]),
                "dynamic_friction_coeff": float(state["dynamic_friction_coeff"]),
                
                # Actions / Targets
                "action_commanded_force_n": float(reflex["commanded_force"]),
                "estimated_mu": float(reflex["estimated_mu"]),
                "safety_margin": float(reflex["margin"]),
                "micro_slip_detected": bool(reflex["micro_slip_detected"]),
                "macro_slip_detected": bool(reflex["macro_slip_detected"]),
                "rotational_slip_detected": bool(reflex["rotational_slip_detected"]),
            }

            # Map 4x4 taxels (16 sensors) to individual columns
            for idx in range(16):
                row[f"taxel_{idx}_normal_n"] = float(sensor["normal"][idx])
                row[f"taxel_{idx}_shear_x_n"] = float(sensor["shear_x"][idx])
                row[f"taxel_{idx}_shear_y_n"] = float(sensor["shear_y"][idx])

            rows.append(row)

    df = pd.DataFrame(rows)
    print(f"✨ Created DataFrame with {df.shape[0]} rows and {df.shape[1]} columns.")

    # Export paths
    parquet_filename = "haptic_trajectories.parquet"
    out_dir_local = os.path.join(script_dir)
    out_dir_aegis = os.path.join(script_dir, "../Aegis OS/manifests")

    local_path = os.path.join(out_dir_local, parquet_filename)
    aegis_path = os.path.join(out_dir_aegis, parquet_filename)

    # Convert to PyArrow Table with metadata for Hugging Face
    table = pa.Table.from_pandas(df)
    
    # Write Parquet files
    print(f"💾 Saving Parquet files...")
    pq.write_table(table, local_path, compression='snappy')
    pq.write_table(table, aegis_path, compression='snappy')

    local_size_mb = os.path.getsize(local_path) / (1024 * 1024)
    print(f"✅ Export successful:")
    print(f"   • Local: {local_path} ({local_size_mb:.2f} MB)")
    print(f"   • Aegis OS Archive: {aegis_path}")
    print("\nDataset Schema:")
    print("-" * 50)
    print(df.info())

if __name__ == "__main__":
    main()
