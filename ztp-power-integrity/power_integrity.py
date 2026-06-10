#!/usr/bin/env python3
"""
ZTP-POWER-INTEGRITY: High-Frequency SMPS Transient & Parametric Auditor.
Part of the Zero-Trust Physics runtime assurance framework.

This tool solves a critical hardware-reliability bottleneck for space LEO power systems:
Voltage regulator (Buck Converter) feedback loop instability caused by radiation-induced 
component degradation (capacitor aging/dielectric decay) under transient RF payloads.
It implements a 100 kHz simulator, audits parametric consistency, and adapts compensator gains.
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
  ███████╗████████╗██████╗     ██████╗  ██████╗ ██╗    ██╗███████╗██████╗ 
  ╚══███╔╝╚══██╔══╝██╔══██╗    ██╔══██╗██╔═══██╗██║    ██║██╔════╝██╔══██╗
    ███╔╝    ██║   ██████╔╝    ██████╔╝██║   ██║██║ █╗ ██║█████╗  ██████╔╝
   ███╔╝     ██║   ██╔═══╝     ██╔═══╝ ██║   ██║██║███╗██║██╔══╝  ██╔══██╗
  ███████╗   ██║   ██║         ██║     ╚██████╔╝╚███╔███╔╝███████╗██║  ██║
  ╚══════╝   ╚═╝   ╚═╝         ╚═╝      ╚═════╝  ╚══╝╚══╝ ╚══════╝╚═╝  ╚═╝
  Zero-Trust Physics: 100kHz SMPS Feedback Loop & Power Integrity Monitor
================================================================================{C_END}
"""

# Simulation Constants
HZ = 100000.0          # 100 kHz simulation step rate
DT = 1.0 / HZ
SIM_TIME = 0.025       # 25 milliseconds total simulation time
TOTAL_STEPS = int(SIM_TIME * HZ)

# Nominal Buck Converter Electronics Parameters
V_IN = 28.0            # V input satellite power bus
V_TARGET = 3.3         # V target output for RF/digital logic
BROWNOUT_LIMIT = 3.0   # V minimum logic threshold (reboot occurs below this)

L_NOMINAL = 15e-6      # H (15 uH Inductor)
C_NOMINAL = 220e-6     # F (220 uF Capacitor) - Tuned to prevent nominal brownout under transient
ESR_NOMINAL = 0.025    # Ohm (25 mOhm capacitor series resistance)
R_LOAD_NOMINAL = 3.3   # Ohm (nominal 1A draw)

def simulate_buck_step(v_c, i_l, duty_cycle, i_load, c_val, esr_val, dt):
    """
    Simulate state equations of a Buck Converter.
    v_c: voltage across the ideal capacitor (physical state variable)
    i_l: inductor current (physical state variable)
    duty_cycle: [0.0 - 1.0] PWM switch command
    i_load: current drawn by load
    """
    # 1. State derivative calculations
    v_switch = duty_cycle * V_IN
    i_c = i_l - i_load
    v_out = v_c + i_c * esr_val
    
    di_l = (v_switch - v_out) / L_NOMINAL
    dv_c = i_c / c_val
    
    # 2. State Integration (Forward Euler)
    new_v_c = v_c + dv_c * dt
    new_i_l = i_l + di_l * dt
    
    # Prevent negative current (discontinuous conduction mode boundary)
    if new_i_l < 0.0:
        new_i_l = 0.0
        
    return new_v_c, new_i_l, dv_c

