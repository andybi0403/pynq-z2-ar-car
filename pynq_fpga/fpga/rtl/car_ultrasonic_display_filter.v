// Display-only median/trend processor; common 100 MHz timebase.
// Each accepted sample is a transaction. No output authorizes motion.
`resetall
`timescale 1ns/1ps
`default_nettype none
module car_ultrasonic_display_filter(
 input wire clk,rst,clear_session,
 input wire [31:0] now_ticks,
 input wire sample_event,source_valid,
 input wire [11:0] sample_mm,input wire [15:0] sample_seq,
 input wire [31:0] sample_ts,
 output wire filter_valid,output reg [11:0] filtered_mm,
 output reg [1:0] sample_count,output reg [15:0] source_seq,
 output reg [31:0] latest_ts,oldest_ts,
 output reg [1:0] trend_state,output wire trend_valid,
 output reg [31:0] trend_dt,output reg signed [15:0] trend_delta_mm,
 output reg [31:0] accepted_count,rejected_count,reset_count,
 output wire busy
);
 localparam [31:0] MIN_DT=2_000_000,MAX_DT=20_000_000,MAX_SUPPORT=50_000_000;
 reg seen;reg [15:0] last_seq;
 reg [11:0] d0,d1,d2;reg [31:0] t0,t1,t2;
 reg [11:0] history_d[0:7];reg [31:0] history_t[0:7];
 reg [3:0] history_count;reg [2:0] write_index,scan;
 reg [3:0] state;reg [1:0] pending;reg pending_seen;
 reg [11:0] work_mm;reg [31:0] work_ts;
 reg found;reg [31:0] best_score,best_dt;reg [11:0] best_mm;
 wire [31:0] source_age=now_ticks-latest_ts,support_age=now_ticks-oldest_ts;
 wire expired=sample_count!=0&&(source_age>=MAX_DT||support_age>=MAX_SUPPORT);
 assign filter_valid=sample_count==3&&!expired&&source_valid&&state==0;
 assign trend_valid=filter_valid&&trend_state!=0;
 assign busy=state!=0;
 wire [15:0] seq_delta=sample_seq-last_seq;
 wire [31:0] incoming_age=now_ticks-sample_ts,interval=sample_ts-latest_ts;
 wire gap=sample_count!=0&&(interval<MIN_DT||interval>MAX_DT);
 reg [31:0] scan_ts,candidate_dt,candidate_score;
 reg [11:0] scan_mm;reg scan_valid,candidate_valid;
 wire signed [15:0] difference=$signed({4'b0,best_mm})-$signed({4'b0,work_mm});
 wire [15:0] absolute_difference=difference[15]?-difference:difference;
 // Cancel the exact common factors in |delta|*100MHz >= dt*50 (or <= dt*20).
 // dt is bounded to 40..60 million ticks. Any |delta|>=31mm is unconditionally
 // fast, so saturating the lookup index at 31 preserves the exact classification.
 // Constant initialization produces two small ROMs, with no runtime multiplier.
 reg [31:0] fast_rom[0:31],stable_rom[0:31];integer table_index;
 initial for(table_index=0;table_index<32;table_index=table_index+1)begin
  fast_rom[table_index]=table_index*2_000_000;
  stable_rom[table_index]=table_index*5_000_000;
 end
 wire [4:0] magnitude_index=absolute_difference>=31?5'd31:absolute_difference[4:0];
 reg [31:0] fast_scaled,stable_scaled;
 wire [1:0] classification=fast_scaled>=best_dt?(difference[15]?2'd3:2'd2):
                            stable_scaled<=best_dt?2'd1:2'd0;
 function [11:0] median3(input [11:0] a,b,c);
  begin median3=a>b?(b>c?b:a>c?c:a):(a>c?a:b>c?c:b);end
 endfunction
 task clear_window;
  begin
   sample_count<=0;history_count<=0;write_index<=0;state<=0;
   trend_state<=0;pending<=0;pending_seen<=0;found<=0;
   trend_dt<=0;trend_delta_mm<=0;
  end
 endtask
 always @(posedge clk)begin
  if(rst)begin
   seen<=0;last_seq<=0;source_seq<=0;latest_ts<=0;oldest_ts<=0;
   filtered_mm<=0;
   sample_count<=0;history_count<=0;write_index<=0;scan<=0;state<=0;
   trend_state<=0;pending<=0;pending_seen<=0;found<=0;
   trend_dt<=0;trend_delta_mm<=0;accepted_count<=0;rejected_count<=0;reset_count<=0;
   // Datapath/history contents are hidden by zero counts and state=IDLE.
   // Every used slot is written before it is read. Avoid resetting 352 history
   // bits (and unused work registers) through the global high-fanout reset net.
  end else if(clear_session)begin
   clear_window();seen<=0;reset_count<=reset_count+1'b1;
  end else if(!source_valid)begin
   if(sample_count!=0||state!=0)reset_count<=reset_count+1'b1;
   clear_window();
   if(sample_event)rejected_count<=rejected_count+1'b1;
  end else if(sample_event)begin
   if(state!=0||incoming_age>=MAX_DT||(seen&&seq_delta[15]))begin
    rejected_count<=rejected_count+1'b1;
    if(sample_count!=0||state!=0)reset_count<=reset_count+1'b1;
    clear_window();
   end else if(!seen||seq_delta!=0)begin
    accepted_count<=accepted_count+1'b1;seen<=1;last_seq<=sample_seq;source_seq<=sample_seq;
    latest_ts<=sample_ts;
    if(expired||gap||sample_count==0)begin
     clear_window();sample_count<=1;d0<=sample_mm;t0<=sample_ts;oldest_ts<=sample_ts;
     if(expired||gap)reset_count<=reset_count+1'b1;
    end else if(sample_count==1)begin
     d1<=sample_mm;t1<=sample_ts;sample_count<=2;
    end else begin
     if(sample_count==2)begin
      d2<=sample_mm;t2<=sample_ts;oldest_ts<=t0;work_mm<=median3(d0,d1,sample_mm);
     end else begin
      d0<=d1;t0<=t1;d1<=d2;t1<=t2;d2<=sample_mm;t2<=sample_ts;
      oldest_ts<=t1;work_mm<=median3(d1,d2,sample_mm);
     end
     // Publish only after trend processing completes: all output fields are one batch.
     work_ts<=sample_ts;scan<=0;found<=0;best_score<=32'hffffffff;state<=1;
    end
   end else if(expired)begin clear_window();reset_count<=reset_count+1'b1;end
  end else if(expired)begin clear_window();reset_count<=reset_count+1'b1;end
  else case(state)
   1:begin
    // Separate RAM lookup, subtraction, absolute offset and best-match compare.
    // A scan takes 32 cycles (320ns), far below the 20ms minimum sample interval.
    scan_ts<=history_t[scan];scan_mm<=history_d[scan];
    scan_valid<={1'b0,scan}<history_count;state<=4;
   end
   4:begin candidate_dt<=work_ts-scan_ts;state<=5;end
   5:begin
    candidate_score<=candidate_dt>50_000_000?candidate_dt-50_000_000:50_000_000-candidate_dt;
    candidate_valid<=scan_valid&&candidate_dt>=40_000_000&&candidate_dt<=60_000_000;
    state<=6;
   end
   6:begin
    if(candidate_valid&&
       (!found||candidate_score<best_score||(candidate_score==best_score&&candidate_dt>best_dt)))begin
     found<=1;best_score<=candidate_score;best_dt<=candidate_dt;best_mm<=scan_mm;
    end
    if(scan==7)state<=2;else begin scan<=scan+1'b1;state<=1;end
   end
   2:begin
    fast_scaled<=fast_rom[magnitude_index];
    stable_scaled<=stable_rom[magnitude_index];
    state<=3;
   end
   3:begin
    if(found)begin
     trend_dt<=best_dt;trend_delta_mm<=difference;
     if(classification==0)pending_seen<=0;
     else begin
      if(pending_seen&&pending==classification)trend_state<=classification;
      pending<=classification;pending_seen<=1;
     end
    end
    filtered_mm<=work_mm;sample_count<=3;
    history_d[write_index]<=work_mm;history_t[write_index]<=work_ts;
    write_index<=write_index+1'b1;if(history_count<8)history_count<=history_count+1'b1;
    state<=0;
   end
   default:state<=0;
  endcase
 end
endmodule
`resetall
