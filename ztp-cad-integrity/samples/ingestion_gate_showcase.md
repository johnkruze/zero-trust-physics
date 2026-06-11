# Zero-Trust CAD Ingestion Gates: Real-Time Manifold Projection and Cryptographic Verification

Traditional CAD tools (SolidWorks, OnShape, Fusion 360, STEP exporters) are geometric sculptors. They represent shapes, not physics. When exporting mechanical assemblies to simulation formats (URDF/SDF), they systematically generate **non-physical garbage**: negative masses, non-positive-definite inertia tensors, and triangle inequality breaches. 

To a visual CAD tool, a model looks perfect. To a high-fidelity physics engine (MuJoCo, Drake, Isaac Gym), these errors represent **negative kinetic energy** and **division-by-zero singularities** in the contact/constraint solvers, resulting in high joint stiffness, IMU drift, and immediate simulation explosions (NaN errors).

**The Zero-Trust CAD Ingestion Gate** replaces human guesswork and statistical neural approximation with first-principles mathematics. It parses robot models, isolates coordinate-level physics violations, and uses **Convex Quadratic Programming (SLSQP)** to project the invalid parameters onto the boundary of the physically realizable manifold, appending an immutable, tamper-evident SHA-256 cryptographic seal.

---

## The Mathematical Target: The Physical Manifold ($\mathcal{M}$)

A symmetric tensor $I$ is physically realizable as a rigid-body mass distribution if and only if its principal moments of inertia (eigenvalues $\boldsymbol{\lambda} = [\lambda_0, \lambda_1, \lambda_2]^T$) are strictly positive and satisfy the triangle inequalities:

$$\lambda_0 + \lambda_1 \ge \lambda_2$$
$$\lambda_0 + \lambda_2 \ge \lambda_1$$
$$\lambda_1 + \lambda_2 \ge \lambda_0$$

If any CAD export violates these boundaries, the joint-space mass matrix $M(q)$ loses its positive-definite structure. The Ingestion Gate intercepts the model at the compiler boundary and runs the following semidefinite optimization loop:

```
 CAD Export (URDF) 
        ↓
 Parse Link Geometry & Mass Properties
        ↓
 Is mass <= 0?  ──[Yes]──>  Force nominal minimum (0.001 kg)
        ↓
 Compute Eigenvalues (Principal Moments)
        ↓
 Validate Invariants (Positive-Definiteness & Triangle Inequalities)
        ↓
   [Breached] ──> Solve Convex QP via SLSQP:
                  min_{x} ||x - λ||²
                  subject to: x_i >= 10⁻⁶
                             x_i + x_j >= x_k
        ↓
 Reconstruct Valid Tensor: I_repaired = R * diag(x*) * R^T
        ↓
 Write Repaired URDF + Append SHA-256 Cryptographic Seal
```

---

## Case Study: Quadruped Robot Model Repaired

