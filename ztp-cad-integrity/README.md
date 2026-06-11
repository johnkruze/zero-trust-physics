# ZTP-CAD-INTEGRITY: Simulation Model Physical consistency Validator & Repair Engine

A CLI tool that solves a critical, universal bottleneck in robotics simulation: **physical instability, high joint stiffness, and simulator explosions caused by invalid or inconsistent inertia properties exported from CAD tools (SolidWorks, STEP, OnShape).**

This tool parses Unified Robot Description Format (URDF) files, evaluates the physical realizability of each link's mass and inertia tensor, mathematically repairs invalid tensors via convex quadratic programming (SLSQP), and seals the verified model with a retroactively tamper-evident SHA-256 cryptographic seal.

---

## The Simulation Import Pain Point

When mechanical designers export robotic assemblies from SolidWorks or Autodesk Inventor to URDF/SDF, the generated physical properties are frequently broken:
1. **Invalid Masses:** Empty assemblies or reference coordinate frames are exported with zero or negative masses.
2. **Non-Positive-Definite Tensors:** Off-diagonal elements (products of inertia) are generated that exceed the diagonal elements, resulting in negative eigenvalues.
3. **Triangle Inequality Breaches:** The principal moments of inertia ($I_1, I_2, I_3$) violate the physical constraint:
   $$I_i + I_j \ge I_k \quad \text{for all cyclic permutations}$$
   This happens because CAD exporters treat components as hollow or fail to compute volume integrals correctly. 

### Why This Crashes Simulators
Physics engines (MuJoCo, Drake, Isaac Sim, PhysX) formulate contacts and rigid body dynamics using joint-space mass matrices:
$$M(q) = J^T M_b J$$
If any link violates the triangle inequalities or positive-definiteness, $M(q)$ loses its positive-definite structure, resulting in **negative kinetic energy** or **division by zero** in the contact solvers. The simulator immediately explodes (e.g. `NaN` errors or links flying off at infinite velocity).

---

## The Solution: Semidefinite Projection

Instead of forcing engineers to manually adjust numbers in XML files by trial and error, `ztp-cad-integrity` projects the invalid CAD-exported tensor onto the closest boundary of the **Physical Manifold** ($\mathcal{M}_{\text{minimax}}$).

### The Mathematics of Repair
For any symmetric, invalid inertia tensor $I_{\text{raw}}$:
1. We compute its principal axes and moments of inertia using eigendecomposition:
   $$I_{\text{raw}} = R \operatorname{diag}(\lambda_0, \lambda_1, \lambda_2) R^T$$
   where $R$ is the rotation matrix of the principal axes, and $\boldsymbol{\lambda} = [\lambda_0, \lambda_1, \lambda_2]^T$ are the raw principal moments of inertia.
2. We project the eigenvalues $\boldsymbol{\lambda}$ onto the convex polyhedron defined by positivity and the triangle inequalities:
   $$\min_{\mathbf{I}_{\text{valid}}} \|\mathbf{I}_{\text{valid}} - \boldsymbol{\lambda}\|^2$$
   $$\text{subject to: } \quad I_i \ge 10^{-6}$$
   $$I_0 + I_1 \ge I_2$$
   $$I_0 + I_2 \ge I_1$$
   $$I_1 + I_2 \ge I_0$$
3. We reconstruct the repaired, physically consistent tensor:
   $$I_{\text{repaired}} = R \operatorname{diag}(\mathbf{I}_{\text{valid}}^*) R^T$$

*By using this projection, we preserve the orientation of the principal axes of inertia ($R$) exported from CAD, while performing the minimal possible adjustment to the principal moments to ensure physical consistency.*

---

## Features

- **Automated Scanning:** Scans all `<link>` elements and verifies mass and inertia variables.
- **Convex Optimization Solver:** Re-computes the closest physical tensor using Scipy's Sequential Least Squares Programming (SLSQP).
- **Zero Dependencies for Verification:** Verification runs on pure Python standard libraries. Repairs require only `numpy` and `scipy`.
- **ZTP Cryptographic Sealing:** Appends a SHA-256 validation certificate directly to the bottom of the output URDF. If the file is altered, the seal becomes invalid.

---

## Installation & Requirements

Ensure you have a Python environment with `numpy` and `scipy` installed:
```bash
pip install numpy scipy
```

---

## Usage

### 1. Scan a URDF for physical boundary violations
```bash
python3 validate_urdf.py path/to/model.urdf
```

### 2. Repair invalid tensors and export a sealed URDF
```bash
python3 validate_urdf.py path/to/broken_model.urdf --repair -o path/to/repaired_model.urdf
```

---

## Demonstration: Running the Samples

Run the included test suite to see the validator and repair engine in action:

```bash
# 1. Scan the nominal (valid) model
python3 validate_urdf.py samples/quadruped_nominal.urdf

# 2. Scan the broken CAD model (will highlight violations)
python3 validate_urdf.py samples/quadruped_broken_cad.urdf

# 3. Repair the broken model and seal it
python3 validate_urdf.py samples/quadruped_broken_cad.urdf --repair -o samples/quadruped_repaired.urdf
```

### Repaired URDF Output Format
The resulting file retains all original geometry and kinematic chains, but replaces invalid `<inertia>` attributes and appends the cryptographic seal:

```xml
<!-- ... repaired links ... -->
</robot>

<!-- 
==========================================================================
  ZERO-TRUST PHYSICS (ZTP) RUNTIME ASSURANCE CERTIFICATE
  
  This simulation model has been validated against physical boundaries.
  All inertia tensors are verified as positive-definite and geometrically realizable.
  
  SHA-256 SEAL: a15136ec4689d7da771212a59c6e4fa9f3471373b0e680360168a035843f2d8d
==========================================================================
-->
```

---

## Case Study: Full Mathematical Breakdown

[**→ ZTP CAD Ingestion Gate Showcase**](samples/ingestion_gate_showcase.md)

Step-by-step walkthrough of the SLSQP projection executing on a corrupted quadruped model — three specific CAD export failures, the exact optimization math, the repaired output, and the cryptographic seal.

---

Part of the [Zero-Trust Physics](https://github.com/johnkruze/zero-trust-physics) suite · [ZeroTrustPhysics.com](https://ZeroTrustPhysics.com)
