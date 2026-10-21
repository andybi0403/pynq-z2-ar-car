# 2026-10-21 Code Verification

## Scope

The regression used the current `v0.10` host, STM32 and RTL sources. It did not
rebuild the Vivado implementation or operate the board. The existing r2 full
layout/route result and the r3 locked no-motor hardware evidence remain the
authoritative build and board records.

## Results

| Area | Result |
|---|---|
| STM32 C safety and hybrid protocol | PASS |
| STM32 ARM UART-role tests | 7/7 PASS |
| PC link suites | 28/28 PASS in the integrated acceptance run |
| Host Python tests | 150/150 PASS |
| Preintegration/runtime/video/evidence tests | 161/161 PASS |
| Supervisor fault matrix | 15/15 PASS |
| Browser MJPEG player tests | PASS |
| RTL self-checking simulations | 20/20 PASS |
| Forward overlay pixels | 6 frames, 1,843,200 pixels, 0 mismatches |
| Frame display chain pixels | 4 frames, 1,228,800 pixels, 0 mismatches |
| Status OSD pixels | 4 frames, 614,400 pixels, 0 mismatches |
| Text OSD pixels | 7 frames, all pixel-exact |
| Full 640x480 OSD pixels | 307,200 pixels, pixel-exact |
| Candidate file identity | PASS |
| Current release/source-patch identity | PASS, 360 source inputs |
| Skill helper tests | 23/23 PASS |

## Commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/preintegration/run_software_round.ps1 -Round 5
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/fpga/scripts/run_acceptance.ps1
python pynq_fpga/preintegration/source_provenance.py --capture validation/source_identity_20261021.json
python skill/amd-pynq-project-workflow/scripts/inspect_candidate.py --project-root . --candidate pynq_fpga/preintegration/portable_r2/latest_candidate.json --skip-current-sources
python skill/amd-pynq-project-workflow/scripts/inspect_release.py --project-root .
python -m unittest discover -s skill/amd-pynq-project-workflow/scripts -p "test_*.py" -v
```

## Evidence

- Software transcript:
  `pynq_fpga/audit/wireless_five_rounds_20261004/round5_evidence/software.log`
- RTL transcript:
  `pynq_fpga/nightly/acceptance_20260918/run_20261021_234039/regression.log`
- Full source identity:
  `validation/source_identity_20261021.json`
- Candidate inspection:
  `validation/candidate_inspection_20261021.json`
- Release inspection:
  `validation/release_inspection_20261021.json`

## Not Proven

- No new full synthesis, implementation, timing, DRC or HWH audit was run on
  2026-10-21.
- No new electrical measurement, encoder calibration, motor-connected run,
  HDMI color-order check or 1800-second joint test was run.
- The release remains `LAB_ONLY_NO_MOTOR_NON_RELEASE`; whole-vehicle acceptance
  is `NOT_CLAIMED`.