Below is the step-by-step mathematical breakdown of the ZTP Ingestion Gate executing on a corrupted quadruped model ([quadruped_broken_cad.urdf](file:///Users/aijesusbro/Spectrum/zero-trust-physics/ztp-cad-integrity/samples/quadruped_broken_cad.urdf)).

### Link 1: `hip_yaw_link` (Mass Insecurity)
*   **The CAD Error:** The exporter generated a coordinate frame with a negative mass:
    ```xml
    <mass value="-0.85"/>
    ```
*   **The ZTP Resolution:** Mass is forced to the nominal physical minimum ($0.001\text{ kg}$). The inertia eigenvalues were already positive, so they are preserved.

### Link 2: `upper_leg_link` (Triangle Inequality Breach)
*   **The CAD Error:** The exporter modeled the leg as an impossible needle-like object, failing to calculate volume integrals. The diagonal inertia terms are:
    ```xml
    <inertia ixx="0.002" ixy="0.0" ixz="0.0" iyy="0.002" iyz="0.0" izz="0.050"/>
    ```
    Here, the principal moments are $\boldsymbol{\lambda} = [0.002, 0.002, 0.050]^T$. 
    $$\lambda_0 + \lambda_1 = 0.002 + 0.002 = 0.004 < 0.050 \quad (\text{BREACH})$$
    *A rigid body cannot have a moment of inertia about its longitudinal axis ($\lambda_2$) that is $12.5\times$ greater than the sum of its transverse axes. This represents a non-physical solid.*
*   **The SLSQP Projection:** The optimizer projects $\boldsymbol{\lambda}$ onto the closest valid boundary:
    $$\mathbf{I}_{\text{valid}}^* = [0.017333, 0.017333, 0.034667]^T$$
    Note that $0.017333 + 0.017333 = 0.034667$. The solver pushed the impossible needle-mass exactly to the boundary of physical realizability, adjusting the moments minimally while preserving the principal axes.
*   **Repaired Output:**
    ```xml
    <inertia ixx="0.017333333" ixy="0.000000000" ixz="0.000000000" 
             iyy="0.017333333" iyz="0.000000000" izz="0.034666667" />
    ```

### Link 3: `lower_leg_link` (Non-Positive-Definite Matrix)
*   **The CAD Error:** The exporter generated dominant off-diagonal elements (products of inertia):
    ```xml
    <inertia ixx="0.0005" ixy="0.0015" ixz="0.0" iyy="0.0005" iyz="0.0" izz="0.0008"/>
    ```
    The determinant of the 2D transverse block is:
    $$\det(I_{2D}) = I_{xx}I_{yy} - I_{xy}^2 = (0.0005)(0.0005) - (0.0015)^2 = -2.0 \times 10^{-6} < 0$$
    Eigendecomposition yields a negative eigenvalue: $\boldsymbol{\lambda} = [-0.001, 0.0008, 0.002]^T$.
    *A negative eigenvalue means the link has negative kinetic energy under rotational acceleration, causing the contact solver to divide by zero and fly off to infinity.*
*   **The SLSQP Projection:** The solver projects the negative eigenvalue to the minimum physical noise floor ($10^{-6}$) and re-balances the remaining moments.
*   **Repaired Output:**
    ```xml
    <inertia ixx="0.000700750" ixy="0.000699750" ixz="0.000000000" 
             iyy="0.000700750" iyz="0.000000000" izz="0.001399500" />
    ```

---

## Execution Log: Ingestion Gate in Action

```bash
$ python3 validate_urdf.py samples/quadruped_broken_cad.urdf --repair -o samples/quadruped_repaired.urdf
```

```text
================================================================================
  ███████╗████████╗██████╗      ██████╗ █████╗ ██████╗ 
  ╚══███╔╝╚══██╔══╝██╔══██╗    ██╔════╝██╔══██╗██╔══██╗
    ███╔╝    ██║   ██████╔╝    ██║     ███████║██║  ██║
   ███╔╝     ██║   ██╔═══╝     ██║     ██╔══██║██║  ██║
  ███████╗   ██║   ██║         ╚██████╗██║  ██║██████╔╝
  ╚══════╝   ╚═╝   ╚═╝          ╚═════╝╚═╝  ╚═╝╚═════╝ 
  Zero-Trust Physics: CAD-to-Sim Inertia & Mesh Physical Validator
================================================================================

Scanning URDF: quadruped_broken_cad.urdf
Path: samples/quadruped_broken_cad.urdf

Link Name                 | Mass     | Physical Integrity Status          
------------------------------------------------------------------------------
base_link                 | ok       | ✔ PASSED (Valid Inertia)
hip_yaw_link              | ok       | ⚠ REPAIRED (Projected to physical manifold)
  └─ Issue: Invalid mass: -0.85 <= 0
upper_leg_link            | ok       | ⚠ REPAIRED (Projected to physical manifold)
  └─ Issue: Triangle inequalities violated. Principal moments: [0.002000, 0.002000, 0.050000]. Violates geometry constraints (impossible physical mass distribution).
lower_leg_link            | ok       | ⚠ REPAIRED (Projected to physical manifold)
  └─ Issue: Inertia tensor is not positive-definite. Eigenvalues: [-0.001   0.0008  0.002 ]
  └─ Issue: Triangle inequalities violated. Principal moments: [-0.001000, 0.000800, 0.002000]. Violates geometry constraints (impossible physical mass distribution).

Verification Summary:
Total Inertial Links Checked: 4
Failed Physical Boundary checks: 3

All 3 failed links have been mathematically projected and repaired.

✔ Repaired model successfully written to: samples/quadruped_repaired.urdf
🔒 SHA-256 Cryptographic Seal: a15136ec4689d7da771212a59c6e4fa9f3471373b0e680360168a035843f2d8d
```

---

## The Cryptographic Seal: Verifiable Physical Trust

The output file [quadruped_repaired.urdf](file:///Users/aijesusbro/Spectrum/zero-trust-physics/ztp-cad-integrity/samples/quadruped_repaired.urdf) is saved with the repaired XML attributes and sealed with the SHA-256 digest of the file structure appended to the bottom:

```xml
<!-- 
==========================================================================
  ZERO-TRUST PHYSICS (ZTP) RUNTIME ASSURANCE CERTIFICATE
  
  This simulation model has been validated against physical boundaries.
  All inertia tensors are verified as positive-definite and geometrically realizable.
  
  SHA-256 SEAL: a15136ec4689d7da771212a59c6e4fa9f3471373b0e680360168a035843f2d8d
==========================================================================
-->
```

If any developer or tool manually alters a mass value, an inertia variable, or a mesh parameter after certification, re-running the verification will output a mismatched hash. 

The compiler or simulator immediately detects the broken seal and blocks execution. **Physics is no longer an assertion to trust; it is a calculation to repeat and verify.**
