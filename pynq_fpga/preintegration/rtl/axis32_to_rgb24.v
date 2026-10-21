// Pre-integration adapter: strip the unused fourth byte from a 32-bit VDMA
// beat while preserving AXI4-Stream backpressure and frame sidebands.
// Pixel lane order is deliberately not interpreted here; verify RGB/BGR on
// hardware with solid color bars before connecting the production OSD.
`resetall
`timescale 1ns/1ps
`default_nettype none
module axis32_to_rgb24(
 (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK", X_INTERFACE_PARAMETER = "XIL_INTERFACENAME aclk, ASSOCIATED_BUSIF S_AXIS:M_AXIS, ASSOCIATED_RESET aresetn, FREQ_HZ 100000000" *) input wire aclk,
 (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST", X_INTERFACE_PARAMETER = "XIL_INTERFACENAME aresetn, POLARITY ACTIVE_LOW" *) input wire aresetn,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TDATA" *) input wire [31:0] s_axis_tdata,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TKEEP" *) input wire [3:0] s_axis_tkeep,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TVALID" *) input wire s_axis_tvalid,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TREADY" *) output wire s_axis_tready,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TUSER" *) input wire s_axis_tuser,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TLAST" *) input wire s_axis_tlast,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TDATA" *) output reg [23:0] m_axis_tdata,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TVALID" *) output reg m_axis_tvalid,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TREADY" *) input wire m_axis_tready,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TUSER" *) output reg m_axis_tuser,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TLAST" *) output reg m_axis_tlast,
 output reg [15:0] format_error_count
);
 wire take_output = !m_axis_tvalid || m_axis_tready;
 assign s_axis_tready = take_output;

 always @(posedge aclk) begin
  if(!aresetn) begin
   m_axis_tdata <= 24'd0;
   m_axis_tvalid <= 1'b0;
   m_axis_tuser <= 1'b0;
   m_axis_tlast <= 1'b0;
   format_error_count <= 16'd0;
  end else if(take_output) begin
   m_axis_tvalid <= s_axis_tvalid;
   if(s_axis_tvalid) begin
    m_axis_tdata <= s_axis_tdata[23:0];
    m_axis_tuser <= s_axis_tuser;
    m_axis_tlast <= s_axis_tlast;
    if(s_axis_tkeep[2:0] != 3'b111 && format_error_count != 16'hffff)
     format_error_count <= format_error_count + 1'b1;
   end
  end
 end
endmodule
`resetall