def run_power_mission():
    """
    Simulate a LEO satellite power rail delivering 3.3V.
    At t=5.0ms: The RF phased array transmitter fires, stepping load current from 1.0A to 2.0A.
    At t=10.0ms: Radiation/thermal stress causes output capacitor degradation (C drops to 60uF).
    At t=15.0ms: The RF transmitter fires a second burst, stepping load again to 2.0A.
    """
    v_c = V_TARGET
    v_out = V_TARGET
    i_l = 1.0 # 1A initial current
    
    # PID controller state
    integral_err = 0.0
    prev_err = 0.0
    
    # Controller gains (tuned for nominal 220uF capacitor)
    Kp = 3.0
    Ki = 50.0
    Kd = 0.000002
    
    log = []
    
    # Current state parameters (degrade at t=10ms)
    c_val = C_NOMINAL
    esr_val = ESR_NOMINAL
    i_load = 1.0 # 1A base load
    
    for step in range(TOTAL_STEPS):
        t = step * DT
        
        # 1. Timeline Events
        # Event A: RF transmitter burst 1 (t=5ms to 8ms)
        if 0.005 <= t < 0.008:
            i_load = 2.0 # 2A transient load step
        # Event B: Capacitor degradation (t >= 10ms)
        elif t >= 0.010:
            c_val = 60e-6 # drops to 60 uF (72.7% loss of capacitance)
            esr_val = 0.050 # ESR increases to 50 mOhm
            i_load = 1.0
        else:
            i_load = 1.0
            
        # Event C: RF transmitter burst 2 (t=15ms to 18ms)
        if 0.015 <= t < 0.018:
            i_load = 2.0
            
        # Closed-Loop Feedback + Feedforward Compensator
        i_c = i_l - i_load
        v_out = v_c + i_c * esr_val
        
        err = V_TARGET - v_out
        integral_err += err * DT
        derivative_err = (err - prev_err) / DT
        prev_err = err
        
        ff = V_TARGET / V_IN
        duty_cycle = ff + Kp * err + Ki * integral_err + Kd * derivative_err
        duty_cycle = np.clip(duty_cycle, 0.0, 0.95) # cap duty cycle at 95%
        
        # 3. Physics step
        v_c, i_l, dv_c = simulate_buck_step(
            v_c, i_l, duty_cycle, i_load, c_val, esr_val, DT
        )
        
        log.append({
            "timestamp": t,
            "v_out": float(v_out),
            "i_l": float(i_l),
            "duty_cycle": float(duty_cycle),
            "i_load": float(i_load),
            "c_val": float(c_val),
            "esr_val": float(esr_val),
            "dv_c": float(dv_c)
        })
        
    return log

