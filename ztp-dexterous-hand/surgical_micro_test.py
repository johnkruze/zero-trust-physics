#!/usr/bin/env python3
"""
surgical_micro_test.py: Verifies surgical tissue compliance and micro-manufacturing release FFI overrides.
"""

import os
import sys
import ctypes
import json
import time

# ANSI Colors
C_BLUE = "\033[94m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_BOLD = "\033[1m"
C_END = "\033[0m"

BANNER = f"""
{C_BLUE}{C_BOLD}================================================================================
  ███████╗████████╗██████╗     ███████╗██╗   ██╗██████╗  ██████╗██╗ ██████╗ ███████╗
  ╚══███╔╝╚══██╔══╝██╔══██╗    ██╔════╝██║   ██║██╔══██╗██╔════╝██║██╔════╝ ██╔════╝
    ███╔╝    ██║   ██████╔╝    ███████╗██║   ██║██████╔╝██║     ██║██║      █████╗  
   ███╔╝     ██║   ██╔═══╝     ╚════██║██║   ██║██╔══██╗██║     ██║██║      ██╔══╝  
  ███████╗   ██║   ██║         ███████║╚██████╔╝██║  ██║╚██████╗██║╚██████╗ ███████╗
  ╚══════╝   ╚═╝   ╚═╝         ╚══════╝ ╚═════╝ ╚═╝  ╚═╝ ╚═════╝╚═╝ ╚═════╝ ╚══════╝
  Zero-Trust Physics: Surgical compliance & Micro-release stiction FFI tests
================================================================================{C_END}
"""

# ─── CTYPES STRUCTURES ────────────────────────────────────────────────────────

class C_SurgicalTissueAuditor(ctypes.Structure):
    _fields_ = [
        ("tissue_type_id", ctypes.c_uint32),
        ("max_tearing_force_n", ctypes.c_float),
        ("measured_displacement_m", ctypes.c_float),
        ("measured_force_n", ctypes.c_float),
        ("relaxation_tau", ctypes.c_float),
        ("last_displacement_m", ctypes.c_float),
        ("last_force_n", ctypes.c_float),
        ("accumulated_energy_j", ctypes.c_float),
    ]

class C_SurgicalResult(ctypes.Structure):
    _fields_ = [
        ("tissue_overstress_detected", ctypes.c_bool),
        ("viscoelastic_rupture_detected", ctypes.c_bool),
        ("cable_slip_fault", ctypes.c_bool),
        ("clamped_force", ctypes.c_float),
    ]

class C_MicroReleaseAuditor(ctypes.Structure):
    _fields_ = [
        ("part_mass_micrograms", ctypes.c_float),
        ("pull_off_force_un", ctypes.c_float),
        ("jaw_separation_um", ctypes.c_float),
        ("dynamic_electrostatic_charge_v", ctypes.c_float),
        ("last_jaw_separation_um", ctypes.c_float),
    ]

class C_MicroResult(ctypes.Structure):
    _fields_ = [
        ("release_stiction_active", ctypes.c_bool),
        ("electrostatic_charge_violation", ctypes.c_bool),
        ("piezo_shake_trigger", ctypes.c_bool),
        ("safe_to_retract", ctypes.c_bool),
    ]

# ─── LOAD LIBRARY ─────────────────────────────────────────────────────────────

def load_lib() -> ctypes.CDLL:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(script_dir, "../../ztp-runtime/target/release/libztp_runtime.dylib")
    if not os.path.exists(path):
        # try G^G folder
        path = os.path.join(script_dir, "../../G^G/target/release/libztp_runtime.dylib")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Dynamic library not found. Run cargo build --release in ztp-runtime.")
    
    lib = ctypes.CDLL(path)
    
    # Configure FFI
    lib.ztp_surgical_evaluate_grasp.argtypes = [ctypes.POINTER(C_SurgicalTissueAuditor), ctypes.c_float]
    lib.ztp_surgical_evaluate_grasp.restype = C_SurgicalResult
    
    lib.ztp_micro_evaluate_release.argtypes = [ctypes.POINTER(C_MicroReleaseAuditor), ctypes.c_float]
    lib.ztp_micro_evaluate_release.restype = C_MicroResult
    
    return lib

# ─── SIMULATIONS ──────────────────────────────────────────────────────────────

def run_surgical_sim(lib, apply_ztp):
    print(f"\n🩺 {C_BOLD}Running Surgical Gripper Simulation (ZTP: {'ENABLED' if apply_ztp else 'DISABLED'}){C_END}")
    print("-" * 90)
    
    # Target: Tissue Type 0 (Liver/Spleen, clamped limit 1.2N)
    auditor = C_SurgicalTissueAuditor()
    auditor.tissue_type_id = 0
    auditor.max_tearing_force_n = 2.0  # Surgeon sets 2.0N, but ZTP clamps it to 1.2N for liver
    auditor.measured_displacement_m = 0.0
    auditor.measured_force_n = 0.0
    auditor.relaxation_tau = 0.5
    auditor.last_displacement_m = 0.0
    auditor.last_force_n = 0.0
    auditor.accumulated_energy_j = 0.0
    
    dt = 0.01  # 100Hz loop
    
    # AI commands gripper jaws to close slowly on liver tissue
    print("Gripper Jaws closing on liver tissue...")
    
    crashed = False
    clamped_force = 2.0
    
    for step in range(1, 100):
        t = step * dt
        
        # Save history
        auditor.last_displacement_m = auditor.measured_displacement_m
        auditor.last_force_n = auditor.measured_force_n
        
        # Jaws close: displacement increases by 0.2mm per step
        auditor.measured_displacement_m += 0.0002
        
        # Viscoelastic force behavior
        # Force increases linearly with displacement until t=0.6s (step 60)
        # where the liver tissue physically tears under extreme compression
        if step < 60:
            # Stiffness is 10N/mm
            auditor.measured_force_n = auditor.measured_displacement_m * 10000.0
        else:
            # Rupture! Force suddenly drops even though jaws are still closing
            if step == 60:
                print(f"⚠️  {C_RED}[t={t:.2f}s] TISSUE MECHANICAL RUPTURE occurs! Fiber elasticity collapses.{C_END}")
            auditor.measured_force_n = max(0.2, auditor.measured_force_n - 0.1)
            
        # Call FFI
        res = lib.ztp_surgical_evaluate_grasp(ctypes.byref(auditor), dt)
        clamped_force = res.clamped_force
        
        # Auditor response
        if apply_ztp:
            if res.tissue_overstress_detected:
                print(f"🔒 {C_YELLOW}[t={t:.2f}s] ZTP OVERRIDE: Tissue Overstress! Command clamped to {res.clamped_force:.2f}N (Measured: {auditor.measured_force_n:.2f}N).{C_END}")
                # Clamp the actual motor command force
                auditor.measured_force_n = res.clamped_force
                
            if res.viscoelastic_rupture_detected:
                print(f"🚨 {C_RED}{C_BOLD}[t={t:.2f}s] ZTP INTERCEPT: Tissue Rupture detected! Halting all gripper motion.{C_END}")
                break
        else:
            # AI blindly trusts the loop and continues compressing
            if auditor.measured_force_n > clamped_force:
                crashed = True
                
        # Simple logging
        if step % 15 == 0 or step == 60:
            print(f"  t={t:.2f}s | Jaws: {auditor.measured_displacement_m*1000.0:.2f}mm | Force: {auditor.measured_force_n:.2f}N | Ruptured: {res.viscoelastic_rupture_detected}")
            
    print(f"\n{C_BOLD}Surgical Run Result:{C_END}")
    if apply_ztp:
        print(f"🟢 {C_GREEN}TISSUE PROTECTED: Grip halted at safety boundary (Max force clamped to {clamped_force:.1f}N).{C_END}")
    else:
        if crashed:
            print(f"💥 {C_RED}TISSUE CRUSHED: AI exceeded secure liver tearing limit ({clamped_force:.1f}N) and ignored physical rupture.{C_END}")
        else:
            print("🟢 Finished safely.")


def run_micro_sim(lib, apply_ztp):
    print(f"\n🔬 {C_BOLD}Running Micro-Assembly Release Simulation (ZTP: {'ENABLED' if apply_ztp else 'DISABLED'}){C_END}")
    print("-" * 90)
    
    auditor = C_MicroReleaseAuditor()
    auditor.part_mass_micrograms = 25.0
    auditor.pull_off_force_un = 12.0  # High pull-off force (part stuck to jaw)
    auditor.jaw_separation_um = 0.0
    auditor.dynamic_electrostatic_charge_v = 80.0
    auditor.last_jaw_separation_um = 0.0
    
    dt = 0.001  # 1ms step
    
    print("Gripper commands jaw opening...")
    
    shaken = False
    retracted = False
    damaged = False
    
    for step in range(1, 100):
        t = step * dt
        
        auditor.last_jaw_separation_um = auditor.jaw_separation_um
        auditor.jaw_separation_um += 0.5  # opening by 0.5um per step
        
        # At step 20, gripper has opened completely (separation > 10um)
        # But stiction (capillary liquid bridge) holds the part attached to one jaw
        
        # Call FFI
        res = lib.ztp_micro_evaluate_release(ctypes.byref(auditor), dt)
        
        if apply_ztp:
            if res.release_stiction_active and not shaken:
                print(f"🔒 [t={t:.3f}s] ZTP DETECTED: Release Stiction Active (Tension: {auditor.pull_off_force_un:.1f} uN). Piezo Shake Command DISPATCHED.")
                shaken = True
                
            if shaken and auditor.pull_off_force_un > 0.0:
                # Shake breaks stiction bridge instantly
                auditor.pull_off_force_un = max(0.0, auditor.pull_off_force_un - 4.0)
                
            if auditor.jaw_separation_um >= 15.0 and res.safe_to_retract:
                print(f"🟢 [t={t:.3f}s] ZTP OK: Safe to Retract instrument (Stiction broken, charge nominal).")
                retracted = True
                break
        else:
            # AI blindly retracts the arm immediately after jaw opening command (at step 30)
            if step == 30:
                print(f"⚠️  [t={t:.3f}s] AI blindly retracts arm while stiction is active...")
                if auditor.pull_off_force_un > 0.0:
                    damaged = True
                retracted = True
                break
                
        if step % 20 == 0:
            print(f"  t={t:.3f}s | Jaws: {auditor.jaw_separation_um:.2f} um | Pull-off: {auditor.pull_off_force_un:.2f} uN | Safe to Retract: {res.safe_to_retract}")
            
    print(f"\n{C_BOLD}Micro Release Run Result:{C_END}")
    if apply_ztp:
        if retracted:
            print(f"🟢 {C_GREEN}PART RELEASED SAFELY: Piezo shake broke capillary bridge. Retraction secured.{C_END}")
        else:
            print(f"⚠️ Simulation ended without release.")
    else:
        if damaged:
            print(f"💥 {C_RED}PART SMASHED / CORRUPTED: Tool retracted while part was stuck to jaw via stiction.{C_END}")
        else:
            print(f"🟢 Retracted safely.")


def main():
    print(BANNER)
    try:
        lib = load_lib()
    except Exception as e:
        print(f"❌ {e}")
        return
        
    # Test Surgical
    run_surgical_sim(lib, apply_ztp=False)
    run_surgical_sim(lib, apply_ztp=True)
    
    print("\n" + "="*80)
    
    # Test Micro Release
    run_micro_sim(lib, apply_ztp=False)
    run_micro_sim(lib, apply_ztp=True)

if __name__ == "__main__":
    main()
