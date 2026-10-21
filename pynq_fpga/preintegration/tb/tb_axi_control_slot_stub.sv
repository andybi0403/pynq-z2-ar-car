`timescale 1ns/1ps
module tb_axi_control_slot_stub;
 reg clk=0,aresetn=0;always #5 clk=~clk;
 reg [11:0] awaddr=0;reg [2:0] awprot=0;reg awvalid=0;wire awready;
 reg [31:0] wdata=0;reg [3:0] wstrb=0;reg wvalid=0;wire wready;wire [1:0] bresp;wire bvalid;reg bready=0;
 reg [11:0] araddr=0;reg [2:0] arprot=0;reg arvalid=0;wire arready;wire [31:0] rdata;wire [1:0] rresp;wire rvalid;reg rready=0;
 integer checks=0,failures=0;
 axi_control_slot_stub dut(.aclk(clk),.aresetn(aresetn),.s_axi_awaddr(awaddr),.s_axi_awprot(awprot),.s_axi_awvalid(awvalid),.s_axi_awready(awready),.s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wvalid(wvalid),.s_axi_wready(wready),.s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(bready),.s_axi_araddr(araddr),.s_axi_arprot(arprot),.s_axi_arvalid(arvalid),.s_axi_arready(arready),.s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(rready));
 task check;input cond;input [255:0] msg;begin checks=checks+1;if(!cond)begin failures=failures+1;$display("[FAIL] %s",msg);end end endtask
 task read_reg;input [11:0] addr;input [31:0] expected;begin
  @(negedge clk);araddr=addr;arvalid=1;rready=0;@(posedge clk);#1;check(arready==0,"read accepted");
  @(negedge clk);arvalid=0;repeat(2)begin @(posedge clk);#1;check(rvalid&&rdata==expected,"read held under backpressure");end
  @(negedge clk);rready=1;@(posedge clk);#1;@(negedge clk);rready=0;check(!rvalid,"read response consumed");
 end endtask
 task write_split;input [11:0] addr;input [31:0] data;input [3:0] strb;input data_first;begin
  if(data_first)begin @(negedge clk);wdata=data;wstrb=strb;wvalid=1;@(posedge clk);@(negedge clk);wvalid=0;repeat(2)@(posedge clk);end
  else begin @(negedge clk);awaddr=addr;awvalid=1;@(posedge clk);@(negedge clk);awvalid=0;repeat(2)@(posedge clk);end
  @(negedge clk);if(data_first)begin awaddr=addr;awvalid=1;end else begin wdata=data;wstrb=strb;wvalid=1;end
  @(posedge clk);#1;@(negedge clk);awvalid=0;wvalid=0;
  repeat(2)begin @(posedge clk);#1;check(bvalid&&bresp==0,"write response held");end
  @(negedge clk);bready=1;@(posedge clk);#1;@(negedge clk);bready=0;check(!bvalid,"write response consumed");
 end endtask
 initial begin
  repeat(3)@(posedge clk);aresetn=1;
  read_reg(12'h000,32'h534c4f54);read_reg(12'h004,32'ha55a5a5a);
  write_split(12'h004,32'h11223344,4'hf,0);read_reg(12'h004,32'h11223344);
  write_split(12'h004,32'haa00cc00,4'b1010,1);read_reg(12'h004,32'haa22cc44);
  write_split(12'h008,32'hffffffff,4'hf,0);read_reg(12'h004,32'haa22cc44);read_reg(12'h008,32'd0);
  aresetn=0;@(posedge clk);#1;check(!bvalid&&!rvalid,"reset clears response valid");
  if(failures==0)$display("TEST PASSED (%0d checks)",checks);else $display("TEST FAILED (%0d/%0d)",failures,checks);$finish;
 end
 initial begin #100000;$display("TEST FAILED (watchdog)");$finish;end
endmodule

