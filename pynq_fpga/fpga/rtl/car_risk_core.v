// Fail-safe forward-motion risk core. No AXI and no private counter.
// Arithmetic and metadata travel through the same pipelined transaction.
`resetall
`timescale 1ns/1ps
`default_nettype none
module car_risk_core #(
 parameter integer DATA_MAX_AGE_TICKS=20_000_000, parameter integer COMMAND_LEASE_TICKS=25_000_000,
 parameter integer REACTION_MS=150, parameter integer BRAKE_DECEL_MMPS2=500,
 parameter integer BASE_MARGIN_MM=100, parameter integer YELLOW_BAND_MM=100,
 parameter integer MAX_SPEED_MMPS=5000
)(
 input wire clk,input wire rst,input wire [31:0] now_ticks,input wire enable,
 input wire command_forward,input wire command_valid,input wire [31:0] command_ts,
 input wire [31:0] us_data,input wire us_valid,input wire [31:0] us_ts,input wire [15:0] us_seq,
 input wire [2:0] ir_status,input wire ir_valid,input wire [31:0] ir_ts,input wire [15:0] ir_seq,
 input wire [31:0] q0_vel,input wire q0_valid,input wire [31:0] q0_ts,input wire [15:0] q0_seq,
 input wire [31:0] q1_vel,input wire q1_valid,input wire [31:0] q1_ts,input wire [15:0] q1_seq,
 output reg stop_request,output reg [1:0] risk_level,output reg [15:0] reason_bits,
 output reg [31:0] required_mm,output reg [31:0] risk_ts,output reg risk_valid,
 output reg [15:0] risk_seq,output reg risk_update
);
 localparam [1:0] RISK_GREEN=2'd0,RISK_YELLOW=2'd1,RISK_RED=2'd2,RISK_FAULT=2'd3;
 localparam integer R_DISABLED=0,R_CMD_INVALID=1,R_CMD_STALE=2,R_US_INVALID=3,R_US_STALE=4,
  R_IR_INVALID=5,R_IR_RESERVED=6,R_IR_OBSTACLE=7,R_Q0_INVALID=8,R_Q1_INVALID=9,
  R_Q0_STALE=10,R_Q1_STALE=11,R_DISTANCE=12,R_DIRECTION=13;
 localparam integer RECIP_SHIFT=20;
 localparam integer REACTION_RECIP=((1<<RECIP_SHIFT)+999)/1000;
 localparam integer BRAKE_DEN=2*BRAKE_DECEL_MMPS2;
 localparam integer BRAKE_RECIP=((1<<RECIP_SHIFT)+BRAKE_DEN-1)/BRAKE_DEN;
 // s0_speed is 13 bits, so s0_speed*REACTION_MS fits 21 bits whenever
 // REACTION_MS is at most 255 (8191*255 < 2^21). Keep full width otherwise.
 localparam integer REACTION_PRODUCT_WIDTH=(REACTION_MS>=0 && REACTION_MS<=255) ? 21 : 32;
 // QEI direction configuration must normalize forward wheel motion positive.
 // A negative wheel while forward is requested is a configuration/fault reason;
 // avoiding a 32-bit abs carry chain also keeps the safety path at 100 MHz.
 // Keep comparison and the positive Q16.16 round-up in separate existing
 // pipeline stages. Metadata and arithmetic retain exactly the same latency.
 wire [31:0] q0_speed=q0_vel[31]?0:{17'b0,q0_vel[30:16]};
 wire [31:0] q1_speed=q1_vel[31]?0:{17'b0,q1_vel[30:16]};
 wire speed_fraction=(q0_speed>=q1_speed && !q0_vel[31] && |q0_vel[15:0]) ||
                     (q1_speed>=q0_speed && !q1_vel[31] && |q1_vel[15:0]);
 wire [31:0] speed_raw=q0_speed>q1_speed?q0_speed:q1_speed;
 wire [12:0] speed_now=speed_raw>MAX_SPEED_MMPS?MAX_SPEED_MMPS:speed_raw[12:0];
 reg [15:0] faults_now;
 always @(*) begin
  faults_now=0;
  if(!enable) faults_now[R_DISABLED]=1;
  if(!command_valid) faults_now[R_CMD_INVALID]=1;
  if(command_valid&&(now_ticks-command_ts)>=COMMAND_LEASE_TICKS) faults_now[R_CMD_STALE]=1;
  if(!us_valid) faults_now[R_US_INVALID]=1;
  if(us_valid&&(now_ticks-us_ts)>=DATA_MAX_AGE_TICKS) faults_now[R_US_STALE]=1;
  if(!ir_valid||!ir_status[2]) faults_now[R_IR_INVALID]=1;
  // IR_TS is an event/change timestamp, not a periodic observation timestamp.
  // A stable obstacle-free input is continuously sampled but does not refresh
  // IR_TS, so applying DATA_MAX_AGE_TICKS here would force a false stop after
  // 200 ms. Disconnection cannot be distinguished from a static level by
  // this RTL; validity/stability and the electrical fail-safe are separate.
  if(ir_valid&&ir_status[1:0]!=0) faults_now[R_IR_OBSTACLE]=1;
  if(!q0_valid) faults_now[R_Q0_INVALID]=1;
  if(!q1_valid) faults_now[R_Q1_INVALID]=1;
  if(q0_valid&&(now_ticks-q0_ts)>=DATA_MAX_AGE_TICKS) faults_now[R_Q0_STALE]=1;
  if(q1_valid&&(now_ticks-q1_ts)>=DATA_MAX_AGE_TICKS) faults_now[R_Q1_STALE]=1;
  if(command_forward&&(q0_vel[31]||q1_vel[31])) faults_now[R_DIRECTION]=1;
 end
 reg [12:0] s0_speed;reg [11:0] s0_distance;reg s0_forward;
 reg s0_fraction;
 reg [15:0] s0_faults;reg [98:0] s0_signature;reg [31:0] s0_now;reg s0_valid;
 reg [12:0] s0a_speed;reg [11:0] s0a_distance;reg s0a_forward;
 reg [15:0] s0a_faults;reg [98:0] s0a_signature;reg [31:0] s0a_now;reg s0a_valid;
 reg [REACTION_PRODUCT_WIDTH-1:0] s1_reaction;reg [31:0] s1_brake;reg [11:0] s1_distance;reg s1_forward;
 reg [15:0] s1_faults;reg [98:0] s1_signature;reg [31:0] s1_now;reg s1_valid;
 reg [REACTION_PRODUCT_WIDTH-1:0] s1a_reaction;reg [31:0] s1a_brake;reg [11:0] s1a_distance;reg s1a_forward;
 reg [15:0] s1a_faults;reg [98:0] s1a_signature;reg [31:0] s1a_now;reg s1a_valid;
 reg [31:0] s1b_brake;reg [11:0] s1b_distance;reg s1b_forward;
 reg [15:0] s1b_faults;reg [98:0] s1b_signature;reg [31:0] s1b_now;reg s1b_valid;
 reg [47:0] s2_brake;reg [11:0] s2_distance;reg s2_forward;
 reg [15:0] s2_faults;reg [98:0] s2_signature;reg [31:0] s2_now;reg s2_valid;
 wire [47:0] s2a_reaction;
 reg [47:0] s2a_brake;reg [11:0] s2a_distance;reg s2a_forward;
 reg [15:0] s2a_faults;reg [98:0] s2a_signature;reg [31:0] s2a_now;reg s2a_valid;
 // Keep the second multiplier's operand register inside its own boundary.
 // Otherwise synthesis can absorb it into the preceding DSP's PREG and
 // leave this multiplier's AREG disabled. Metadata follows the same 3 clocks.
 car_risk_reaction_scale #(.INPUT_WIDTH(REACTION_PRODUCT_WIDTH),.RECIP(REACTION_RECIP)) reaction_scale (
  .clk(clk),.rst(rst),.reaction(s1a_reaction),.scaled(s2a_reaction));
 wire [31:0] reaction_mm=(s2a_reaction+((1<<RECIP_SHIFT)-1))>>RECIP_SHIFT;
 wire [31:0] brake_mm=(s2a_brake+((1<<RECIP_SHIFT)-1))>>RECIP_SHIFT;
 reg [31:0] s3_reaction_mm,s3_brake_mm;reg [11:0] s3_distance;reg s3_forward;
 reg [15:0] s3_faults;reg [98:0] s3_signature;reg [31:0] s3_now;reg s3_valid;
 wire [31:0] required_next=BASE_MARGIN_MM+s3_reaction_mm+s3_brake_mm;
 // Register the long reciprocal/add chain before policy comparisons.  Apart
 // from improving timing, this makes the arithmetic result and source tuple
 // an explicit pipeline transaction.
 reg [31:0] s4_required;reg [11:0] s4_distance;reg s4_forward;
 reg [15:0] s4_faults;reg [98:0] s4_signature;reg [31:0] s4_now;reg s4_valid;
 reg [15:0] reasons_next;reg [1:0] level_next;reg stop_next;
 always @(*) begin
  reasons_next=s4_faults;
  if(s4_forward&&!s4_faults[R_US_INVALID]&&!s4_faults[R_US_STALE]&&s4_distance<=s4_required)
   reasons_next[R_DISTANCE]=1;
  // v0.11: IR invalid/obstacle bits remain observable warnings. They never
  // grant/revoke driving permission, alter the distance policy or request STOP.
  if((reasons_next[11:0]&12'hf5f)!=0||reasons_next[R_DIRECTION]) level_next=RISK_FAULT;
  else if(reasons_next[R_DISTANCE]) level_next=RISK_RED;
  else if(s4_forward&&s4_distance<=s4_required+YELLOW_BAND_MM) level_next=RISK_YELLOW;
  else level_next=RISK_GREEN;
  stop_next=(level_next==RISK_RED)||(level_next==RISK_FAULT);
 end
 reg [98:0] published_signature;
 always @(posedge clk) begin
  if(rst) begin
   s0_speed<=0;s0_fraction<=0;s0_distance<=0;s0_forward<=0;s0_faults<=16'hffff;s0_signature<=0;s0_now<=0;s0_valid<=0;
   s0a_speed<=0;s0a_distance<=0;s0a_forward<=0;s0a_faults<=16'hffff;s0a_signature<=0;s0a_now<=0;s0a_valid<=0;
   s1_reaction<=0;s1_brake<=0;s1_distance<=0;s1_forward<=0;s1_faults<=16'hffff;s1_signature<=0;s1_now<=0;s1_valid<=0;
   s1a_reaction<=0;s1a_brake<=0;s1a_distance<=0;s1a_forward<=0;s1a_faults<=16'hffff;s1a_signature<=0;s1a_now<=0;s1a_valid<=0;
   s1b_brake<=0;s1b_distance<=0;s1b_forward<=0;s1b_faults<=16'hffff;s1b_signature<=0;s1b_now<=0;s1b_valid<=0;
   s2_brake<=0;s2_distance<=0;s2_forward<=0;s2_faults<=16'hffff;s2_signature<=0;s2_now<=0;s2_valid<=0;
   s2a_brake<=0;s2a_distance<=0;s2a_forward<=0;s2a_faults<=16'hffff;s2a_signature<=0;s2a_now<=0;s2a_valid<=0;
   s3_reaction_mm<=0;s3_brake_mm<=0;s3_distance<=0;s3_forward<=0;s3_faults<=16'hffff;s3_signature<=0;s3_now<=0;s3_valid<=0;
   s4_required<=0;s4_distance<=0;s4_forward<=0;s4_faults<=16'hffff;s4_signature<=0;s4_now<=0;s4_valid<=0;
   stop_request<=1;risk_level<=RISK_FAULT;reason_bits<=16'hffff;required_mm<=0;
   risk_ts<=0;risk_valid<=0;risk_seq<=0;risk_update<=0;published_signature<=0;
  end else begin
   s0_speed<=speed_now;s0_fraction<=speed_fraction;s0_distance<=us_data[11:0];s0_forward<=command_forward;
   // Command writes renew the PL lease even when the requested direction is
   // unchanged, so command timestamp/state belong to the evaluated batch.
   s0_faults<=faults_now;s0_signature<={us_seq,ir_seq,q0_seq,q1_seq,command_ts,enable,command_valid,command_forward};s0_now<=now_ticks;s0_valid<=1;
   s0a_speed<=s0_speed<MAX_SPEED_MMPS ? s0_speed+{12'b0,s0_fraction}:s0_speed;
   s0a_distance<=s0_distance;s0a_forward<=s0_forward;
   s0a_faults<=s0_faults;s0a_signature<=s0_signature;s0a_now<=s0_now;s0a_valid<=s0_valid;
   s1_reaction<=s0a_speed*REACTION_MS;s1_brake<=s0a_speed*s0a_speed;s1_distance<=s0a_distance;
   s1_forward<=s0a_forward;s1_faults<=s0a_faults;s1_signature<=s0a_signature;s1_now<=s0a_now;s1_valid<=s0a_valid;
   s1a_reaction<=s1_reaction;s1a_brake<=s1_brake;s1a_distance<=s1_distance;
   s1a_forward<=s1_forward;s1a_faults<=s1_faults;s1a_signature<=s1_signature;s1a_now<=s1_now;s1a_valid<=s1_valid;
   s1b_brake<=s1a_brake;s1b_distance<=s1a_distance;
   s1b_forward<=s1a_forward;s1b_faults<=s1a_faults;s1b_signature<=s1a_signature;s1b_now<=s1a_now;s1b_valid<=s1a_valid;
   s2_brake<=s1b_brake*BRAKE_RECIP;s2_distance<=s1b_distance;
   s2_forward<=s1b_forward;s2_faults<=s1b_faults;s2_signature<=s1b_signature;s2_now<=s1b_now;s2_valid<=s1b_valid;
   s2a_brake<=s2_brake;s2a_distance<=s2_distance;
   s2a_forward<=s2_forward;s2a_faults<=s2_faults;s2a_signature<=s2_signature;s2a_now<=s2_now;s2a_valid<=s2_valid;
   s3_reaction_mm<=reaction_mm;s3_brake_mm<=brake_mm;s3_distance<=s2a_distance;s3_forward<=s2a_forward;
   s3_faults<=s2a_faults;s3_signature<=s2a_signature;s3_now<=s2a_now;s3_valid<=s2a_valid;
   s4_required<=required_next;s4_distance<=s3_distance;s4_forward<=s3_forward;
   s4_faults<=s3_faults;s4_signature<=s3_signature;s4_now<=s3_now;s4_valid<=s3_valid;
   risk_update<=0;
   if(s4_valid&&(stop_next!=stop_request||level_next!=risk_level||reasons_next!=reason_bits||
      s4_required!=required_mm||s4_signature!=published_signature)) begin
    stop_request<=stop_next;risk_level<=level_next;reason_bits<=reasons_next;required_mm<=s4_required;
    risk_ts<=s4_now;risk_valid<=1;risk_seq<=risk_seq+1'b1;risk_update<=1;published_signature<=s4_signature;
   end
  end
 end
endmodule

// Three clocks: registered operand, multiplier MREG, output PREG.
(* keep_hierarchy = "soft" *)
module car_risk_reaction_scale #(
 parameter integer INPUT_WIDTH=21, parameter integer RECIP=1049
)(
 input wire clk,input wire rst,input wire [INPUT_WIDTH-1:0] reaction,
 output reg [47:0] scaled
);
 reg [INPUT_WIDTH-1:0] operand;
 (* use_dsp = "yes" *) reg [47:0] product_m;
 always @(posedge clk) begin
  if(rst) begin operand<=0;product_m<=0;scaled<=0;end
  else begin operand<=reaction;product_m<=operand*RECIP;scaled<=product_m;end
 end
endmodule
`resetall
