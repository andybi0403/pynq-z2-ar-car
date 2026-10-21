// Backpressure-safe AXI4-Stream RGB888 OSD architecture.
// RGB order: [23:16] R, [15:8] G, [7:0] B. TUSER=SOF, TLAST=EOL.
// State inputs are committed only when an SOF pixel is accepted.
//
// Native 24px OFL Chinese HUD, native 32px status labels. Values are signed mm/s and distance mm.
// Invalid readings are labelled in Chinese; BCD runs at accepted SOF.
`resetall
`timescale 1ns/1ps
`default_nettype none
module car_axis_osd #(
 parameter integer WIDTH=640,parameter integer HEIGHT=480,
 parameter integer ENABLE_TEXT=1
)(
 input wire clk,input wire rst,
 input wire [23:0] s_axis_tdata,input wire s_axis_tvalid,output wire s_axis_tready,
 input wire s_axis_tuser,input wire s_axis_tlast,
 output reg [23:0] m_axis_tdata,output reg m_axis_tvalid,input wire m_axis_tready,
 output reg m_axis_tuser,output reg m_axis_tlast,
 input wire [1:0] state_risk_level,input wire state_stop,input wire state_locked,
 input wire state_distance_valid,input wire state_speed_valid,
 input wire [11:0] state_distance_mm,input wire [31:0] state_speed_q16,
 output reg [15:0] frame_error_count
);
 localparam [23:0] C_GREEN=24'h00d060,C_YELLOW=24'hffd000,C_RED=24'hff2020,C_FAULT=24'hff2020,
  C_WHITE=24'hffffff,C_BLACK=24'h101010;
 reg [15:0] x_q,y_q;
 reg [1:0] active_risk;
 reg active_stop,active_locked,active_distance_valid,active_speed_valid;
 reg [11:0] active_distance;
 reg [31:0] active_speed;
 reg prep_valid,prep_user,prep_last,prep_band;
 reg [23:0] prep_data,prep_color;
 reg [5:0] prep_glyph;
 reg [4:0] prep_row,prep_bit;
 reg prep_distance_background,prep_lamp_text;
 reg prep_lamp_panel,prep_lamp_selected;
 reg [7:0] prep_lamp_dx,prep_lamp_dy;
 reg [23:0] prep_lamp_color;
 // Separate ROM/bit selection from RGB composition with an elastic stage.
 reg font_valid,font_user,font_last,font_band,font_distance_background;
 reg font_fg,font_outline;
 reg [23:0] font_data,font_color,font_lamp_pixel;
 wire take_out=!m_axis_tvalid||m_axis_tready;
 wire take_font=!font_valid||take_out;
 wire take_in=!prep_valid||take_font;
 assign s_axis_tready=take_in;
 wire [15:0] px=s_axis_tuser?16'd0:x_q;
 wire [15:0] py=s_axis_tuser?16'd0:y_q;
 wire [1:0] draw_risk=s_axis_tuser?state_risk_level:active_risk;
 wire draw_stop=s_axis_tuser?state_stop:active_stop;
 wire draw_locked=s_axis_tuser?state_locked:active_locked;
 wire draw_distance_valid=s_axis_tuser?state_distance_valid:active_distance_valid;
 wire draw_speed_valid=s_axis_tuser?state_speed_valid:active_speed_valid;
 wire draw_all_valid=draw_distance_valid&&draw_speed_valid;
 wire [11:0] draw_distance=s_axis_tuser?state_distance_mm:active_distance;
 wire [31:0] draw_speed=s_axis_tuser?state_speed_q16:active_speed;
 wire [23:0] risk_color=(draw_risk==2'd0) ? C_GREEN :
  (draw_risk==2'd1) ? C_YELLOW : (draw_risk==2'd2) ? C_RED : C_FAULT;
 // Three 48px status circles and 32px Chinese labels, display only.
 // Fault/STOP selects emergency, never the green safe lamp.
 localparam [23:0] C_GRAY=24'h686868;
 wire [1:0] lamp_active=(draw_stop||!draw_all_valid||draw_risk>=2)?2'd2:draw_risk;
 wire lamp_panel=WIDTH>=560&&px>=WIDTH-264&&px<WIDTH-24&&py>=16&&py<116;
 wire [1:0] lamp_index=px>=WIDTH-104?2'd2:px>=WIDTH-184?2'd1:2'd0;
 // Only evaluated inside the bounded panel: local x is 0..79, y is 16..115.
 // Modular 8-bit subtraction is exact there and avoids a 16-bit carry chain.
 localparam [7:0] LAMP_X0=WIDTH-264,LAMP_X1=WIDTH-184,LAMP_X2=WIDTH-104;
 wire [7:0] lamp_local=px[7:0]-(lamp_index==2?LAMP_X2:lamp_index==1?LAMP_X1:LAMP_X0);
 wire [7:0] lamp_dx=lamp_local>=8'd40 ? lamp_local-8'd40 : 8'd40-lamp_local;
 wire [7:0] lamp_dy=py[7:0]>=8'd48 ? py[7:0]-8'd48 : 8'd48-py[7:0];
 function [4:0] circle_outer(input [4:0] dy);
  begin case(dy)
   5'd0:circle_outer=5'd24;
   5'd1:circle_outer=5'd23;
   5'd2:circle_outer=5'd23;
   5'd3:circle_outer=5'd23;
   5'd4:circle_outer=5'd23;
   5'd5:circle_outer=5'd23;
   5'd6:circle_outer=5'd23;
   5'd7:circle_outer=5'd22;
   5'd8:circle_outer=5'd22;
   5'd9:circle_outer=5'd22;
   5'd10:circle_outer=5'd21;
   5'd11:circle_outer=5'd21;
   5'd12:circle_outer=5'd20;
   5'd13:circle_outer=5'd20;
   5'd14:circle_outer=5'd19;
   5'd15:circle_outer=5'd18;
   5'd16:circle_outer=5'd17;
   5'd17:circle_outer=5'd16;
   5'd18:circle_outer=5'd15;
   5'd19:circle_outer=5'd14;
   5'd20:circle_outer=5'd13;
   5'd21:circle_outer=5'd11;
   5'd22:circle_outer=5'd9;
   5'd23:circle_outer=5'd6;
   5'd24:circle_outer=5'd0;
   default:circle_outer=0;
  endcase end
 endfunction
 function [4:0] circle_inner(input [4:0] dy);
  begin case(dy)
   5'd0:circle_inner=5'd21;
   5'd1:circle_inner=5'd20;
   5'd2:circle_inner=5'd20;
   5'd3:circle_inner=5'd20;
   5'd4:circle_inner=5'd20;
   5'd5:circle_inner=5'd20;
   5'd6:circle_inner=5'd20;
   5'd7:circle_inner=5'd19;
   5'd8:circle_inner=5'd19;
   5'd9:circle_inner=5'd18;
   5'd10:circle_inner=5'd18;
   5'd11:circle_inner=5'd17;
   5'd12:circle_inner=5'd17;
   5'd13:circle_inner=5'd16;
   5'd14:circle_inner=5'd15;
   5'd15:circle_inner=5'd14;
   5'd16:circle_inner=5'd13;
   5'd17:circle_inner=5'd12;
   5'd18:circle_inner=5'd10;
   5'd19:circle_inner=5'd8;
   5'd20:circle_inner=5'd6;
   5'd21:circle_inner=5'd0;
   default:circle_inner=0;
  endcase end
 endfunction
 wire lamp_inside=prep_lamp_dy<=24&&prep_lamp_dx<=circle_outer(prep_lamp_dy[4:0]);
 wire lamp_hole=prep_lamp_dy<=21&&prep_lamp_dx<=circle_inner(prep_lamp_dy[4:0]);
 wire lamp_selected=lamp_index==lamp_active;
 wire [23:0] lamp_color=!lamp_selected?C_GRAY:lamp_index==0?C_GREEN:lamp_index==1?C_YELLOW:C_RED;
 wire lamp_text=lamp_panel&&py>=80&&py<112&&lamp_local>=8&&lamp_local<72;
 wire [7:0] lamp_tx=lamp_local-8'd8,lamp_ty=py[7:0]-8'd80;
 wire [5:0] lamp_glyph=6'd52+{lamp_index,1'b0}+lamp_tx[5];
 // Native 24px Chinese labels; values retain their mm and mm/s units.
 localparam [15:0] TXT_X0=24, TXT_Y0=24;
 // Fourteen 24px cells end before the status panel at the 640px profile.
 // Trailing blank cells must not take priority over a status circle.
 wire text_band = ENABLE_TEXT && px>=24 && px<360 &&
                  ((py>=24&&py<48)||(py>=64&&py<88));
 wire [15:0] tx=px-TXT_X0;
 wire line0=py<64;
 wire [15:0] ty=py-(line0?16'd24:16'd64);
 wire [4:0] grow=ty[4:0];
 reg [1:0]  cdc_st;
 reg [35:0] cdc_shift;    // {bcd[35:16], bin[15:0]}
 reg [4:0]  cdc_cnt;
 reg [15:0] speed_bcd, dist_bcd;   // 4 BCD digits each
 reg        speed_neg, speed_invalid, dist_invalid;
 wire [15:0] spd_int = (draw_speed[31] ? (~draw_speed + 32'd1) : draw_speed) >> 16;
 wire [15:0] dst_int = {4'b0, draw_distance};

 // Fixed OFL font subset, generated once and bound to the candidate.
 (* rom_style="distributed" *) reg [47:0] font_mem[0:2047];
 (* rom_style="distributed" *) reg [63:0] lamp_font_mem[0:2047];
 initial begin
  $readmemh("font_24x24_hud.mem",font_mem);
  $readmemh("font_32x32_hud.mem",lamp_font_mem);
 end

 function [19:0] dabble(input [19:0] bcd);
  reg [19:0] r; integer i4;
  begin
   r = bcd;
   for (i4 = 0; i4 < 5; i4 = i4 + 1)
    if (r[i4*4 +: 4] > 4) r[i4*4 +: 4] = r[i4*4 +: 4] + 4'd3;
   dabble = r;
  end
 endfunction
 wire [35:0] cdc_next = {dabble(cdc_shift[35:16]), cdc_shift[15:0]} << 1;

 // Parallel cell decode avoids division on the 100MHz pixel path.
 wire [13:0] text_cell;
 genvar text_index;
 generate for(text_index=0;text_index<14;text_index=text_index+1)begin: text_cells
  localparam [8:0] CELL_START=24+text_index*24,CELL_END=48+text_index*24;
  assign text_cell[text_index]=px[8:0]>=CELL_START&&px[8:0]<CELL_END;
 end endgenerate
 wire [3:0] gcol;
 assign gcol[0]=|(text_cell&14'h2aaa);
 assign gcol[1]=|(text_cell&14'h0ccc);
 assign gcol[2]=|(text_cell&14'h30f0);
 assign gcol[3]=|(text_cell&14'h3f00);
 wire [4:0] gx=px[4:0]-{~gcol[1:0],3'b000};
 reg [5:0] glyph;
 reg fg_white;
 always @(*) begin
  glyph=6'd11;fg_white=line0?!speed_invalid:!dist_invalid;
  if(line0) begin
   case(gcol)
    0:glyph=6'd26;
    1:glyph=6'd27;
    2:glyph=6'd12;
    3:glyph=6'd11;
    4:glyph=speed_invalid?6'd43:speed_neg?6'd10:6'd11;
    5:glyph=speed_invalid?6'd44:{2'b0,speed_bcd[15:12]};
    6:glyph=speed_invalid?6'd11:{2'b0,speed_bcd[11:8]};
    7:glyph=speed_invalid?6'd11:{2'b0,speed_bcd[7:4]};
    8:glyph=speed_invalid?6'd11:{2'b0,speed_bcd[3:0]};
    10,11:glyph=6'd15;12:glyph=6'd17;13:glyph=6'd16;
    default:glyph=6'd11;
   endcase
  end else begin
   case(gcol)
    0:glyph=6'd28;
    1:glyph=6'd29;
    2:glyph=6'd12;
    3:glyph=6'd11;
    4:glyph=dist_invalid?6'd43:{2'b0,dist_bcd[15:12]};
    5:glyph=dist_invalid?6'd44:{2'b0,dist_bcd[11:8]};
    6:glyph=dist_invalid?6'd11:{2'b0,dist_bcd[7:4]};
    7:glyph=dist_invalid?6'd11:{2'b0,dist_bcd[3:0]};
    9,10:glyph=6'd15;
    default:glyph=6'd11;
   endcase
  end
 end
 // Register the selector before ROM lookup; keep the enlarged font path short.
 wire [47:0] rom_word=font_mem[{prep_glyph,prep_row}];
 wire [63:0] lamp_rom_word=lamp_font_mem[{prep_glyph,prep_row}];
 wire [23:0] normal_fg=rom_word[47:24],normal_outline=rom_word[23:0];
 wire [31:0] lamp_fg=lamp_rom_word[63:32],lamp_outline=lamp_rom_word[31:0];
 wire text_fg=prep_lamp_text?lamp_fg[prep_bit]:normal_fg[prep_bit];
 wire text_outline=prep_lamp_text?lamp_outline[prep_bit]:normal_outline[prep_bit];
 wire [23:0] text_color=fg_white?C_WHITE:(line0?C_FAULT:C_YELLOW);

 // Per-frame decimal conversion engine: classic double-dabble on a
 // {bcd20, bin16} cascade, 16 cycles per value, short 4-bit add chains only
 // -- no divider, no long combinational path. Started when an SOF is
 // accepted; done well before the text band rows (band starts at y=16,
 // >2560 pixels after SOF; conversion needs 32).
 localparam [1:0] C_SPD=2'd0, C_DST=2'd1, C_DONE=2'd2;
 always @(posedge clk) begin
  if (rst) begin
   cdc_st<=0;cdc_shift<=0;cdc_cnt<=0;speed_bcd<=0;dist_bcd<=0;
   speed_neg<=0;speed_invalid<=1;dist_invalid<=1;
  end else if (take_in && s_axis_tvalid && s_axis_tuser) begin
   // SOF accepted: load speed conversion from the live state mux
   cdc_shift <= {20'b0, spd_int[15:0]};
   speed_neg <= draw_speed[31] && spd_int != 0;
   speed_invalid <= !draw_speed_valid || draw_speed == 32'h80000000 || spd_int > 9999;
   dist_invalid <= !draw_distance_valid || dst_int > 9999;
   cdc_st <= C_SPD; cdc_cnt <= 5'd0;
  end else begin
   case (cdc_st)
    C_SPD: begin
     cdc_shift <= cdc_next;
     cdc_cnt   <= cdc_cnt + 1'b1;
     if (cdc_cnt == 5'd15) begin
      // cdc_next contains the 16th shift. BCD occupies [35:16]; keep the
      // four decimal digits [31:16] and discard the always-zero 10k nibble.
      speed_bcd <= cdc_next[31:16];
      cdc_shift <= {20'b0, dst_int};
      cdc_cnt   <= 5'd0;
      cdc_st    <= C_DST;
     end
    end
    C_DST: begin
     cdc_shift <= cdc_next;
     cdc_cnt   <= cdc_cnt + 1'b1;
     if (cdc_cnt == 5'd15) begin
      dist_bcd <= cdc_next[31:16];
      cdc_st   <= C_DONE;
     end
    end
    default: cdc_st <= C_DONE;
   endcase
  end
 end


 // Coordinate arithmetic and circle lookup occupy separate existing stages.
 // Three elastic stages retain one pixel/clock and hold all payloads on stalls.
 wire [23:0] composed_pixel=s_axis_tdata;
 wire [23:0] lamp_pixel=lamp_inside&&(prep_lamp_selected||!lamp_hole)?prep_lamp_color:prep_data;

 always @(posedge clk) begin
  if (rst) begin
   m_axis_tdata<=0;m_axis_tvalid<=0;m_axis_tuser<=0;m_axis_tlast<=0;
   prep_valid<=0;prep_user<=0;prep_last<=0;prep_band<=0;prep_distance_background<=0;prep_lamp_text<=0;
   prep_data<=0;prep_color<=0;prep_glyph<=0;prep_row<=0;prep_bit<=0;
   prep_lamp_panel<=0;prep_lamp_selected<=0;prep_lamp_dx<=0;prep_lamp_dy<=0;prep_lamp_color<=0;
   font_valid<=0;font_user<=0;font_last<=0;font_band<=0;font_distance_background<=0;
   font_fg<=0;font_outline<=0;font_data<=0;font_color<=0;font_lamp_pixel<=0;
   x_q<=0;y_q<=0;active_risk<=3;active_stop<=1;active_locked<=1;
   active_distance_valid<=0;active_speed_valid<=0;
   active_distance<=0;active_speed<=0;frame_error_count<=0;
  end else begin
   if(take_out) begin
    m_axis_tvalid<=font_valid;
    if(font_valid)begin
     m_axis_tdata<=font_band?(font_fg?font_color:(font_outline||font_distance_background)?C_BLACK:font_data):font_lamp_pixel;
     m_axis_tuser<=font_user;m_axis_tlast<=font_last;
    end
   end
   if(take_font)begin
    font_valid<=prep_valid;
    if(prep_valid)begin
     font_user<=prep_user;font_last<=prep_last;font_band<=prep_band;
     font_distance_background<=prep_distance_background;font_data<=prep_data;font_color<=prep_color;
     font_fg<=text_fg;font_outline<=text_outline;
     font_lamp_pixel<=prep_lamp_panel?lamp_pixel:prep_data;
    end
   end
   if(take_in)begin
    prep_valid<=s_axis_tvalid;
    if(s_axis_tvalid) begin
    prep_data<=composed_pixel;prep_user<=s_axis_tuser;prep_last<=s_axis_tlast;
    prep_lamp_panel<=lamp_panel;prep_lamp_selected<=lamp_selected;
    prep_lamp_dx<=lamp_dx;prep_lamp_dy<=lamp_dy;prep_lamp_color<=lamp_color;
    prep_band<=text_band||lamp_text;
    prep_distance_background<=text_band&&!line0&&px<312;prep_lamp_text<=lamp_text;
    prep_color<=lamp_text?(lamp_selected?C_WHITE:24'hd0d7de):text_color;
    prep_glyph<=lamp_text?lamp_glyph:glyph;
    prep_row<=lamp_text?lamp_ty[4:0]:grow;
    prep_bit<=lamp_text?5'd31-lamp_tx[4:0]:5'd23-gx;
    if(s_axis_tuser) begin
     if((x_q!=0 || y_q!=0) && frame_error_count!=16'hffff) frame_error_count<=frame_error_count+1'b1;
     active_risk<=state_risk_level;active_stop<=state_stop;active_locked<=state_locked;
     active_distance_valid<=state_distance_valid;active_speed_valid<=state_speed_valid;
     active_distance<=state_distance_mm;active_speed<=state_speed_q16;
    end
    if(s_axis_tlast) begin
     if(px!=WIDTH-1 && frame_error_count!=16'hffff) frame_error_count<=frame_error_count+1'b1;
     x_q<=0;y_q<=(py==HEIGHT-1)?0:py+1'b1;
    end else begin x_q<=px+1'b1;y_q<=py;end
   end
   end
  end
 end
endmodule
`resetall
