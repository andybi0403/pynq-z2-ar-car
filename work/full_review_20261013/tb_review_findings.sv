`timescale 1ns/1ps
module tb_review_findings;
reg clk=0,rst=1,echo=0,qa=0,qb=0;
always #5 clk=~clk;
reg [31:0] ticks=0;always @(posedge clk) if(rst)ticks<=0;else ticks<=ticks+1;
wire trig,valid,update;wire [31:0] ts,data;wire [15:0] seq,err;
car_ultrasonic us(.clk(clk),.rst(rst),.enable(1'b1),.now_ticks(ticks),.sample_ts(ts),.echo(echo),.trig(trig),
.cfg_period(32'd20),.cfg_max_echo(32'd5000),.cfg_trig_clk(32'd2),.samp_data(data),.samp_valid(valid),.samp_update(update),.err_cnt(err),.samp_seq(seq));
wire stop;wire[1:0]level;
car_perception_top top(.clk(clk),.rst(rst),.us_echo(1'b0),.ir_l_raw(1'b1),.ir_r_raw(1'b1),
.qei0_a(qa),.qei0_b(qb),.qei1_a(1'b0),.qei1_b(1'b0),.risk_stop_o(stop),.risk_level_o(level),
.osd_errors_i(16'd0),.osd_frames_i(32'd0),.display_frame_id_i(32'd0),.display_frame_state_i(32'd0),
.display_frame_ticks_i(64'd0),.display_frame_sof_i(64'd0),.display_header_errors_i(16'd0),.display_repeats_i(32'd0),.display_tag_count_i(32'd0),.display_frame_age_i(32'd0),
.s_axil_awaddr(12'd0),.s_axil_awprot(3'd0),.s_axil_awvalid(1'b0),.s_axil_wdata(32'd0),.s_axil_wstrb(4'd0),.s_axil_wvalid(1'b0),.s_axil_bready(1'b1),
.s_axil_araddr(12'd0),.s_axil_arprot(3'd0),.s_axil_arvalid(1'b0),.s_axil_rready(1'b1));
integer mixed=0;reg [31:0]prev_ts=0;reg [15:0]prev_seq=0;reg prev_valid=0;
always @(negedge clk)begin
 if(!rst && prev_valid && valid && seq==prev_seq && ts!=prev_ts)begin mixed=mixed+1;$display("REPRO_US_MIXED_BATCH old_seq=%0d new_ts=%0d old_data=%0d",seq,ts,data);end
 prev_ts=ts;prev_seq=seq;prev_valid=valid;
end
task pulse(input integer width);begin
 @(posedge trig);@(negedge trig);repeat(5)@(negedge clk);echo=1;repeat(width)@(negedge clk);echo=0;@(posedge update);@(negedge clk);
end endtask
initial begin
 repeat(6)@(negedge clk);rst=0;
 force top.q0_scale_cfg=32'd5362;force top.q1_scale_cfg=32'd5362;
 force top.q0_zero_cfg=32'd100;force top.q1_zero_cfg=32'd100;
 force top.us_data=32'd1000;force top.us_valid=1'b1;force top.us_ts=0;
 force top.command_valid=1'b1;force top.command_forward=1'b0;force top.command_ts=0;
 repeat(10)@(negedge clk);qa=1;qb=1;
 repeat(5200)@(negedge clk);
 if(top.q0_info[11:4]==0 || !top.odo0_fault || !top.q0_valid || stop || level!=0)$fatal(1,"risk repro assumptions not met info=%h fault=%b valid=%b stop=%b level=%d",top.q0_info,top.odo0_fault,top.q0_valid,stop,level);
 $display("REPRO_PL_GREEN_WITH_QEI_FAULT illegal=%0d odometry_fault=%b risk_stop=%b",top.q0_info[11:4],top.odo0_fault,stop);
 pulse(600);pulse(1200);
 if(mixed<1)$fatal(1,"timestamp defect not reproduced");
 $display("TEST PASSED (2 checks) -- known defects reproduced, not product acceptance");$finish;
end
initial begin #2000000;$fatal(1,"review repro watchdog");end
endmodule
