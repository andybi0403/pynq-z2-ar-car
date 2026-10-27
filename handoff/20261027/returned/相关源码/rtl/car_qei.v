// x4 table decoder. AMDC structural reference; filtering/period are local.
// Startup adopts stable AB without inventing motion; reverse/illegal resets period.
`timescale 1ns/1ps
`default_nettype none
module car_qei(
 input wire clk,rst,a_raw,b_raw,cfg_dir,
 input wire [31:0] cfg_filt,
 output reg [31:0] pos_cnt,
 output reg dir_pos,seen_edge,
 output reg [7:0] ill_cnt,filt_rej_cnt,
 output reg [31:0] period_ticks,
 output reg period_valid,step_pulse,step_dir
);
 (* ASYNC_REG="TRUE" *) reg [1:0] sync1,sync2;
 reg [1:0] candidate,state_ab;
 reg [31:0] stable_count,gap,old_filter;
 reg [2:0] warmup;
 reg initialized,have_edge,old_dir;
 wire forward=({state_ab,sync2}==4'b0010)||({state_ab,sync2}==4'b1011)||
              ({state_ab,sync2}==4'b1101)||({state_ab,sync2}==4'b0100);
 wire direction=forward ^ cfg_dir;
 wire stable_input=cfg_filt==0 || (candidate==sync2 && stable_count>=cfg_filt-1);
 always @(posedge clk) begin
  if(rst) begin
   sync1<=0;sync2<=0;candidate<=0;state_ab<=0;stable_count<=0;gap<=0;
   old_filter<=0;old_dir<=0;warmup<=0;initialized<=0;have_edge<=0;
   pos_cnt<=0;dir_pos<=0;seen_edge<=0;ill_cnt<=0;filt_rej_cnt<=0;
   period_ticks<=0;period_valid<=0;step_pulse<=0;step_dir<=0;
  end else begin
   sync1<={a_raw,b_raw};sync2<=sync1;step_pulse<=0;
   old_filter<=cfg_filt;old_dir<=cfg_dir;
   if(gap!=32'hffffffff) gap<=gap+1'b1;
   else begin period_valid<=0;have_edge<=0;end
   if(warmup<4) warmup<=warmup+1'b1;
   if(candidate!=sync2) begin
    if(candidate!=state_ab && stable_count<cfg_filt && filt_rej_cnt!=255)
     filt_rej_cnt<=filt_rej_cnt+1'b1;
    candidate<=sync2;stable_count<=1;
   end else if(stable_count!=32'hffffffff) stable_count<=stable_count+1'b1;
   if(old_filter!=cfg_filt || old_dir!=cfg_dir) begin
    initialized<=0;have_edge<=0;period_valid<=0;stable_count<=0;
   end else if(warmup==4 && stable_input) begin
    if(!initialized) begin
     state_ab<=sync2;initialized<=1;have_edge<=0;period_valid<=0;
    end else if(sync2!=state_ab) begin
     state_ab<=sync2;
     if((sync2 ^ state_ab)==2'b11) begin
      if(ill_cnt!=255) ill_cnt<=ill_cnt+1'b1;
      have_edge<=0;period_valid<=0;
     end else begin
      pos_cnt<=direction ? pos_cnt+1'b1 : pos_cnt-1'b1;
      dir_pos<=direction;seen_edge<=1;step_pulse<=1;step_dir<=direction;
      period_valid<=have_edge && direction==dir_pos && gap!=32'hffffffff;
      period_ticks<=have_edge && direction==dir_pos ? gap+1'b1 : 0;
      have_edge<=1;gap<=0;
     end
    end
   end
  end
 end
endmodule
`default_nettype wire
