`timescale 1ns/1ps
module tb_wireless_capture;
 reg clk=0,rstn=0;always #5 clk=~clk;
 reg [23:0] sdata=0;reg svalid=0,suser=0,slast=0;wire sready;
 wire [23:0] rgb;wire valid,user,last,ready;
 wire [31:0] outdata;wire [3:0] keep;wire outvalid,outuser,outlast;reg outready=0;
 integer sent=0,received=0,errors=0,cycles=0;reg [31:0] rng=32'h8124bc67;
 reg held=0;reg [31:0] held_data;reg held_user,held_last;
 reg [23:0] prefix[0:17];integer i;
 car_board_video_wrapper #(.VIDEO_WIDTH(1280),.VIDEO_HEIGHT(720)) dut(
  .aclk(clk),.aresetn(rstn),.us_echo(1'b0),.ir_l_raw(1'b1),.ir_r_raw(1'b1),
  .qei0_a(1'b0),.qei0_b(1'b0),.qei1_a(1'b0),.qei1_b(1'b0),
  .s_axi_awaddr(12'd0),.s_axi_awprot(3'd0),.s_axi_awvalid(1'b0),
  .s_axi_wdata(32'd0),.s_axi_wstrb(4'd0),.s_axi_wvalid(1'b0),.s_axi_bready(1'b1),
  .s_axi_araddr(12'd0),.s_axi_arprot(3'd0),.s_axi_arvalid(1'b0),.s_axi_rready(1'b1),
  .s_axis_tdata(sdata),.s_axis_tvalid(svalid),.s_axis_tready(sready),.s_axis_tuser(suser),.s_axis_tlast(slast),
  .m_axis_tdata(rgb),.m_axis_tvalid(valid),.m_axis_tready(ready),.m_axis_tuser(user),.m_axis_tlast(last));
 rgb24_to_axis32 adapter(.aclk(clk),.aresetn(rstn),.s_axis_tdata(rgb),.s_axis_tvalid(valid),
  .s_axis_tready(ready),.s_axis_tuser(user),.s_axis_tlast(last),.m_axis_tdata(outdata),
  .m_axis_tkeep(keep),.m_axis_tvalid(outvalid),.m_axis_tready(outready),.m_axis_tuser(outuser),.m_axis_tlast(outlast));
 always @(negedge clk) begin
  rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};outready=rng[0]|rng[1];
 end
 always @(posedge clk) if(rstn)begin
  cycles=cycles+1;
  if(held && (!outvalid || outdata!==held_data || outuser!==held_user || outlast!==held_last))begin
   errors=errors+1;$display("FAIL unstable AXIS under backpressure");
  end
  held=outvalid&&!outready;held_data=outdata;held_user=outuser;held_last=outlast;
  if(outvalid&&outready)begin
   if(outuser!==(received==0)||outlast!==(received%1280==1279)||keep!==4'b1111||outdata[31:24]!==0)begin
    errors=errors+1;$display("FAIL 720p BGR0/frame geometry at %d",received);
   end
   // Independent constant-field region outside overlays must remain RGB 112233.
   if(received%1280>1000 && received%1280<1200 && received/1280>350 && received/1280<600 && outdata!==32'h00112233)begin
    errors=errors+1;if(errors<10)$display("FAIL unchanged actual PL background %h at %d",outdata,received);
   end
   received=received+1;
  end
 end
 initial begin
  for(i=0;i<18;i=i+1)prefix[i]=0;
  prefix[0]=24'hd3a95c;prefix[1]=24'h010012;prefix[2]=24'h123456;prefix[3]=24'h000101;
  prefix[4]=24'h0013e8;prefix[17]=24'hffffff;
  for(i=0;i<17;i=i+1)prefix[17]=prefix[17]^prefix[i];
  repeat(5)@(negedge clk);rstn=1;
  for(sent=0;sent<1280*720;sent=sent+1)begin
   @(negedge clk);sdata=sent<18?prefix[sent]:24'h112233;svalid=1;suser=sent==0;slast=sent%1280==1279;
   do @(posedge clk);while(!sready);
   if(rng[2:0]==0)begin @(negedge clk);svalid=0;repeat(2)@(posedge clk);end
  end
  @(negedge clk);svalid=0;suser=0;slast=0;
  wait(received==1280*720);repeat(8)@(posedge clk);
  if(dut.header_errors!==0 || dut.osd_frame_errors!==0)begin errors=errors+1;$display("FAIL metadata/geometry errors");end
  if(errors==0)$display("TEST PASSED 720p actual wrapper + S2MM adapter pixels=%d cycles=%d",received,cycles);
  else $display("TEST FAILED errors=%d",errors);
  $finish;
 end
 initial begin #100000000;$display("TEST FAILED watchdog");$finish;end
endmodule
