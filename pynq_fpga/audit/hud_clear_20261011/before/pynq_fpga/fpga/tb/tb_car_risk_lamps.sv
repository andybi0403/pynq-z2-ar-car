`timescale 1ns/1ps
module tb_car_risk_lamps;
 localparam W=640,H=120;
 reg clk=0,rst=1;always #5 clk=~clk;
 reg [23:0] sd=24'h112233;reg sv=0,su=0,sl=0;
 wire sr,mv,mu,ml;wire [23:0] md;wire [15:0] ferr;
 reg mr=0;reg [1:0] risk=0;reg stop=0,dv=1,vv=1;
 integer cycle=0,received=0,frame=0,x,y,errors=0,checks=0,active;
 integer ox,oy,idx,dx,dy;reg [23:0] want;reg blocked=0;reg [25:0] held;
 car_axis_osd #(.WIDTH(W),.HEIGHT(H)) dut(.clk(clk),.rst(rst),
 .s_axis_tdata(sd),.s_axis_tvalid(sv),.s_axis_tready(sr),.s_axis_tuser(su),.s_axis_tlast(sl),
 .m_axis_tdata(md),.m_axis_tvalid(mv),.m_axis_tready(mr),.m_axis_tuser(mu),.m_axis_tlast(ml),
 .state_risk_level(risk),.state_stop(stop),.state_locked(1'b0),.state_distance_valid(dv),
 .state_speed_valid(vv),.state_distance_mm(12'd1234),.state_speed_q16(32'd0),.frame_error_count(ferr));
 always @(negedge clk)begin cycle=cycle+1;mr=(cycle%7!=0&&cycle%7!=1);end
 always @(posedge clk)if(!rst)begin
  if(blocked && (!mv||{mu,ml,md}!==held))begin errors=errors+1;$display("FAIL held pixel");end
  blocked=mv&&!mr;held={mu,ml,md};
  if(mv&&mr)begin
   ox=received%W;oy=(received/W)%H;
   if(mu!==(ox==0&&oy==0)||ml!==(ox==W-1))begin errors=errors+1;$display("FAIL markers");end
   if(oy>=16&&oy<80&&ox>=W-264&&ox<W-24)begin
    idx=(ox-(W-264))/80;dx=ox-(W-224+idx*80);dy=oy-48;
    want=24'h101010;
    if(dx*dx+dy*dy<=24*24 && (idx==active||dx*dx+dy*dy>21*21))
     want=idx!=active?24'h686868:idx==0?24'h00d060:idx==1?24'hffd000:24'hff2020;
    checks=checks+1;
    if(md!==want)begin errors=errors+1;if(errors<10)$display("FAIL frame=%0d x=%0d y=%0d got=%h expected=%h",frame,ox,oy,md,want);end
   end
   received=received+1;
  end
 end
 initial begin
  repeat(4)@(negedge clk);rst=0;
  for(frame=0;frame<8;frame=frame+1)begin
   risk=frame<4?frame:0;stop=frame==4;dv=frame!=5;vv=frame!=6;
   active=(stop||!dv||!vv||risk>=2)?2:risk;
   for(y=0;y<H;y=y+1)for(x=0;x<W;x=x+1)begin
    @(negedge clk);sv=1;su=(x==0&&y==0);sl=(x==W-1);
    if(y==16&&x==0)begin risk=3;stop=1;dv=0;vv=0;end // live changes wait for next SOF
    do @(posedge clk);while(!sr);
    if((x+y)%31==0)begin @(negedge clk);sv=0;@(posedge clk);end
   end
   @(negedge clk);sv=0;
   while(received<(frame+1)*W*H)@(negedge clk);
  end
  if(ferr!=0)errors=errors+1;
  if(errors==0)$display("TEST PASSED (%0d independent circle checks, all 8 states, stalls and frame latch)",checks);
  else $display("TEST FAILED (%0d errors)",errors);
  $finish;
 end
 initial begin #30000000;$display("TEST FAILED watchdog");$finish;end
endmodule
