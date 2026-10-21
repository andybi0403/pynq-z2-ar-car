`timescale 1ns/1ps
module tb_car_review_regressions;
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
integer checks=0; integer mixed=0;reg [31:0]prev_ts=0;reg [15:0]prev_seq=0;reg prev_valid=0;reg [31:0] prev_data=0;
always @(negedge clk)begin
 if(!rst && seq==prev_seq && (ts!=prev_ts || data!=prev_data || valid!=prev_valid))begin mixed=mixed+1;$display("REPRO_US_MIXED_BATCH old_seq=%0d new_ts=%0d old_data=%0d",seq,ts,data);end
 prev_ts=ts;prev_seq=seq;prev_valid=valid;prev_data=data;
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
 if(top.q0_info[11:4]==0 || !top.odo0_fault || !top.q0_valid)
  $fatal(1,"real illegal transition fixture did not produce diagnostics and fresh raw zero");
 if(!stop || level!=3 || !top.risk_reasons[8] || top.osd_speed_valid_o)
  $fatal(1,"faulted QEI was trusted by risk/OSD");
 checks=checks+1;
 // Clearing distance does not erase the decoder's missed-edge history.
 force top.odo_clear=1'b1;repeat(3)@(negedge clk);release top.odo_clear;
 repeat(15)@(negedge clk);
 if(!stop || !top.risk_reasons[8])$fatal(1,"odometer clear hid retained decoder fault");
 checks=checks+1;
 // Integration boundary injection checks right-wheel symmetry and limits.
 force top.q0_info=0;force top.q1_info=32'h00001000;
 force top.odo0_fault=0;force top.odo1_fault=0;
 repeat(15)@(negedge clk);
 if(!stop || !top.risk_reasons[9])$fatal(1,"right divider overrun trusted");
 checks=checks+1;
 force top.q1_info=0;force top.q1_vel=32'h80000000;
 repeat(15)@(negedge clk);
 if(!stop || !top.risk_reasons[9])$fatal(1,"negative saturated velocity trusted");
 checks=checks+1;
 force top.q1_vel=32'h7fffffff;repeat(15)@(negedge clk);
 if(!stop || !top.risk_reasons[9])$fatal(1,"positive saturated velocity trusted");
 checks=checks+1;
 force top.q1_vel=0;force top.q0_info=32'h00100000;
 repeat(15)@(negedge clk);
 if(stop || !top.osd_speed_valid_o)$fatal(1,"rejected filter pulse alone must not poison good measurements");
 checks=checks+1;
 pulse(600);
 if(!valid || data[11:0]!=1)$fatal(1,"600 ticks must floor to 1mm");
 checks=checks+1;
 pulse(1200);
 if(!valid || data[11:0]!=2)$fatal(1,"1200 ticks must floor to 2mm");
 checks=checks+1;
 // A no-echo timeout must also commit an invalid batch atomically.
 @(posedge update);@(negedge clk);
 if(valid || data[15:12]!=1)$fatal(1,"no-echo timeout did not revoke validity");
 checks=checks+1;
 if(mixed!=0)$fatal(1,"US timestamp changed without sequence commit");
 checks=checks+1;
 $display("TEST PASSED (%0d checks)",checks);$finish;
end
initial begin #2000000;$fatal(1,"review repro watchdog");end
endmodule
