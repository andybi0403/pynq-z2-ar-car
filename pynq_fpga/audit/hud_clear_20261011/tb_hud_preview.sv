`timescale 1ns/1ps
module tb_hud_preview;
 localparam W=1280,H=720,N=W*H;
 reg clk=0,rst=1;always #5 clk=~clk;
 reg [23:0] sd;reg sv=0,su=0,sl=0;wire sr;
 wire [23:0] fd,td,md;wire fv,fu,fl,fr,tv,tu,tl,tr,mv,mu,ml;
 wire [15:0] errors;wire [31:0] frames;
 reg [23:0] camera[0:N-1];integer count=0,fh=0,k,f;
 car_axis_front_overlay #(.WIDTH(W),.HEIGHT(H)) front(.clk(clk),.rst(rst),.s_axis_tdata(sd),.s_axis_tvalid(sv),.s_axis_tready(sr),.s_axis_tuser(su),.s_axis_tlast(sl),.m_axis_tdata(fd),.m_axis_tvalid(fv),.m_axis_tready(fr),.m_axis_tuser(fu),.m_axis_tlast(fl),.state_valid(1'b0),.state_distance_valid(1'b0),.state_distance_mm(12'd0),.state_risk_level(2'd3),.state_stop(1'b1));
 car_axis_osd #(.WIDTH(W),.HEIGHT(H)) osd(.clk(clk),.rst(rst),.s_axis_tdata(fd),.s_axis_tvalid(fv),.s_axis_tready(fr),.s_axis_tuser(fu),.s_axis_tlast(fl),.m_axis_tdata(td),.m_axis_tvalid(tv),.m_axis_tready(tr),.m_axis_tuser(tu),.m_axis_tlast(tl),.state_risk_level(2'd3),.state_stop(1'b1),.state_locked(1'b1),.state_distance_valid(1'b0),.state_speed_valid(1'b0),.state_distance_mm(12'd0),.state_speed_q16(32'd0),.frame_error_count(errors));
 car_axis_status_osd #(.WIDTH(W),.HEIGHT(H)) status(.clk(clk),.rst(rst),.s_axis_tdata(td),.s_axis_tvalid(tv),.s_axis_tready(tr),.s_axis_tuser(tu),.s_axis_tlast(tl),.m_axis_tdata(md),.m_axis_tvalid(mv),.m_axis_tready(1'b1),.m_axis_tuser(mu),.m_axis_tlast(ml),.state_displacement_q16(64'd0),.state_path_q16(64'd0),.state_odometry_valid(1'b0),.state_reasons(16'h030a),.state_car_valid(1'b0),.state_car_locked(1'b1),.state_car_fault(16'd0),.state_speed_q16(32'd0),.state_speed_valid(1'b0),.committed_frames(frames));
 always @(posedge clk) if(!rst&&mv)begin
   if(mu!==(count%N==0)||ml!==(count%W==W-1))$fatal(1,"preview sideband mismatch");
   if(count>=N)$fwrite(fh,"%06x\n",md);
   count=count+1;
 end
 initial begin
  $readmemh("camera_input.rgb",camera);fh=$fopen("preview.rgb","w");
  repeat(5)@(negedge clk);rst=0;
  for(f=0;f<2;f=f+1)for(k=0;k<N;k=k+1)begin
   @(negedge clk);sv=1;sd=camera[k];su=k==0;sl=k%W==W-1;
   do @(posedge clk);while(!sr);
  end
  @(negedge clk);sv=0;while(count<2*N)@(negedge clk);
  if(errors!=0||frames!=2)$fatal(1,"preview frame count/error");
  $fclose(fh);$display("TEST PASSED HUD_PREVIEW pixels=%0d",N);$finish;
 end
 initial begin #30000000;$fatal(1,"preview watchdog");end
endmodule
