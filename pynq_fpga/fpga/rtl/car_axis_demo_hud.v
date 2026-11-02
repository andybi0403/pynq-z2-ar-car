// Four-row native PL HUD. All data commits only at accepted SOF.
// Display-only consumer: no feedback into control or sensor freshness.
`resetall
`timescale 1ns/1ps
`default_nettype none
module car_axis_demo_hud #(
 parameter integer WIDTH=1280,HEIGHT=720
)(
 input wire clk,rst,
 input wire [23:0] s_axis_tdata,input wire s_axis_tvalid,output wire s_axis_tready,
 input wire s_axis_tuser,s_axis_tlast,
 output reg [23:0] m_axis_tdata,output reg m_axis_tvalid,input wire m_axis_tready,
 output reg m_axis_tuser,m_axis_tlast,
 input wire [11:0] state_distance_mm,input wire state_distance_valid,
 input wire state_car_valid,state_car_locked,
 input wire [1:0] state_ir,input wire state_ir_valid,
 output reg [31:0] committed_frames
);
 localparam integer SCALE=(WIDTH==640&&HEIGHT==360)?2:1;
 reg [15:0] x,y;
 wire [15:0] hx=(s_axis_tuser?16'd0:x)*SCALE;
 wire [15:0] hy=(s_axis_tuser?16'd0:y)*SCALE;
 wire out_take=!m_axis_tvalid||m_axis_tready;
 reg prep_valid,prep_user,prep_last,prep_overlay;
 reg [23:0] prep_data;
 reg [5:0] prep_glyph;reg [4:0] prep_row,prep_bit;
 wire take=!prep_valid||out_take;
 assign s_axis_tready=take;
 reg dv,cv,locked,iv;reg [1:0] ir;
 reg [27:0] conversion;reg [3:0] count;reg converting;
 wire [15:0] bcd=conversion[27:12];
 reg [15:0] adjusted;integer i;
 always @(*)begin
  adjusted=bcd;
  for(i=0;i<4;i=i+1)if(bcd[i*4+:4]>4)adjusted[i*4+:4]=bcd[i*4+:4]+4'd3;
 end
 wire [27:0] next_conversion={adjusted,conversion[11:0]}<<1;
 reg [1:0] row;reg [4:0] ty;reg band;
 always @(*)begin
  row=0;ty=0;band=0;
  if(hy>=40&&hy<64)begin row=0;ty=hy-40;band=1;end
  else if(hy>=80&&hy<104)begin row=1;ty=hy-80;band=1;end
  else if(hy>=120&&hy<144)begin row=2;ty=hy-120;band=1;end
  else if(hy>=160&&hy<184)begin row=3;ty=hy-160;band=1;end
 end
 wire [15:0] cells;
 genvar n;
 generate for(n=0;n<16;n=n+1)begin: columns
  assign cells[n]=(hx>=24+n*24)&&(hx<48+n*24);
 end endgenerate
 wire [3:0] col={|(cells&16'hff00),|(cells&16'hf0f0),|(cells&16'hcccc),|(cells&16'haaaa)};
 wire [4:0] gx=hx[4:0]-{~col[1:0],3'b000};
 reg [5:0] glyph;
 always @(*)begin
  glyph=11;
  case(row)
   0:case(col)
    0:glyph=16;1:glyph=17;2:glyph=18;3:glyph=19;4:glyph=12;
    6:glyph=!dv?6'd10:bcd[15:12]==0?6'd11:{2'b0,bcd[15:12]};
    7:glyph=!dv?6'd10:bcd[15:8]==0?6'd11:{2'b0,bcd[11:8]};
    8:glyph=dv?{2'b0,bcd[7:4]}:6'd11;
    9:glyph=dv?6'd13:6'd11;10:glyph=dv?{2'b0,bcd[3:0]}:6'd11;
    12:glyph=14;13:glyph=15;default:glyph=11;
   endcase
   1:case(col)
    0:glyph=20;1:glyph=21;2:glyph=22;3:glyph=23;4:glyph=12;
    6:glyph=!cv?6'd10:locked?6'd20:6'd21;7:glyph=cv?6'd11:6'd10;
    default:glyph=11;
   endcase
   default:case(col)
    0:glyph=23;1:glyph=24;2:glyph=row==2?6'd25:6'd26;3:glyph=17;
    4:glyph=27;5:glyph=28;6:glyph=12;
    8:glyph=!iv?6'd10:ir[row==2?0:1]?6'd31:6'd29;
    9:glyph=!iv?6'd10:ir[row==2?0:1]?6'd32:6'd30;
    default:glyph=11;
   endcase
  endcase
 end
 reg [47:0] font[0:2047];
 initial $readmemh("font_24x24_demo.mem",font);
 wire [47:0] bits=font[{prep_glyph,prep_row}];
 wire foreground=bits[24+prep_bit],outline=bits[prep_bit];
 always @(posedge clk)begin
  if(rst)begin
   x<=0;y<=0;dv<=0;cv<=0;locked<=1;iv<=0;ir<=0;
   conversion<=0;count<=0;converting<=0;committed_frames<=0;
   prep_valid<=0;prep_user<=0;prep_last<=0;prep_overlay<=0;
   prep_data<=0;prep_glyph<=11;prep_row<=0;prep_bit<=0;
   m_axis_tvalid<=0;m_axis_tdata<=0;m_axis_tuser<=0;m_axis_tlast<=0;
  end else begin
   if(out_take)begin
    m_axis_tvalid<=prep_valid;
    if(prep_valid)begin
     m_axis_tdata<=prep_overlay?(foreground?24'hffffff:outline?24'h101010:prep_data):prep_data;
     m_axis_tuser<=prep_user;m_axis_tlast<=prep_last;
    end
   end
   if(take)begin
    prep_valid<=s_axis_tvalid;
    if(s_axis_tvalid)begin
     prep_data<=s_axis_tdata;prep_user<=s_axis_tuser;prep_last<=s_axis_tlast;
     prep_glyph<=glyph;prep_row<=ty;prep_bit<=23-gx;
     prep_overlay<=band&&hx>=24&&hx<360;
     if(s_axis_tlast)begin x<=0;y<=hy/SCALE==HEIGHT-1?0:(hy/SCALE)+1'b1;end
     else begin x<=(s_axis_tuser?16'd0:x)+1'b1;y<=s_axis_tuser?16'd0:y;end
    end
   end
   if(take&&s_axis_tvalid&&s_axis_tuser)begin
    dv<=state_distance_valid;cv<=state_car_valid;locked<=state_car_locked;
    iv<=state_ir_valid;ir<=state_ir;
    conversion<={16'b0,state_distance_mm};count<=0;converting<=1;
    committed_frames<=committed_frames+1'b1;
   end else if(converting)begin
    conversion<=next_conversion;count<=count+1'b1;
    if(count==11)converting<=0;
   end
  end
 end
endmodule
`resetall
