`timescale 1ns/1ps
module tb_car_board_video_wrapper;
 reg clk=0,aresetn=0;
 always #5 clk=~clk;
 reg us_echo=0,ir_l_raw=1,ir_r_raw=1,q0a=0,q0b=0,q1a=0,q1b=0;
 wire us_trig;
 wire qei_oe_n;
 reg [11:0] awaddr=0,araddr=0;reg [2:0] awprot=0,arprot=0;
 reg awvalid=0,wvalid=0,arvalid=0;reg [31:0] wdata=0;reg [3:0] wstrb=15;
 wire awready,wready,bvalid,arready,rvalid;reg bready=0,rready=0;
 wire [1:0] bresp,rresp;wire [31:0] rdata;
 reg [23:0] sdata=0;reg svalid=0,suser=0,slast=0;wire sready;
 wire [23:0] mdata;wire mvalid,muser,mlast;reg mready=1;
 integer errors=0,checks=0;
 integer age_case;reg [63:0] age_now,age_stamp;reg [31:0] rd;reg [23:0] held_data;reg held_user,held_last;
 integer capture_file=0,captured=0,j;reg [23:0] prefix[0:17];reg [63:0] reception_ticks;

 car_board_video_wrapper dut(
  .aclk(clk),.aresetn(aresetn),.us_echo(us_echo),.us_trig(us_trig),
  .ir_l_raw(ir_l_raw),.ir_r_raw(ir_r_raw),.qei0_a(q0a),.qei0_b(q0b),.qei1_a(q1a),.qei1_b(q1b),
  .qei_oe_n(qei_oe_n),
  .s_axi_awaddr(awaddr),.s_axi_awprot(awprot),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
  .s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
  .s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(bready),
  .s_axi_araddr(araddr),.s_axi_arprot(arprot),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
  .s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(rready),
  .s_axis_tdata(sdata),.s_axis_tvalid(svalid),.s_axis_tready(sready),.s_axis_tuser(suser),.s_axis_tlast(slast),
  .m_axis_tdata(mdata),.m_axis_tvalid(mvalid),.m_axis_tready(mready),.m_axis_tuser(muser),.m_axis_tlast(mlast));

 task check(input string n,input bit ok);begin checks++;if(!ok)begin errors++;$display("[FAIL] %s",n);end end endtask
 task rdreg(input [11:0] a,output [31:0] d);begin
  @(negedge clk);araddr=a;arvalid=1;rready=0;do @(posedge clk);while(!arready);
  @(negedge clk);arvalid=0;rready=1;do @(posedge clk);while(!rvalid);d=rdata;@(negedge clk);rready=0;
 end endtask

 always @(posedge clk) if(capture_file!=0&&mvalid&&mready) begin
  $fdisplay(capture_file,"%06x",mdata);captured=captured+1;
  if(captured%640==1) check("full-frame SOF geometry",muser===(captured==1));
  if(captured%640==0) check("full-frame EOL geometry",mlast===1'b1);
 end
 task frame(input integer number);begin
  if(number<3) reception_ticks=dut.live_ticks;
  prefix[0]=24'hd3a95c;prefix[1]=24'h010012;
  prefix[2]=number==1?24'h345678:24'h345679;prefix[3]=number==1?24'habcd12:24'habce12;
  prefix[4]=number==1?24'h0373e8:24'h0072ee;
  prefix[5]=number==1?24'hff0000:24'h070000;prefix[6]=number==1?24'h0000ff:0;
  prefix[7]=number==1?24'hfe0000:24'h2a0000;prefix[8]=number==1?24'hffffff:0;
  prefix[9]=number==1?24'h00ffff:0;prefix[10]=number==1?24'h030000:24'h630000;
  prefix[11]=0;prefix[12]=0;prefix[13]=number==1?24'h000201:24'h000e13;
  prefix[14]=reception_ticks[23:0];prefix[15]=reception_ticks[47:24];prefix[16]={8'd0,reception_ticks[63:48]};
  prefix[17]=24'hffffff;for(j=0;j<17;j=j+1)prefix[17]=prefix[17]^prefix[j];
  capture_file=$fopen($sformatf("display_chain_f%0d.rgb",number),"w");captured=0;
  for(j=0;j<640*480;j=j+1) begin
   @(negedge clk);
   sdata=j<18?prefix[j]:
       number==1&&j%640>=220&&j%640<410&&j/640>=165&&j/640<300?24'hf0f0f0:24'h112233;
   svalid=1;suser=j==0;slast=j%640==639;
   do @(posedge clk);while(!sready);
   if(j==1000) begin
    // Latest safety changes after SOF must not change this frame's latched
    // border; its historical values are carried by the embedded prefix.
    force dut.risk_level=2'd0;force dut.risk_stop=1'b0;
    force dut.speed_q16=32'h7fffffff;force dut.distance_mm=12'd1;
   end
  end
  @(negedge clk);svalid=0;suser=0;slast=0;
  wait(captured==640*480);@(negedge clk);$fclose(capture_file);capture_file=0;
  rdreg('h2a0,rd);check("decoded frame ID via AXI",rd===(number==1?32'h12345678:32'h12345679));
  rdreg('h2a4,rd);check("snapshot epoch and fresh metadata via AXI",rd===(number==1?32'habcd0003:number==4?32'habce0001:32'habce0003));
  rdreg('h2a8,rd);check("reception timestamp low via AXI",rd===reception_ticks[31:0]);
  rdreg('h2ac,rd);check("reception timestamp high via AXI",rd===reception_ticks[63:32]);
  rdreg('h2b0,rd);check("metadata valid without prefix errors",rd===0);
  rdreg('h2b8,rd);check("accepted metadata SOF count",rd===number);
  rdreg('h2c0,rd);check("actual OSD acceptance follows reception",rd>=reception_ticks[31:0]&&(number==4?rd<=dut.live_ticks[31:0]:rd<dut.live_ticks[31:0]));
  rdreg('h2c4,rd);check("OSD SOF high timestamp through AXI",rd===reception_ticks[63:32]);
 end endtask

 task stalled_sof_freshness;begin
  reception_ticks=dut.live_ticks;
  for(j=0;j<18;j=j+1)prefix[j]=0;
  prefix[0]=24'hd3a95c;prefix[1]=24'h010012;prefix[2]=1;prefix[3]=24'h000100;
  prefix[4]=24'h0013e8;prefix[14]=reception_ticks[23:0];prefix[15]=reception_ticks[47:24];
  prefix[16]={8'd0,reception_ticks[63:48]};prefix[17]=24'hffffff;
  for(j=0;j<17;j=j+1)prefix[17]=prefix[17]^prefix[j];
  // Fill/block the downstream base stage so the front SOF is accepted first.
  // Capture is disabled for this directed fixture; reset flushes it afterwards.
  force dut.base_ready=1'b0;force dut.osd.m_axis_tvalid=1'b1;
  for(j=0;j<18;j=j+1)begin
   @(negedge clk);sdata=prefix[j];svalid=1;suser=j==0;slast=0;
   do @(posedge clk);while(!sready);
  end
  @(negedge clk);svalid=0;suser=0;
  wait(dut.front_valid&&dut.front_user);
  check("front SOF accepted fresh before stall",dut.front_overlay.frame_distance_valid===1'b1);
  force dut.live_ticks=reception_ticks+64'd20_000_001;
  repeat(5)@(negedge clk);
  release dut.base_ready;release dut.osd.m_axis_tvalid;
  repeat(8)@(negedge clk);
  check("all historical overlays share accepted SOF validity",dut.osd.active_distance_valid===1'b1);
  release dut.live_ticks;
  aresetn=0;repeat(5)@(negedge clk);aresetn=1;repeat(8)@(negedge clk);
 end endtask

 initial begin
  repeat(5) begin @(posedge clk); check("QEI shifter disabled during reset",qei_oe_n===1'b1); end
  @(negedge clk);aresetn=1;repeat(8)@(posedge clk);
  check("QEI shifter enabled after reset",qei_oe_n===1'b0);
  // Independent 64-bit reference, exact window boundary and low-word carry.
  check("fresh equality",dut.recent_frame(64'd0,64'd0));
  check("last valid tick",dut.recent_frame(64'd19999999,64'd0));
  check("expiry equality",!dut.recent_frame(64'd20000000,64'd0));
  check("low word wrap",dut.recent_frame(64'h100000010,64'hfffffff0));
  check("future high-word overflow",!dut.recent_frame(64'd0,64'hffffffffffffffff));
  check("far stale high word",!dut.recent_frame(64'h200000000,64'd0));
  for(age_case=0;age_case<2000;age_case=age_case+1)begin
   age_stamp={$urandom,$urandom};
   case(age_case%4)
    0:age_now=age_stamp+64'd19999999;
    1:age_now=age_stamp+64'd20000000;
    2:age_now=age_stamp-64'd1;
    3:age_now={$urandom,$urandom};
   endcase
   check("split comparator versus 64bit reference",
    dut.recent_frame(age_now,age_stamp)===(age_now>=age_stamp&&(age_now-age_stamp)<64'd20000000));
  end

  rdreg('h000,rd);check("production ID through wrapper",rd===32'hc4251009);

  // One SOF/EOL sample proves that the production OSD, not a placeholder,
  // is connected in the AXIS path.  The fail-safe default may recolour it.
  @(negedge clk);mready=0;sdata=24'h123456;suser=1;slast=1;svalid=1;
  do @(posedge clk);while(!sready);@(negedge clk);svalid=0;suser=0;slast=0;
  do @(posedge clk);while(!mvalid);
  check("SOF forwarded",muser===1'b1);check("EOL forwarded",mlast===1'b1);
  held_data=mdata;held_user=muser;held_last=mlast;
  repeat(4)begin @(posedge clk);
   check("valid held under backpressure",mvalid===1'b1);
   check("payload stable under backpressure",mdata===held_data && muser===held_user && mlast===held_last);
  end
  @(negedge clk);mready=1;@(posedge clk);@(negedge clk);
  check("sample consumed",mvalid===1'b0);
  @(negedge clk);aresetn=0;repeat(5)@(negedge clk);aresetn=1;repeat(8)@(negedge clk);
  stalled_sof_freshness();
  force dut.risk_level=2'd2;force dut.risk_stop=1'b1;
  force dut.car_valid=1'b1;force dut.car_locked=1'b1;force dut.car_fault=16'h1234;
  frame(1);
  force dut.risk_level=2'd0;force dut.risk_stop=1'b0;
  force dut.car_locked=1'b0;force dut.car_fault=16'd0;
  frame(2);
  force dut.live_ticks=reception_ticks+64'd20_000_001;
  rdreg('h2a4,rd);check("old historical display expires",rd===32'habce0001);
  force dut.live_ticks=reception_ticks-64'd1;
  rdreg('h2a4,rd);check("future reception cannot become fresh",rd===32'habce0001);
  rdreg('h2bc,rd);check("future display age is saturated",rd===32'hffffffff);
  force dut.live_ticks=reception_ticks+64'h100000001;
  rdreg('h2bc,rd);check("64-bit age cannot wrap into freshness",rd===32'hffffffff);
  release dut.live_ticks;
  frame(3);
  rdreg('h2b4,rd);check("repeated VDMA frame keeps original identity",rd===1);
  force dut.live_ticks=reception_ticks+64'd20_000_001;
  frame(4);
  release dut.live_ticks;
  if(errors==0)$display("TEST PASSED (%0d checks)",checks);else $display("TEST FAILED (%0d errors)",errors);$finish;
 end
 initial begin #200000000;$display("TEST FAILED watchdog");$finish;end
endmodule
