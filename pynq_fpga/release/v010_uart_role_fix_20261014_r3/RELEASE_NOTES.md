# Release Notes

Release date: 2026-10-21

This directory packages the v0.10 UART-role-fix runtime for repository delivery.
The FPGA `bit`/`HWH`, Python runtime payloads and STM32 firmware are byte-identical
to the package tested on 2026-10-14.

Only metadata was corrected relative to the tested package:

- restored the immutable r2 candidate source map as the comparison baseline;
- recorded all five source/test files changed by the UART-role fix;
- regenerated `artifact_source_binding.json` from the final manifest;
- fixed current-version text and added standalone wiring/startup notes.

Original tested package:
`pynq_fpga/lab/task7_8_lab_only_v010_uart_role_fix_20261014_r3`

Original tested ZIP SHA-256:
`fd4c8f10944f48fa6bb865bd3a3d0ef6b1c227f8dbe65c1010b7ba76e25acd9b`

This is a locked, no-motor bench release. It is not a whole-vehicle release and
does not authorize nonzero motor output.
