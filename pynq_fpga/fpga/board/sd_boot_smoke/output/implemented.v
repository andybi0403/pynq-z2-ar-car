// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2026 Advanced Micro Devices, Inc. All Rights Reserved.
// --------------------------------------------------------------------------------
// Tool Version: Vivado v.2026.1 (win64) Build 6511674 Tue Jun 16 11:02:23 MDT 2026
// Date        : Sun Oct  4 21:48:25 2026
// Host        : BZY running 64-bit major release  (build 9200)
// Command     : write_verilog -force C:/Users/39909/Desktop/FPGA/pynq_fpga/fpga/board/sd_boot_smoke/output/implemented.v
// Design      : sd_boot_led
// Purpose     : This is a Verilog netlist of the current design or from a specific cell of the design. The output is an
//               IEEE 1364-2001 compliant Verilog HDL file that contains netlist information obtained from the input
//               design files.
// Device      : xc7z020clg400-1
// --------------------------------------------------------------------------------
`timescale 1 ps / 1 ps

(* ECO_CHECKSUM = "ce73cdfa" *) 
(* STRUCTURAL_NETLIST = "yes" *)
(* \DesignAttr:TELEMETRY_DATA  = "{\n  \"Design Characteristics Data\": {\n    \"Utilization Report\": {\n      \"BRAM\": {\n        \"Available\": \"140\",\n        \"Utilization\": \"0\"\n      },\n      \"BUFGCTRL\": {\n        \"Available\": \"32\",\n        \"Utilization\": \"0\"\n      },\n      \"DSP\": {\n        \"Available\": \"220\",\n        \"Utilization\": \"0\"\n      },\n      \"F7MUX\": {\n        \"Available\": \"26600\",\n        \"Utilization\": \"0\"\n      },\n      \"F8MUX\": {\n        \"Available\": \"13300\",\n        \"Utilization\": \"0\"\n      },\n      \"LUT\": {\n        \"Available\": \"53200\",\n        \"Utilization\": \"0\"\n      },\n      \"LUTAsLogic\": {\n        \"Available\": \"53200\",\n        \"Utilization\": \"0\"\n      },\n      \"LUTAsMem\": {\n        \"Available\": \"17400\",\n        \"Utilization\": \"0\"\n      },\n      \"MMCM\": {\n        \"Available\": \"4\",\n        \"Utilization\": \"0\"\n      },\n      \"PLL\": {\n        \"Available\": \"4\",\n        \"Utilization\": \"0\"\n      },\n      \"REG\": {\n        \"Available\": \"106400\",\n        \"Utilization\": \"0\"\n      }\n    }\n  },\n  \"Design Flow Data\": {\n    \"Design Data\": {\n      \"Design Mode\": \"Non-Project Flow\",\n      \"Top Methodology\": \"Verilog\"\n    },\n    \"Implementation\": {\n      \"Opt Design\": {\n        \"Run Time\": \"7 seconds\"\n      },\n      \"Place Design\": {\n        \"Run Time\": \"0.956000 seconds\"\n      },\n      \"Route Design\": {\n        \"Run Time\": \"16.490000 seconds\"\n      }\n    },\n    \"Synthesis\": {\n      \"Run Time\": \"24.763000 seconds\"\n    }\n  }\n}" *) 
module sd_boot_led
   (led);
  output [3:0]led;

  wire \<const0> ;
  wire \<const1> ;
  wire [3:0]led;

  GND GND
       (.G(\<const0> ));
  VCC VCC
       (.P(\<const1> ));
  OBUF \led_OBUF[0]_inst 
       (.I(\<const1> ),
        .O(led[0]));
  OBUF \led_OBUF[1]_inst 
       (.I(\<const0> ),
        .O(led[1]));
  OBUF \led_OBUF[2]_inst 
       (.I(\<const0> ),
        .O(led[2]));
  OBUF \led_OBUF[3]_inst 
       (.I(\<const0> ),
        .O(led[3]));
endmodule
