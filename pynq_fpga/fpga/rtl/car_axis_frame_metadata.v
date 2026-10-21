// A bounded 18-pixel prefix buffer; never stores a whole video frame.
// Decoded historical state is stable before the replayed SOF handshake.
// An invalid header explicitly invalidates metadata instead of reusing state.
`resetall
`timescale 1ns/1ps
`default_nettype none
module car_axis_frame_metadata(
 input wire clk,input wire rst,
 input wire [23:0] s_axis_tdata,input wire s_axis_tvalid,output wire s_axis_tready,
 input wire s_axis_tuser,input wire s_axis_tlast,
 output wire [23:0] m_axis_tdata,output wire m_axis_tvalid,input wire m_axis_tready,
 output wire m_axis_tuser,output wire m_axis_tlast,
 output reg metadata_valid,output reg [31:0] frame_id,output reg [15:0] snapshot_epoch,
 output reg [63:0] frame_pl_ticks,
 output reg [11:0] distance_mm,output reg distance_valid,
 output reg [31:0] speed_q16,output reg speed_valid,
 output reg signed [63:0] displacement_q16,output reg [63:0] path_q16,
 output reg odometry_valid,output reg [1:0] risk_level,output reg risk_stop,
 output reg [15:0] risk_reasons,output reg [15:0] header_errors
);
 localparam [1:0] CAPTURE=0,REPLAY=1,STREAM=2;
 reg [1:0] state;
 reg [4:0] count,replay_index,buffer_length;
 reg [23:0] pixels[0:17];
 reg users[0:17],lasts[0:17];
 reg [23:0] checksum;
 reg malformed;
 wire new_frame=state==STREAM && s_axis_tuser;
 assign s_axis_tready=state==CAPTURE || (state==STREAM && (new_frame||m_axis_tready));
 assign m_axis_tvalid=state==REPLAY || (state==STREAM && !new_frame && s_axis_tvalid);
 assign m_axis_tdata=state==REPLAY ? (metadata_valid?24'd0:pixels[replay_index]):s_axis_tdata;
 assign m_axis_tuser=state==REPLAY ? users[replay_index]:s_axis_tuser;
 assign m_axis_tlast=state==REPLAY ? lasts[replay_index]:s_axis_tlast;
 wire header_ok=count==17 && !malformed && !s_axis_tuser && !s_axis_tlast &&
  pixels[0]==24'hd3a95c && pixels[1]==24'h010012 &&
  (checksum^s_axis_tdata)==24'hffffff &&
  pixels[4][23:18]==0 && pixels[6][23:8]==0 && pixels[9][23:16]==0 &&
  pixels[12][23:16]==0 && pixels[13][23:16]==0 && pixels[16][23:16]==0;
 always @(posedge clk) begin
  if(rst) begin
   state<=CAPTURE;count<=0;replay_index<=0;buffer_length<=0;checksum<=0;malformed<=0;
   metadata_valid<=0;frame_id<=0;snapshot_epoch<=0;frame_pl_ticks<=0;
   distance_mm<=0;distance_valid<=0;speed_q16<=0;speed_valid<=0;
   displacement_q16<=0;path_q16<=0;odometry_valid<=0;risk_level<=3;risk_stop<=1;
   risk_reasons<=0;header_errors<=0;
  end else if(state==REPLAY) begin
   if(m_axis_tready) begin
    if(replay_index+1==buffer_length) begin
     state<=STREAM;replay_index<=0;
    end else replay_index<=replay_index+1'b1;
   end
  end else if(s_axis_tvalid && s_axis_tready) begin
   if(new_frame) begin
    pixels[0]<=s_axis_tdata;users[0]<=s_axis_tuser;lasts[0]<=s_axis_tlast;
    count<=1;checksum<=s_axis_tdata;malformed<=0;state<=CAPTURE;
    if(s_axis_tlast) begin
     state<=REPLAY;buffer_length<=1;replay_index<=0;metadata_valid<=0;
     distance_valid<=0;speed_valid<=0;odometry_valid<=0;risk_level<=3;risk_stop<=1;
     if(header_errors!=16'hffff) header_errors<=header_errors+1'b1;
    end
   end else if(state==CAPTURE) begin
    pixels[count]<=s_axis_tdata;users[count]<=s_axis_tuser;lasts[count]<=s_axis_tlast;
    checksum<=checksum^s_axis_tdata;
    if((count==0&&!s_axis_tuser)||(count!=0&&s_axis_tuser)) malformed<=1;
    if(count==17 || s_axis_tlast) begin
     state<=REPLAY;buffer_length<=count+1'b1;replay_index<=0;metadata_valid<=header_ok;
     count<=0;
     if(header_ok) begin
      frame_id<={pixels[3][7:0],pixels[2]};snapshot_epoch<=pixels[3][23:8];
      frame_pl_ticks<={pixels[16][15:0],pixels[15],pixels[14]};
      distance_mm<=pixels[4][11:0];distance_valid<=pixels[4][12];speed_valid<=pixels[4][13];
      odometry_valid<=pixels[4][14];risk_level<=pixels[4][16:15];risk_stop<=pixels[4][17];
      speed_q16<={pixels[6][7:0],pixels[5]};
      displacement_q16<={pixels[9][15:0],pixels[8],pixels[7]};
      path_q16<={pixels[12][15:0],pixels[11],pixels[10]};risk_reasons<=pixels[13][15:0];
     end else begin
      distance_valid<=0;speed_valid<=0;odometry_valid<=0;risk_level<=3;risk_stop<=1;
      if(header_errors!=16'hffff) header_errors<=header_errors+1'b1;
     end
    end else count<=count+1'b1;
   end
  end
 end
endmodule
`resetall