def audit_power_rail(log, apply_ztp_compensator=False):
    """
    Audit the power rail transient performance.
    If apply_ztp_compensator=True, ZTP detects the capacitance degradation in real-time,
    and retunes the PID controller gains to prevent loop oscillation and voltage brownout.
    """
    print(f"\n{C_BOLD}Auditing Power Subsystem (ZTP Power Integrity: {'ENABLED' if apply_ztp_compensator else 'DISABLED'}){C_END}")
    print("-" * 95)
    
    v_c = V_TARGET
    v_out = V_TARGET
    i_l = 1.0
    
    integral_err = 0.0
    prev_err = 0.0
    
    # PID gains (nominal)
    Kp = 3.0
    Ki = 50.0
    Kd = 0.000002
    
    # Estimation parameters
    estimated_c = C_NOMINAL
    c_degraded_detected = False
    
    brownout_tripped = False
    brownout_time = None
    
    steps_log = []
    
    for i, frame in enumerate(log):
        t = frame["timestamp"]
        i_load = frame["i_load"]
        c_val = frame["c_val"]
        esr_val = frame["esr_val"]
        
        # Calculate current v_out from states
        i_c = i_l - i_load
        v_out = v_c + i_c * esr_val
        
        # 1. RUN ZTP PARAMETRIC CONSTRAINTS CHECK
        # We estimate the physical capacitance in real-time using charge conservation:
        # i_c = C * dv_c/dt  =>  C = (i_L - i_load) / (dv_c/dt)
        # We can observe dv_c/dt as the derivative of output voltage during transient steps
        if i > 0:
            v_out_prev = steps_log[-1]["v_out"]
            dv_out_dt = (v_out - v_out_prev) / DT
            i_c_est = i_l - i_load
            
            # To avoid division by zero, we only estimate when there is a significant transient current
            if abs(dv_out_dt) > 10.0:
                raw_c_est = i_c_est / dv_out_dt
                # Bound estimation physically (capacitance cannot be negative)
                if 5e-6 < raw_c_est < 500e-6:
                    estimated_c = 0.98 * estimated_c + 0.02 * raw_c_est # low pass filter
                    
        # Parametric Inconsistency indicator: Mismatch between nominal C and estimated C
        c_mismatch = abs(C_NOMINAL - estimated_c) / C_NOMINAL
        
        # 2. Decision & Adaptation Logic
        if apply_ztp_compensator:
            # If capacitance drops by more than 40%
            if c_mismatch > 0.40 and not c_degraded_detected:
                c_degraded_detected = True
                print(f"🔒 {C_RED}{C_BOLD}[t={t*1000:.2f}ms] PARAMETRIC DEGRADATION DETECTED! Capacitance dropped to {estimated_c*1e6:.1f} uF (ESR increased).{C_END}")
                print(f"   ├─ Action: RETUNING PID COMPENSATOR GAINS to stabilize degraded LC loop.")
                # Retune PID parameters: Lower Kp/Ki to prevent oscillation and handle degraded C
                Kp = 0.1
                Ki = 10.0
                Kd = 0.000002
                
        # 3. PID Loop Execution
        # Closed-Loop Feedback + Feedforward Compensator
        err = V_TARGET - v_out
        integral_err += err * DT
        derivative_err = (err - prev_err) / DT
        prev_err = err
        
        ff = V_TARGET / V_IN
        duty_cycle = ff + Kp * err + Ki * integral_err + Kd * derivative_err
        duty_cycle = np.clip(duty_cycle, 0.0, 0.95)
        
        # 4. Integrate physical step
        v_c, i_l, dv_c = simulate_buck_step(
            v_c, i_l, duty_cycle, i_load, c_val, esr_val, DT
        )
        
        # 5. Check logic brownout
        if v_out < BROWNOUT_LIMIT and not brownout_tripped:
            brownout_tripped = True
            brownout_time = t
            print(f"💥 {C_RED}{C_BOLD}[t={t*1000:.2f}ms] LOGIC BROWNOUT! V_out dropped to {v_out:.3f}V below {BROWNOUT_LIMIT}V limit.{C_END}")
            print(f"   └─ Cause: Degraded output capacitance caused loop under-damping, resulting in transient voltage collapse.")
            
        steps_log.append({
            "t": t,
            "v_out": float(v_out),
            "estimated_c": float(estimated_c),
            "brownout": brownout_tripped
        })
        
    print(f"\n{C_BOLD}Power Rail Summary:{C_END}")
    print(f"Total test time: {SIM_TIME*1000:.1f} ms")
    print(f"ZTP Loop Retuning: {'ENABLED' if apply_ztp_compensator else 'DISABLED'}")
    print(f"Minimum Voltage: {min([s['v_out'] for s in steps_log]):.3f} V")
    print(f"Result: {C_GREEN}SYSTEM OPERATIONAL (Voltage Regulated){C_END}" if not brownout_tripped else f"{C_RED}SYSTEM SHUTDOWN (Brownout Reboot){C_END}")
    
    if apply_ztp_compensator and c_degraded_detected:
        log_bytes = json.dumps(steps_log).encode("utf-8")
        seal = hashlib.sha256(log_bytes).hexdigest()
        print(f"🔒 {C_BOLD}SHA-256 Power Telemetry Seal:{C_END} {C_BLUE}{seal}{C_END}")
        
    return not brownout_tripped

def main():
    print(BANNER)
    
    # 1. Run simulation
    log = run_power_mission()
    
    # 2. Audit WITHOUT ZTP (reboots at second load step)
    audit_power_rail(log, apply_ztp_compensator=False)
    
    print("\n" + "="*80 + "\n")
    
    # 3. Audit WITH ZTP (survives by adjusting compensator gains)
    audit_power_rail(log, apply_ztp_compensator=True)

if __name__ == "__main__":
    main()
