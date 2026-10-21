// Central forward-view Sobel overlay; display only, never a control input.
// Structure studied in erendn/sobel-pipeline-fpga (MIT, c765b9d058ce).
// Independently implemented AXIS flow control, RAM scheduling and annotation.
// Causal window ends at (x,y): its centre is (x-1,y-1), so the drawn edge
// has a documented one-pixel right/down phase. No whole-line video delay.
`resetall
`timescale 1ns/1ps
`default_nettype none
module car_axis_front_overlay #(
 parameter integer WIDTH=640, HEIGHT=480,
 parameter integer EDGE_THRESHOLD=160,
 parameter integer ROI_X0=WIDTH/4, ROI_X1=3*WIDTH/4,
 parameter integer ROI_Y0=HEIGHT/4, ROI_Y1=3*HEIGHT/4
)(
 input wire clk,input wire rst,
 input wire [23:0] s_axis_tdata,input wire s_axis_tvalid,output wire s_axis_tready,
 input wire s_axis_tuser,input wire s_axis_tlast,
 output reg [23:0] m_axis_tdata,output reg m_axis_tvalid,input wire m_axis_tready,
 output reg m_axis_tuser,output reg m_axis_tlast,
 input wire state_valid,input wire state_distance_valid,input wire [11:0] state_distance_mm,
 input wire [1:0] state_risk_level,input wire state_stop
);
 localparam [23:0] GREEN=24'h00d060,YELLOW=24'hffd000,RED=24'hff2020,FAULT=24'hd020ff;
 // Previous complete frame's gradient envelope anchors the annotation.
 // This is display geometry, not object detection or per-object ranging.
 reg seen_edges,anchor_valid;
 reg [15:0] min_edge_x,min_edge_y,label_x,label_y;
 reg [15:0] b_x,b_y,c_x,c_y;
 localparam integer LABEL_WIDTH=288;

 reg [15:0] x,y;
 wire [15:0] px=s_axis_tuser?16'd0:x,py=s_axis_tuser?16'd0:y;
 // A common clock-enable freezes all payload and neighbourhood stages.
 // Ready depends only on the registered output, with one pixel/clock II.
 wire step=!m_axis_tvalid||m_axis_tready;
 assign s_axis_tready=step;
 wire accept=step&&s_axis_tvalid;
 wire [9:0] grey_sum={2'b0,s_axis_tdata[23:16]}+
                         {1'b0,s_axis_tdata[15:8],1'b0}+{2'b0,s_axis_tdata[7:0]};
 wire [7:0] grey=grey_sum[9:2];
 (* ram_style="block" *) reg [7:0] line1[0:WIDTH-1];
 (* ram_style="block" *) reg [7:0] line2[0:WIDTH-1];
 reg a_valid,a_user,a_last;reg [15:0] a_x,a_y;
 reg [23:0] a_data,a_color;reg [7:0] a_top,a_mid,a_bot;
 reg [5:0] a_glyph;reg [4:0] a_row,a_bit;reg a_label;
 reg b_valid,b_user,b_last,b_roi,b_box,b_label;
 reg [23:0] b_data,b_color;
 reg signed [8:0] b_dx0,b_dx1,b_dx2,b_dy0,b_dy1,b_dy2;
 reg c_valid,c_user,c_last,c_roi,c_box,c_label;
 reg [23:0] c_data,c_color;reg signed [11:0] c_gx,c_gy;
 reg [5:0] c_glyph;reg [4:0] c_row,c_bit;
 reg [5:0] b_glyph;reg [4:0] b_row,b_bit;
 reg [7:0] t0,t1,m0,m1,d0,d1;
 reg [23:0] frame_color;reg frame_distance_valid;
 wire [23:0] incoming_color=GREEN; // Geometry color is independent of safety status.
 // Convert mm to decimal once per accepted SOF. Dropping the units digit
 // gives approximate centimetres without a divider on the pixel path.
 reg [27:0] conversion;reg [3:0] convert_count;reg converting;
 reg [11:0] cm_bcd;
 function [15:0] dabble(input [15:0] value);
  reg [15:0] temp;integer i;
  begin temp=value;for(i=0;i<4;i=i+1)
   if(temp[i*4+:4]>4)temp[i*4+:4]=temp[i*4+:4]+4'd3;
   dabble=temp;end
 endfunction
 wire [27:0] conversion_next={dabble(conversion[27:12]),conversion[11:0]}<<1;
 reg [47:0] font[0:2047];
 initial $readmemh("font_24x24_hud.mem",font);
 wire label=anchor_valid&&py>=label_y&&py<label_y+24&&px>=label_x&&px<label_x+LABEL_WIDTH;
 wire [15:0] tx=px-label_x,ty=py-label_y;
 // Twelve bounded 24px cells, decoded without a pixel-path divider.
 wire [11:0] label_cell;
 genvar label_index;
 generate for(label_index=0;label_index<12;label_index=label_index+1)begin: label_cells
  localparam [8:0] CELL_START=label_index*24,CELL_END=(label_index+1)*24;
  assign label_cell[label_index]=tx[8:0]>=CELL_START&&tx[8:0]<CELL_END;
 end endgenerate
 wire [3:0] column;
 assign column[0]=|(label_cell&12'haaa);
 assign column[1]=|(label_cell&12'hccc);
 assign column[2]=|(label_cell&12'h0f0);
 assign column[3]=|(label_cell&12'hf00);
 // 24*column modulo 32 equals -8*column. The active cell offset is 0..23.
 wire [1:0] gx_high=tx[4:3]+column[1:0];
 wire [4:0] gx={gx_high,tx[2:0]};
 reg [5:0] glyph;
 always @(*)begin
  glyph=6'd11;
  case(column)
    0:glyph=6'd45;
    1:glyph=6'd41;
    2:glyph=6'd46;
    3:glyph=6'd28;
    4:glyph=6'd12;
   5:glyph=frame_distance_valid?6'd14:6'd43;
   6:glyph=frame_distance_valid?{2'b0,cm_bcd[11:8]}:6'd44;
   7:glyph=frame_distance_valid?{2'b0,cm_bcd[7:4]}:6'd11;
   8:glyph=frame_distance_valid?{2'b0,cm_bcd[3:0]}:6'd11;
   10:glyph=6'd18;11:glyph=6'd15;
   default:glyph=6'd11;
  endcase
 end
 wire [47:0] font_word=font[{c_glyph,c_row}];
 wire [23:0] font_foreground=font_word[47:24];
 wire [11:0] abs_x=c_gx[11]?-c_gx:c_gx,abs_y=c_gy[11]?-c_gy:c_gy;
 wire [12:0] magnitude={1'b0,abs_x}+{1'b0,abs_y};
 // Read-first synchronous RAMs. The second row is written one stage later
 // using line1's registered output; no asynchronous RAM read for write data.
 always @(posedge clk)begin
  if(!rst&&step)begin
   if(s_axis_tvalid&&px<WIDTH)begin
    a_mid<=line1[px];a_top<=line2[px];line1[px]<=grey;
   end
   if(a_valid&&a_x<WIDTH)line2[a_x]<=a_mid;
  end
 end
 always @(posedge clk)begin
  if(rst)begin
   seen_edges<=0;anchor_valid<=0;min_edge_x<=WIDTH;min_edge_y<=HEIGHT;
   label_x<=ROI_X0;label_y<=ROI_Y0; b_x<=0;b_y<=0;c_x<=0;c_y<=0;
   x<=0;y<=0;a_valid<=0;b_valid<=0;m_axis_tvalid<=0;
   m_axis_tdata<=0;m_axis_tuser<=0;m_axis_tlast<=0;
   a_user<=0;a_last<=0;a_x<=0;a_y<=0;a_data<=0;a_color<=FAULT;a_bot<=0;
   a_glyph<=13;a_row<=0;a_bit<=0;a_label<=0;
   b_user<=0;b_last<=0;b_roi<=0;b_box<=0;b_label<=0;b_data<=0;b_color<=FAULT;
   b_dx0<=0;b_dx1<=0;b_dx2<=0;b_dy0<=0;b_dy1<=0;b_dy2<=0;
   c_valid<=0;c_user<=0;c_last<=0;c_roi<=0;c_box<=0;c_label<=0;
   c_data<=0;c_color<=FAULT;c_gx<=0;c_gy<=0;c_glyph<=13;c_row<=0;c_bit<=0;
   b_glyph<=13;b_row<=0;b_bit<=0;
   t0<=0;t1<=0;m0<=0;m1<=0;d0<=0;d1<=0;
   frame_color<=FAULT;frame_distance_valid<=0;cm_bcd<=0;
   conversion<=0;convert_count<=0;converting<=0;
  end else begin
   if(accept&&s_axis_tuser)begin
    frame_color<=incoming_color;frame_distance_valid<=state_valid&&state_distance_valid;
    conversion<={16'd0,state_distance_mm};convert_count<=0;converting<=1;cm_bcd<=0;
   end else if(converting)begin
    conversion<=conversion_next;convert_count<=convert_count+1'b1;
    if(convert_count==11)begin cm_bcd<=conversion_next[27:16];converting<=0;end
   end
   if(step&&c_valid)begin
    if(c_user)begin
     anchor_valid<=seen_edges;
     label_x<=min_edge_x>WIDTH-LABEL_WIDTH?WIDTH-LABEL_WIDTH:min_edge_x;
     label_y<=min_edge_y>=28?min_edge_y-28:0;
     seen_edges<=0;min_edge_x<=WIDTH;min_edge_y<=HEIGHT;
    end else if(c_roi&&magnitude>=EDGE_THRESHOLD)begin
     seen_edges<=1;
     if(c_x<min_edge_x)min_edge_x<=c_x;
     if(c_y<min_edge_y)min_edge_y<=c_y;
    end
   end
   if(step)begin
    m_axis_tvalid<=c_valid;
    if(c_valid)begin
     m_axis_tuser<=c_user;m_axis_tlast<=c_last;
     m_axis_tdata<=c_label?(font_foreground[c_bit]?c_color:24'h101010):
                      (c_roi&&magnitude>=EDGE_THRESHOLD)?c_color:c_data;
    end
    // Split RAM-to-Sobel carry chains: six differences, then weighted sums.
    c_valid<=b_valid;
    if(b_valid)begin
     c_data<=b_data;c_user<=b_user;c_last<=b_last;c_color<=b_color;
     c_glyph<=b_glyph;c_row<=b_row;c_bit<=b_bit;c_label<=b_label;
     c_roi<=b_roi;c_box<=0;c_x<=b_x;c_y<=b_y;
     c_gx<=$signed({{3{b_dx0[8]}},b_dx0})+
           ($signed({{3{b_dx1[8]}},b_dx1})<<<1)+$signed({{3{b_dx2[8]}},b_dx2});
     c_gy<=$signed({{3{b_dy0[8]}},b_dy0})+
           ($signed({{3{b_dy1[8]}},b_dy1})<<<1)+$signed({{3{b_dy2[8]}},b_dy2});
    end
    b_valid<=a_valid;
    if(a_valid)begin
     b_data<=a_data;b_user<=a_user;b_last<=a_last;b_color<=a_color;
     b_glyph<=a_glyph;b_row<=a_row;b_bit<=a_bit;b_label<=a_label;
     b_roi<=a_x>=ROI_X0+2&&a_x<ROI_X1-2&&a_y>=ROI_Y0+2&&a_y<ROI_Y1-2;
     b_box<=0;b_x<=a_x;b_y<=a_y;
     b_dx0<=$signed({1'b0,a_top})-$signed({1'b0,t0});
     b_dx1<=$signed({1'b0,a_mid})-$signed({1'b0,m0});
     b_dx2<=$signed({1'b0,a_bot})-$signed({1'b0,d0});
     b_dy0<=$signed({1'b0,t0})-$signed({1'b0,d0});
     b_dy1<=$signed({1'b0,t1})-$signed({1'b0,d1});
     b_dy2<=$signed({1'b0,a_top})-$signed({1'b0,a_bot});
     // No previous-row shift history may enter the new row's window.
     if(a_x==0)begin t0<=0;t1<=a_top;m0<=0;m1<=a_mid;d0<=0;d1<=a_bot;end
     else begin t0<=t1;t1<=a_top;m0<=m1;m1<=a_mid;d0<=d1;d1<=a_bot;end
    end
    a_valid<=s_axis_tvalid;
    if(s_axis_tvalid)begin
     a_data<=s_axis_tdata;a_bot<=grey;a_user<=s_axis_tuser;a_last<=s_axis_tlast;
     a_x<=px;a_y<=py;a_color<=s_axis_tuser?incoming_color:frame_color;
     a_glyph<=glyph;a_row<=ty[4:0];a_bit<=5'd23-gx;a_label<=label&&!converting;
     if(s_axis_tlast)begin x<=0;y<=py==HEIGHT-1?0:py+1'b1;end
     else begin x<=px+1'b1;y<=py;end
    end
   end
  end
 end
endmodule
`resetall
