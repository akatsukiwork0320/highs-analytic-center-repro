# Wrong Optimal 0 instead of 1 with presolve=off: analytic-center fixing of a continuous column

HiGHS 1.15.1 (`04024d7`, highspy) reports **Optimal, objective 0** for the following 11-column, 4-row MIP. Its exact optimum is **1**: the explicit feasible point below attains the upper bound `g <= 1`.

```text
maximize g
r - f - k*g = 0             k = 0.000002
r - f - y = 0
g - v <= 0
525*z0 + 560*z1 + 779*z2 + 955*z3 + 131*z4 + 229*z5 - 1470*v = 0

0 <= g <= 1
0 <= f,r,y <= 1000
v,z0,...,z5 binary
```

A feasible point is `g=v=1`, `r=y=k`, `f=0`, `z1=z2=z4=1`, all other z values zero. In particular, `560+779+131=1470`. This works both for rational-decimal k and for the exact binary64 k loaded from the MPS below.

Save the MPS at the end of this report as `small_repro_17digit.mps`, then run:

```python
import platform
import highspy

h = highspy.Highs()
print(platform.system(), platform.machine(), platform.python_version(),
      h.version(), h.githash())
assert h.readModel("small_repro_17digit.mps") == highspy.HighsStatus.kOk
for name, value in {"presolve": "off", "threads": 1, "random_seed": 0,
                    "time_limit": 10.0, "log_dev_level": 1}.items():
    assert h.setOptionValue(name, value) == highspy.HighsStatus.kOk
h.run()
print(h.modelStatusToString(h.getModelStatus()),
      h.getInfo().objective_function_value)
# Observed: Optimal 0.0; exact optimum: 1.
```

Excerpt from the recorded MPS run:

```text
 J       0       0         0   0.00%   inf             -0                 Large        0      0      0         0     0.0s
         0       0         0   0.00%   1               -0                 Large        0      0      2         0     0.0s
Fixing 1 columns (0 integers) sitting at bound at analytic center
         1       0         1 100.00%   -0              -0                 0.00%       11      3      2         9     0.0s
```

| Setting, seed 0 and one thread | Reported objective |
|---|---:|
| Presolve off, API input | 0 (Optimal, 1 node) |
| Presolve off, MPS input | 0 (Optimal, 1 node) |
| Presolve on | 1 |
| Presolve off, mip_feasibility_tolerance=1e-9 | 1 |
| Presolve off, implied bound y<=k | 1 |

The five cases were checked with the distributed reproducer on Windows 11 x86-64, Python 3.12.14, highspy 1.15.1. The loaded API/MPS coefficients, bounds, integrality and objective were checked against their intended exact binary64 models, including the extra bound in the last case. A separate baseline run under gdb on Linux x86-64, highspy 1.15.1 also returned 0. That debugger run used a 120-second time limit and `mip_rel_gap=1e-6`; it is not a timing comparison. Other seeds and builds are not claimed here.

The two equalities imply `y=k*g`; together with `g<=1`, this gives the valid implied bound `y<=k`, which removes no feasible points.

### Observed fixing

In the Linux run, gdb on the unmodified PyPI library recorded a direct call from [`finishAnalyticCenterComputation`](https://github.com/ERGO-Code/HiGHS/blob/v1.15.1/highs/mip/HighsMipSolverData.cpp#L505-L541) to `HighsDomain::changeBound`. Exactly one column was fixed:

- column 3, `y`;
- analytic-center value `5.353065146424651e-7`;
- current domain `[0,1000]`, giving a threshold of `feastol * min(1000,1) = 1e-6`;
- upper bound changed to `0`, with reason `unspecified`, and domain `[0,0]` confirmed after the call.

This bound excludes the feasible point above. Because `y=k*g` and `k>0`, it forces `g=0`.

The implied range of y is only `[0,k]`, although the recorded domain at this test remains `[0,1000]`. Even an exact feasible center would satisfy `y=k*g_center`; whenever `g_center<=0.5`, its y value is at most the threshold, satisfying the loop's `<=` test. Thus the observed fixing need not be explained by inaccurate center computation.

Possibly related: [#2173](https://github.com/ERGO-Code/HiGHS/issues/2173). Version 1.15.1 already includes [#2663](https://github.com/ERGO-Code/HiGHS/pull/2663), which enables `run_centring`. The reproduction above shows the failure with that change present; it is not a claim about all versions or a proposed general fix.

A source-only check on 2026-10-10 found the same loop, unchanged, on the `latest` development branch at [f2ec37bc0365](https://github.com/ERGO-Code/HiGHS/blob/f2ec37bc0365c3f7527c27c5f6bc098e1fa2c8f3/highs/mip/HighsMipSolverData.cpp#L509-L545). That development commit has not been executed for this report.

AI agents constructed and ran the reproducer, inspected the runtime trace, and checked the model with exact rational arithmetic. The measurements above are agent-run. The 11-variable example originated in a Claude-assisted review.

<details>
<summary>small_repro_17digit.mps — complete input</summary>

```text
NAME SMALL_REPRO
OBJSENSE
 MAX
ROWS
 N OBJ
 E k_balance
 E y_balance
 L gate
 E subset
COLUMNS
    g OBJ 1
    g k_balance -1.9999999999999999e-06
    g gate 1
    f k_balance -1
    f y_balance -1
    r k_balance 1
    r y_balance 1
    y y_balance -1
    MARK0000 'MARKER' 'INTORG'
    v gate -1
    v subset -1470
    z0 subset 525
    z1 subset 560
    z2 subset 779
    z3 subset 955
    z4 subset 131
    z5 subset 229
    MARK0001 'MARKER' 'INTEND'
RHS
    RHS1 k_balance 0
    RHS1 y_balance 0
    RHS1 gate 0
    RHS1 subset 0
BOUNDS
 LO BND g 0
 UP BND g 1
 LO BND f 0
 UP BND f 1000
 LO BND r 0
 UP BND r 1000
 LO BND y 0
 UP BND y 1000
 BV BND v
 BV BND z0
 BV BND z1
 BV BND z2
 BV BND z3
 BV BND z4
 BV BND z5
ENDATA
```

</details>
