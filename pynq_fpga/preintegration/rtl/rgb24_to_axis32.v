// Preserve the actual PL pixels for S2MM; one elastic register, II=1.
`resetall
`timescale 1ns/1ps
`default_nettype none
module rgb24_to_axis32(
 (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 aclk CLK", X_INTERFACE_PARAMETER="XIL_INTERFACENAME aclk, ASSOCIATED_BUSIF S_AXIS:M_AXIS, ASSOCIATED_RESET aresetn, FREQ_HZ 100000000" *) input wire aclk,
 (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 aresetn RST", X_INTERFACE_PARAMETER="XIL_INTERFACENAME aresetn, POLARITY ACTIVE_LOW" *) input wire aresetn,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS TDATA" *) input wire [23:0] s_axis_tdata,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS TVALID" *) input wire s_axis_tvalid,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS TREADY" *) output wire s_axis_tready,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS TUSER" *) input wire s_axis_tuser,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS TLAST" *) input wire s_axis_tlast,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 M_AXIS TDATA", X_INTERFACE_PARAMETER="XIL_INTERFACENAME M_AXIS, TDATA_NUM_BYTES 4, TUSER_WIDTH 1, HAS_TLAST 1, FREQ_HZ 100000000" *) output reg [31:0] m_axis_tdata,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 M_AXIS TKEEP" *) output wire [3:0] m_axis_tkeep,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 M_AXIS TVALID" *) output reg m_axis_tvalid,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 M_AXIS TREADY" *) input wire m_axis_tready,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 M_AXIS TUSER" *) output reg m_axis_tuser,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 M_AXIS TLAST" *) output reg m_axis_tlast
);
 assign m_axis_tkeep=4'b1111;
 assign s_axis_tready=!m_axis_tvalid||m_axis_tready;
 always @(posedge aclk) begin
  if(!aresetn) begin m_axis_tvalid<=0;m_axis_tdata<=0;m_axis_tuser<=0;m_axis_tlast<=0;end
  else if(s_axis_tready) begin
   m_axis_tvalid<=s_axis_tvalid;
   if(s_axis_tvalid) begin
    m_axis_tdata<={8'd0,s_axis_tdata};m_axis_tuser<=s_axis_tuser;m_axis_tlast<=s_axis_tlast;
   end
  end
 end
endmodule
`resetall
