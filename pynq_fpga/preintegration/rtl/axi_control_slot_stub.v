// Deliberately non-production AXI-Lite endpoint for the task 7 framework.
// ID 0x534c4f54 spells "SLOT" and cannot pass the production version gate.
`resetall
`timescale 1ns/1ps
`default_nettype none
module axi_control_slot_stub(
 (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK", X_INTERFACE_PARAMETER = "XIL_INTERFACENAME aclk, ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET aresetn, FREQ_HZ 100000000" *) input wire aclk,
 (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST", X_INTERFACE_PARAMETER = "XIL_INTERFACENAME aresetn, POLARITY ACTIVE_LOW" *) input wire aresetn,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWADDR", X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXI, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 12, FREQ_HZ 100000000" *) input wire [11:0] s_axi_awaddr,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWPROT" *) input wire [2:0] s_axi_awprot,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *) input wire s_axi_awvalid,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *) output wire s_axi_awready,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WDATA" *) input wire [31:0] s_axi_wdata,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *) input wire [3:0] s_axi_wstrb,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WVALID" *) input wire s_axi_wvalid,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WREADY" *) output wire s_axi_wready,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *) output wire [1:0] s_axi_bresp,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *) output reg s_axi_bvalid,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *) input wire s_axi_bready,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *) input wire [11:0] s_axi_araddr,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *) input wire [2:0] s_axi_arprot,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *) input wire s_axi_arvalid,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *) output wire s_axi_arready,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RDATA" *) output reg [31:0] s_axi_rdata,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RRESP" *) output wire [1:0] s_axi_rresp,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RVALID" *) output reg s_axi_rvalid,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RREADY" *) input wire s_axi_rready
);
 reg aw_pending,w_pending;
 reg [11:0] awaddr_q;
 reg [31:0] wdata_q,scratch;
 reg [3:0] wstrb_q;
 wire aw_take=s_axi_awvalid&&s_axi_awready;
 wire w_take=s_axi_wvalid&&s_axi_wready;
 wire write_fire=!s_axi_bvalid&&(aw_pending||aw_take)&&(w_pending||w_take);
 wire [11:0] write_addr=aw_pending?awaddr_q:s_axi_awaddr;
 wire [31:0] write_data=w_pending?wdata_q:s_axi_wdata;
 wire [3:0] write_strb=w_pending?wstrb_q:s_axi_wstrb;
 assign s_axi_awready=!aw_pending&&!s_axi_bvalid;
 assign s_axi_wready=!w_pending&&!s_axi_bvalid;
 assign s_axi_bresp=2'b00;
 assign s_axi_arready=!s_axi_rvalid;
 assign s_axi_rresp=2'b00;
 function [31:0] merge_bytes;
  input [31:0] oldv,inputv;input [3:0] strb;
  begin merge_bytes=oldv;if(strb[0])merge_bytes[7:0]=inputv[7:0];if(strb[1])merge_bytes[15:8]=inputv[15:8];if(strb[2])merge_bytes[23:16]=inputv[23:16];if(strb[3])merge_bytes[31:24]=inputv[31:24];end
 endfunction
 wire unused_prot=&{1'b0,s_axi_awprot,s_axi_arprot};
 always @(posedge aclk) begin
  if(!aresetn) begin
   aw_pending<=0;w_pending<=0;awaddr_q<=0;wdata_q<=0;wstrb_q<=0;
   scratch<=32'ha55a5a5a;s_axi_bvalid<=0;s_axi_rvalid<=0;s_axi_rdata<=0;
  end else begin
   if(s_axi_bvalid&&s_axi_bready)s_axi_bvalid<=0;
   if(aw_take)begin aw_pending<=1;awaddr_q<=s_axi_awaddr;end
   if(w_take)begin w_pending<=1;wdata_q<=s_axi_wdata;wstrb_q<=s_axi_wstrb;end
   if(write_fire)begin
    aw_pending<=0;w_pending<=0;s_axi_bvalid<=1;
    if(write_addr[11:0]==12'h004)scratch<=merge_bytes(scratch,write_data,write_strb);
   end
   if(s_axi_rvalid&&s_axi_rready)s_axi_rvalid<=0;
   if(s_axi_arvalid&&s_axi_arready)begin
    s_axi_rvalid<=1;
    case(s_axi_araddr[11:0])
     12'h000:s_axi_rdata<=32'h534c4f54;
     12'h004:s_axi_rdata<=scratch;
     default:s_axi_rdata<=32'd0;
    endcase
   end
  end
 end
endmodule
`resetall

