# M7 xG-informed Bayesian parent

Source: September 6, 2026 steering memo. The batch implementation and evaluation
are complete; [the report](experiments/m7_xg_parent.md) records decisions and limits.
M2 remains the unchanged operational benchmark.

| Requirement | Evidence |
| --- | --- |
| Separate information, representation and operational evidence | `research_principles.md` |
| Pin long-history Understat match xG and reconcile fixtures | `experiments/m7/understat_audit.json`, `configs/understat_snapshot.json` |
| Center Tilt while preserving priors, dynamics and forecasts | `centered_quality_tilt_model.md`, `experiments/m7/centered_reference.json` |
| Joint probabilistic goals/xG channel with uncertainty | `xg_model.md`, `experiments/m7/xg_reference.json`, likelihood/cutoff tests |
| Chronological M2/M5/M7 comparison and diagnostics | `experiments/m7/chronological_summary.json`, `experiments/m7/diagnostics.json` |
| High-information, adaptation and state checks | Oracle and known-state tracking sections in `diagnostics.json` |
| Evolving season simulation | 350-fixture, 10,000-path M7 archive and direct-frequency/table checks |
| Audit player process and identity feasibility | `experiments/m7/understat_players.json`, `configs/understat_player_sample.json` |
| Continue M5/M6 prospective capture | `experiments/m7/prospective_manifest.json` and retained bundle |
| Preserve benchmark and avoid prohibited tuning | Final diff audit; M2 and M6-v1 parameters unchanged |

Remaining scientific limitations are not hidden implementation tasks: the xG
observation is simplified, historical publication times are unverified, calibration
is not established, opening/promoted slices do not improve, and player identity/role
mappings require a separate formulation. Operational promotion is not justified.
