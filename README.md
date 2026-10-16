# Auditing a MIP solver's Optimal claim with exact certificates (HiGHS 1.15.1 case study)

This **11-variable, 4-row MIP has exact optimum 1**, yet the recorded HiGHS 1.15.1 baseline reports **`Optimal`, objective 0**. An explicit feasible point attains the declared upper bound `g <= 1`; an independent standard-library checker verifies both with exact rational arithmetic.

This repository contains the reproducer and verification material. **Reported upstream as [HiGHS issue #3387](https://github.com/ERGO-Code/HiGHS/issues/3387) on 2026-10-10 (JST). A maintainer [confirmed the bug on `latest`](https://github.com/ERGO-Code/HiGHS/issues/3387#issuecomment-6120063138), and the fix, [PR #3408](https://github.com/ERGO-Code/HiGHS/pull/3408), was merged into `latest` on 2026-10-16 (JST) as commit [`c2ddc850`](https://github.com/ERGO-Code/HiGHS/commit/c2ddc850fc0594ea1afbae1eca3cb0b642f00537).** The [earlier source-build verification at `7bb364c1733`](https://github.com/ERGO-Code/HiGHS/pull/3408#issuecomment-6152858701) remains a record of that candidate commit. See [ISSUE_EN.md](ISSUE_EN.md) for the original model and report.

A new agent-run source-build comparison on 2026-10-16 tested the merged commit against a control built from the same checkout with only `HighsMipSolverData.cpp` restored from its first parent, `9c97fd0d098eb1630b932bacee69edbf502c74e7`. On Linux x86-64, CPython 3.12.3, one thread and seed 0, the original five settings and the five settings of the [999-redundant-row variant](https://github.com/ERGO-Code/HiGHS/issues/3387#issuecomment-6128073516) all returned objective 1 on the merged build; the control reproduced objective 0 in the five previously failing settings. Exact rational checks accepted 7 of the merged build's 10 returned points, including the presolve-off API and MPS baseline points; three others had small nonzero residuals. The separate exact witness and upper bound establish optimum 1 for every tested model. This checks these examples, not general safety of the tighter fixing tolerance, solver performance, or inclusion in a released version.

With `highspy` already installed, run from this directory:

```sh
python standalone_repro.py baseline --output-dir baseline_results
python standalone_repro.py all --output-dir five_case_results
```

Each output directory must be new. `baseline` performs one solve; `all` performs the five cases below, once each, with a 10-second limit per case. The script records OS, Python and HiGHS versions, seed, threads, and settings. Before each solve it checks the complete loaded API or MPS model against the definition, including coefficients, bounds, integrality, and objective, and verifies the exact witness in that loaded model. It installs no packages. Versions other than HiGHS 1.15.1 are allowed with a warning but have not been tested here.

| Case (`random_seed=0`, `threads=1`) | Reported result on Windows |
|---|---|
| `baseline`: API input, presolve off | Optimal 0 |
| `presolve_on`: API input, presolve on | Optimal 1 |
| `tight_tolerance`: presolve off, `mip_feasibility_tolerance=1e-9` | Optimal 1 |
| `proved_y_bound`: presolve off, implied bound `y <= k` | Optimal 1 |
| `mps`: supplied MPS input, presolve off | Optimal 0 |

All five were measured on **Windows 11 x86-64, Python 3.12.14, highspy/HiGHS 1.15.1 (`04024d7`)**. A separate baseline under gdb on Linux x86-64 with highspy 1.15.1 also returned 0; that run used a 120-second limit and `mip_rel_gap=1e-6`. The Linux observation covers the baseline only, and these runs are not a timing comparison. That original package-level comparison does not cover other seeds or builds; the later source-build comparison is described above.

The independent proof checker needs **only Python's standard library**:

```sh
python exact_check.py
python exact_check.py --records five_case_results
```

The first command proves optimum 1 for the stated decimal and binary64 models separately. The second also checks the saved actual models, input and objective identities, witnesses, and returned points. It imports neither `highspy` nor the reproducer and writes only to stdout. The decimal value `k=1/500000` and the exact value of binary64 `0.000002` are distinct; each has its own exact witness. A numerical solver point is not silently treated as an exact witness: the presolve-on returned point has about `5.05e-15` equality residual, while the separate exact witness establishes optimum 1.

The reproducer files are [standalone_repro.py](standalone_repro.py), [exact_check.py](exact_check.py), and [small_repro_17digit.mps](small_repro_17digit.mps). [trace_excerpt.json](trace_excerpt.json) records the observed bound change described in the report. This is a small case study, without a claim of mathematical minimality, performance improvement, or a tested general fix.

AI agents constructed and ran the reproducer, inspected the runtime trace, and checked the model with exact rational arithmetic. The measurements above are agent-run. The 11-variable example originated in a Claude-assisted review.

The original files distributed in this repository are licensed under **Apache-2.0**; see [LICENSE](LICENSE). `highspy`/HiGHS is a separate dependency under the **MIT license** and is not included in this repository.

Contact: Satoshi Kawasaki — [akatsuki.work@gmail.com](mailto:akatsuki.work@gmail.com).
