`timescale 1ns/1ps
module tb_car_front_overlay;
 reg clk=0,rst=1;always #5 clk=~clk;
 reg [23:0] sd=0;reg sv=0,su=0,sl=0;wire sr;
 wire [23:0] md;wire mv,mu,ml;reg mr=1;
 reg state_valid=1,dv=1,stop=0;reg [11:0] distance=0;reg [1:0] risk=0;
 integer errors=0,checks=0,frame,j,received=0,output_frame=0,fd[0:5];
 integer cycles=0,accepted=0,stalls=0,gaps=0;reg capture=0,random_ready=0;
 reg was_stalled=0;reg [25:0] held;reg [31:0] rng=32'h13579bdf;
 car_axis_front_overlay dut(.clk(clk),.rst(rst),.s_axis_tdata(sd),.s_axis_tvalid(sv),
  .s_axis_tready(sr),.s_axis_tuser(su),.s_axis_tlast(sl),.m_axis_tdata(md),
  .m_axis_tvalid(mv),.m_axis_tready(mr),.m_axis_tuser(mu),.m_axis_tlast(ml),
  .state_valid(state_valid),.state_distance_valid(dv),.state_distance_mm(distance),
  .state_risk_level(risk),.state_stop(stop));
 task check(input string name,input bit ok);begin checks++;if(!ok)begin errors++;$display("[FAIL] %s",name);end end endtask
 function [23:0] picture(input integer f,xx,yy);
  begin case(f)
   0:picture=24'h112233;
   1:picture=xx>=220&&xx<410&&yy>=165&&yy<300?24'hf0f0f0:24'h182030;
   2:picture=((xx*3+yy*5)&255)*24'h010101;
   3:picture=((xx/8+yy/8)&1)?24'hffffff:0;
   4:picture=(((xx*17+yy*31)&255)<<16)|(((xx*11+yy*7)&255)<<8)|((xx*5+yy*23)&255);
   default:picture=xx==320||yy==240?24'hffffff:0;
  endcase end
 endfunction
 always @(negedge clk)begin
  rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
  if(random_ready)mr=rng[0]||rng[4];
 end
 always @(posedge clk)begin
  if(rst)was_stalled=0;
  else begin
   if(was_stalled)check("output stable across stall",mv&&{mu,ml,md}===held);
   was_stalled=mv&&!mr;held={mu,ml,md};
   if(capture)begin
    cycles++;if(sv&&sr)accepted++;if(!sr)stalls++;if(!sv)gaps++;
    if(mv&&mr)begin
     check("SOF exactly at first pixel",mu===(received==0));
     check("EOL exactly at row end",ml===(received%640==639));
     $fdisplay(fd[output_frame],"%06x",md);
     received++;
     if(received==640*480)begin received=0;output_frame++;end
    end
   end
  end
 end
 task send(input [23:0] data,input bit user,last);begin
  @(negedge clk);sd=data;su=user;sl=last;sv=1;
  do @(posedge clk);while(!sr);
 end endtask
 initial begin
  repeat(5)@(negedge clk);rst=0;
  // Reset while a valid output is stalled, then recover without stale pixels.
  mr=0;send(24'hffffff,1,0);send(24'h000000,0,0);send(24'hffffff,0,0);
  repeat(5)@(negedge clk);check("pending output reached",mv);
  rst=1;sv=0;repeat(3)@(negedge clk);check("reset drops pending output",!mv);
  rst=0;mr=1;
  for(frame=0;frame<6;frame++)fd[frame]=$fopen($sformatf("front_f%0d.rgb",frame),"w");
  capture=1;
  for(frame=0;frame<6;frame++)begin
   random_ready=frame!=0;
   state_valid=frame!=5;dv=frame!=4;stop=frame==3;
   risk=frame==1?2:frame==2?1:0;
   case(frame)0:distance=0;1:distance=1234;2:distance=4095;3:distance=999;4:distance=2500;5:distance=1800;endcase
   for(j=0;j<640*480;j++)begin
    if(frame!=0&&rng[8:6]==0)begin @(negedge clk);sv=0;repeat(2)@(posedge clk);end
    send(picture(frame,j%640,j/640),j==0,j%640==639);
    // Change every live state after SOF, including during output backpressure.
    if(j==20)begin state_valid=0;dv=0;distance=17;risk=3;stop=1;end
   end
   if(frame==0)begin #1;check("uninterrupted one-pixel-per-clock input",accepted==640*480&&cycles<=640*480+1);end
  end
  @(negedge clk);sv=0;su=0;sl=0;
  wait(output_frame==6);@(negedge clk);capture=0;
  for(frame=0;frame<6;frame++)$fclose(fd[frame]);
  check("random stalls exercised",stalls>1000);check("source bubbles exercised",gaps>1000);
  check("exact frame/pixel count",accepted==6*640*480&&received==0);
  $display("FRONT_STREAM_METRICS pixels=%0d cycles=%0d stalls=%0d bubbles=%0d",accepted,cycles,stalls,gaps);
  if(errors==0)$display("TEST PASSED (%0d checks)",checks);else $display("TEST FAILED (%0d errors)",errors);
  $finish;
 end
 initial begin #100000000;$display("TEST FAILED watchdog");$finish;end
endmodule
