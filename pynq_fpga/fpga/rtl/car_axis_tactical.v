// Vehicle-local sensor schematic. Regions are not calibrated sensor FOVs.
// Streaming overlay only; no complete-frame buffer or control output.
`resetall
`timescale 1ns/1ps
`default_nettype none
module car_axis_tactical #(
 parameter integer WIDTH=1280,HEIGHT=720
)(
 input wire clk,rst,
 input wire [23:0] s_axis_tdata,input wire s_axis_tvalid,output wire s_axis_tready,
 input wire s_axis_tuser,s_axis_tlast,
 output reg [23:0] m_axis_tdata,output reg m_axis_tvalid,input wire m_axis_tready,
 output reg m_axis_tuser,m_axis_tlast,
 input wire state_enabled,state_filter_valid,input wire [11:0] state_distance_mm,
 input wire [1:0] state_sample_count,state_trend,input wire state_trend_valid,
 input wire [1:0] state_ir,input wire state_ir_valid
);
 reg [15:0] x,y;
 wire [15:0] px=s_axis_tuser?16'd0:x,py=s_axis_tuser?16'd0:y;
 reg enabled,dv,iv,tv;reg [1:0] ir,trend,samples;
 reg [23:0] front_color;
 localparam [23:0] GREEN=24'h00b870,YELLOW=24'hffd000,RED=24'hff3030,GRAY=24'h737d89;
 reg [27:0] conversion;reg [3:0] convert_count;reg converting;
 wire [15:0] bcd=conversion[27:12];reg [15:0] adjusted;integer i;
 always @(*)begin
  adjusted=bcd;
  for(i=0;i<4;i=i+1)if(bcd[i*4+:4]>4)adjusted[i*4+:4]=bcd[i*4+:4]+4'd3;
 end
 wire [27:0] next_conversion={adjusted,conversion[11:0]}<<1;
 wire out_take=!m_axis_tvalid||m_axis_tready;
 reg prep_valid,prep_user,prep_last;
 reg [23:0] prep_data;reg [5:0] prep_glyph;reg [4:0] prep_row,prep_bit;
 reg prep_text;
 wire take=!prep_valid||out_take;
 assign s_axis_tready=take;
 wire panel=enabled&&px>=992&&px<1272&&py>=368&&py<704;
 wire [8:0] red_dark={1'b0,s_axis_tdata[23:18]}+{1'b0,s_axis_tdata[23:19]}+9'd8;
 wire [8:0] green_dark={1'b0,s_axis_tdata[15:10]}+{1'b0,s_axis_tdata[15:11]}+9'd8;
 wire [8:0] blue_dark={1'b0,s_axis_tdata[7:2]}+{1'b0,s_axis_tdata[7:3]}+9'd8;
 wire [23:0] dark={red_dark[7:0],green_dark[7:0],blue_dark[7:0]};
 // Raster recurrences replace constant multipliers on the pixel critical path.
 // Projection = a*x+b*y+c. Advance by a on an accepted pixel, by b on EOL.
 // 24 signed bits cover the complete 16-bit coordinate range without overflow.
 localparam signed [23:0] LA0=-24'sd9256,LN0=-24'sd42666,
                           RA0=-24'sd42816,RN0=-24'sd20726;
 reg signed [23:0] la,ln,ra,rn,la_row,ln_row,ra_row,rn_row;
 wire signed [23:0] left_along=s_axis_tuser?LA0:la;
 wire signed [23:0] left_normal=s_axis_tuser?LN0:ln;
 wire signed [23:0] right_along=s_axis_tuser?RA0:ra;
 wire signed [23:0] right_normal=s_axis_tuser?RN0:rn;
 wire signed [23:0] current_la_row=s_axis_tuser?LA0:la_row;
 wire signed [23:0] current_ln_row=s_axis_tuser?LN0:ln_row;
 wire signed [23:0] current_ra_row=s_axis_tuser?RA0:ra_row;
 wire signed [23:0] current_rn_row=s_axis_tuser?RN0:rn_row;
 always @(posedge clk)begin
  if(rst)begin
   la<=LA0;ln<=LN0;ra<=RA0;rn<=RN0;
   la_row<=LA0;ln_row<=LN0;ra_row<=RA0;rn_row<=RN0;
  end else if(take&&s_axis_tvalid)begin
   if(s_axis_tlast)begin
    la<=current_la_row-24'sd28;ln<=current_ln_row+24'sd23;
    ra<=current_ra_row+24'sd28;rn<=current_rn_row-24'sd23;
    la_row<=current_la_row-24'sd28;ln_row<=current_ln_row+24'sd23;
    ra_row<=current_ra_row+24'sd28;rn_row<=current_rn_row-24'sd23;
   end else begin
    la<=left_along+24'sd23;ln<=left_normal+24'sd28;
    ra<=right_along+24'sd23;rn<=right_normal+24'sd28;
    if(s_axis_tuser)begin la_row<=LA0;ln_row<=LN0;ra_row<=RA0;rn_row<=RN0;end
   end
  end
 end
 // Exact 4px/cm silhouette: rear 78px, nose 32px, 80px straight + 28px taper.
 wire lower_inside=py>=592&&py<672&&px>=1093&&px<1171;
 wire upper_inside=py>=564&&py<592&&left_normal>=1554&&right_normal<=-1554;
 wire body=lower_inside||upper_inside;
 wire body_edge=body&&(py<566||py>=670||(lower_inside&&(px<1095||px>=1169))||
                                   (upper_inside&&(left_normal<1610||right_normal>-1610)));
 wire wheels=((px>=1085&&px<1093)||(px>=1171&&px<1179))&&
             ((py>=606&&py<624)||(py>=646&&py<664));
 // Obstacle indication bars: long edges parallel to the corresponding body edge.
 // The taper has direction (23,-28) on the left and (23,28) on the right.
 // Orthogonal integer projections avoid trigonometry and preserve exact parallelism.
 wire front_zone=px>=1104&&px<1160&&py>=520&&py<530;
 wire left_zone=left_along>=-1050&&left_along<=1050&&left_normal>=-200&&left_normal<=200;
 wire right_zone=right_along>=-1050&&right_along<=1050&&right_normal>=-200&&right_normal<=200;
 wire ir_left_icon=px>=1099&&px<1111&&py>=572&&py<584;
 wire ir_right_icon=px>=1154&&px<1166&&py>=572&&py<584;
 wire ultrasonic=((px>=1118&&px<1129)||(px>=1135&&px<1146))&&py>=560&&py<570;
 wire forward_arrow=(px>=1131&&px<1133&&py>=612&&py<636)||
                    (py>=602&&py<612&&px>=1132-(py-602)&&px<=1132+(py-602));
 reg [23:0] colored;
 always @(*)begin
  colored=s_axis_tdata;
  if(panel)begin
   colored=dark;
   if(front_zone)colored=front_color;
   if(left_zone||ir_left_icon)colored=!iv?GRAY:ir[0]?RED:GREEN;
   if(right_zone||ir_right_icon)colored=!iv?GRAY:ir[1]?RED:GREEN;
   if(wheels)colored=GRAY;
   if(body_edge||forward_arrow)colored=24'hffffff;
   if(ultrasonic)colored=24'h83cfff;
  end
 end
 wire [10:0] cells;
 genvar n;
 generate for(n=0;n<11;n=n+1)begin: text_cells
  assign cells[n]=px>=1008+n*24&&px<1032+n*24;
 end endgenerate
 // Explicit priority-free one-hot encoder; bit masks are indices 0..10.
 wire [3:0] text_col={|(cells&11'h700),|(cells&11'h0f0),|(cells&11'h4cc),|(cells&11'h2aa)};
 wire [4:0] gx=(px-1008)-text_col*24;
 reg [5:0] glyph;reg [4:0] row;reg text_active;
 always @(*)begin
  glyph=11;row=0;text_active=0;
  if(panel&&px>=1008&&px<1272)begin
   if(py>=380&&py<404)begin
    row=py-380;text_active=text_col<4;
    case(text_col)0:glyph=35;1:glyph=36;2:glyph=28;3:glyph=37;default:glyph=11;endcase
   end else if(py>=420&&py<444)begin
    row=py-420;text_active=1;
    case(text_col)
     0:glyph=39;1:glyph=40;
     3:glyph=!dv?6'd10:bcd[15:12]==0?6'd11:{2'b0,bcd[15:12]};
     4:glyph=!dv?6'd10:bcd[15:8]==0?6'd11:{2'b0,bcd[11:8]};
     5:glyph=dv?{2'b0,bcd[7:4]}:6'd11;
     6:glyph=dv?6'd13:6'd11;7:glyph=dv?{2'b0,bcd[3:0]}:6'd11;
     9:glyph=14;10:glyph=15;default:glyph=11;
    endcase
   end else if(py>=452&&py<476)begin
    row=py-452;text_active=text_col>=3&&text_col<6;
    if(!dv||!tv)begin
     if(samples!=0)case(text_col)3:glyph=47;4:glyph=48;5:glyph=49;default:glyph=11;endcase
     else case(text_col)3:glyph=45;4:glyph=46;default:glyph=11;endcase
    end else case(text_col)
     3:glyph=trend==1?6'd43:trend==2?6'd41:6'd42;
     4:glyph=trend==1?6'd44:trend==2?6'd32:6'd19;default:glyph=11;
    endcase
   end
  end
 end
 reg [47:0] font[0:2047];initial $readmemh("font_24x24_demo.mem",font);
 wire [47:0] word=font[{prep_glyph,prep_row}];
 wire foreground=word[24+prep_bit],outline=word[prep_bit];
 always @(posedge clk)begin
  if(rst)begin
   x<=0;y<=0;enabled<=0;dv<=0;iv<=0;tv<=0;ir<=0;trend<=0;samples<=0;
   front_color<=GRAY;conversion<=0;convert_count<=0;converting<=0;
   prep_valid<=0;prep_user<=0;prep_last<=0;prep_data<=0;prep_glyph<=11;prep_row<=0;prep_bit<=0;prep_text<=0;
   m_axis_tvalid<=0;m_axis_tdata<=0;m_axis_tuser<=0;m_axis_tlast<=0;
  end else begin
   if(out_take)begin
    m_axis_tvalid<=prep_valid;
    if(prep_valid)begin
     m_axis_tdata<=prep_text?(foreground?24'hffffff:outline?24'h101010:prep_data):prep_data;
     m_axis_tuser<=prep_user;m_axis_tlast<=prep_last;
    end
   end
   if(take)begin
    prep_valid<=s_axis_tvalid;
    if(s_axis_tvalid)begin
     prep_data<=colored;prep_glyph<=glyph;prep_row<=row;prep_bit<=23-gx;prep_text<=text_active;
     prep_user<=s_axis_tuser;prep_last<=s_axis_tlast;
     if(s_axis_tlast)begin x<=0;y<=py==HEIGHT-1?0:py+1'b1;end
     else begin x<=px+1'b1;y<=py;end
    end
   end
   if(take&&s_axis_tvalid&&s_axis_tuser)begin
    enabled<=state_enabled;dv<=state_filter_valid;iv<=state_ir_valid;tv<=state_trend_valid;
    ir<=state_ir;trend<=state_trend;samples<=state_sample_count;
    front_color<=!state_filter_valid?GRAY:state_distance_mm<=250?RED:state_distance_mm<=350?YELLOW:GREEN;
    conversion<={16'b0,state_distance_mm};convert_count<=0;converting<=1;
   end else if(converting)begin
    conversion<=next_conversion;convert_count<=convert_count+1'b1;
    if(convert_count==11)converting<=0;
   end
  end
 end
endmodule
`resetall
