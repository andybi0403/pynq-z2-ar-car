# Third-Party Notices

The root [MIT License](LICENSE) applies only to original project code and
documentation. Files under `pynq_fpga/third_party/` and generated font assets
retain their upstream terms. The detailed file-level adoption record is
`pynq_fpga/OPEN_SOURCE_USAGE.md`.

| Component | Pinned source | License / use |
|---|---|---|
| verilog-axi | `alexforencich/verilog-axi` commit `516bd5dadc3365b7f9e225d2af8fe0b8d804fe53` | MIT. Three `axil_reg_if*.v` files are reused with their copyright headers retained. |
| PYNQ board IP | `Xilinx/PYNQ` commit `e054c09c52db3244ef35c8ae08a2e62c1e4955fd` | BSD-3-Clause. `axi_dynclk` and `rgb2dvi` IP sources are used with local Vivado 2026.1 integration. |
| AMDC-Firmware | `Severson-Group/AMDC-Firmware` commit `5cf9769d33cc821fd55b4268ab80e285e3d4a607` | BSD-3-Clause. Snapshot is reference evidence; project RTL is independently implemented. |
| HC-SR04-FPGA | `yunkai1841/HC-SR04-FPGA` commit `f4df022d27349fbf1dd71fb0aa99834365dfe0a9` | CC0-1.0. Snapshot is reference evidence for ultrasonic behavior. |
| Project F Explore | `projf/projf-explore` commit `dd212c2e5e0e0d8bdcf93ba077630dbfd49ae708` | RTL is MIT. No upstream font resource is used; project glyphs are self-made. |
| Sobel pipeline reference | `erendn/sobel-pipeline-fpga` commit `c765b9d058ce489f9b262e9c5e83a99599a91e4a` | MIT. Architecture reference only; project pipeline implementation is independent. |
| Noto Sans SC glyph source | Google Fonts / Noto Sans SC, recorded in `pynq_fpga/fpga/rtl/font_16x16_hud.json` | SIL Open Font License 1.1; text in `pynq_fpga/fpga/rtl/font_16x16_hud_OFL.txt`. |
| PYNQ-Z2 Sobel HDMI example | `aclich/PYNQ-Z2_sobel_filter_HDMI` commit `71a4409d76470fac7daed6552b9b3188ffe69d8f` | No repository license found. No source, notebook, bit/HWH or binary is included as project code; behavior/structure reference only. |

The original board, STM32 BSP and vendor PDFs remain subject to their publishers'
terms. They are included as hardware documentation, not relicensed under MIT.

## Returned diagnostic handoff (2026-10-27)

`handoff/20261027/returned/` preserves materials from [asdsadfghsdhs/1111](https://github.com/asdsadfghsdhs/1111/tree/2e567bc72ea6d8c947a50aef588e9fd0c4501975), commit `2e567bc72ea6d8c947a50aef588e9fd0c4501975`. Its original LICENSE and author notices remain in place. Vendor manuals/photos retain their original terms. This import adds diagnostic sources and evidence; the nine supplied production sources and original r17b package match the existing project. The receipt records one upstream prerequisites-document manifest discrepancy.
