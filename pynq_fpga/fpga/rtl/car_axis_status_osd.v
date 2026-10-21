// Additional status rows. All state commits at an accepted SOF; no feedback
// into risk/control. L is actual fresh STM32 LOCK, F denotes unavailable.
`resetall
`timescale 1ns/1ps
`default_nettype none
module car_axis_status_osd #(
 parameter integer WIDTH=640,parameter integer HEIGHT=480
)(
 input wire clk,input wire rst,
 input wire [23:0] s_axis_tdata,input wire s_axis_tvalid,output wire s_axis_tready,
 input wire s_axis_tuser,input wire s_axis_tlast,
 output reg [23:0] m_axis_tdata,output reg m_axis_tvalid,input wire m_axis_tready,
 output reg m_axis_tuser,output reg m_axis_tlast,
 input wire signed [63:0] state_displacement_q16,input wire [63:0] state_path_q16,
 input wire state_odometry_valid,input wire [15:0] state_reasons,
 input wire state_car_valid,input wire state_car_locked,input wire [15:0] state_car_fault,
 input wire signed [31:0] state_speed_q16,input wire state_speed_valid,
 output reg [31:0] committed_frames
);
 reg prep_valid,prep_user,prep_last,prep_overlay,prep_healthy;
 reg [23:0] prep_data;reg [5:0] prep_glyph;reg [4:0] prep_row,prep_bit;
 wire out_take=!m_axis_tvalid||m_axis_tready;
 wire take=!prep_valid||out_take;
 assign s_axis_tready=take;
 reg [15:0] x,y;
 wire [15:0] px=s_axis_tuser?16'd0:x,py=s_axis_tuser?16'd0:y;
 reg [15:0] reasons,car_fault;
 reg car_valid,car_locked,odo_valid,net_negative;
 reg [1:0] direction;
 reg [31:0] path_bcd,net_bcd;
 reg [63:0] conversion;
 reg [31:0] net_binary;
 reg [5:0] counter;
 reg [1:0] stage;
 wire [63:0] net_abs=state_displacement_q16[63] ? -state_displacement_q16 : state_displacement_q16;
 wire range_ok=state_path_q16[63:16]<=48'd99999999 && net_abs[63:16]<=48'd99999999;
 function [31:0] dabble(input [31:0] bcd);
  reg [31:0] result;integer i;
  begin result=bcd;
   for(i=0;i<8;i=i+1)if(result[i*4+:4]>4)result[i*4+:4]=result[i*4+:4]+4'd3;
   dabble=result;
  end
 endfunction
 wire [63:0] next_conversion={dabble(conversion[63:32]),conversion[31:0]}<<1;
 reg [47:0] font[0:2047];
 initial $readmemh("font_24x24_hud.mem",font);
 reg [2:0] row;reg [15:0] ty;reg row_band;
 always @(*) begin
  row=0;ty=0;row_band=0;
  if(py>=104&&py<128)begin row=0;ty=py-104;row_band=1;end
  else if(py>=136&&py<160)begin row=1;ty=py-136;row_band=1;end
  else if(py>=168&&py<192)begin row=2;ty=py-168;row_band=1;end
  else if(py>=200&&py<224)begin row=3;ty=py-200;row_band=1;end
  else if(py>=232&&py<256)begin row=4;ty=py-232;row_band=1;end
  else if(py>=264&&py<288)begin row=5;ty=py-264;row_band=1;end
 end
 wire band=row_band&&px>=24&&px<408;
 // Decode the sixteen bounded 24px cells with parallel comparisons. A
 // constant divider followed by the BCD selector was the critical path.
 wire [15:0] cell_select;
 genvar cell_index;
 generate for(cell_index=0;cell_index<16;cell_index=cell_index+1)begin: cells
  localparam [8:0] CELL_START=24+cell_index*24,CELL_END=48+cell_index*24;
  assign cell_select[cell_index]=px[8:0]>=CELL_START&&px[8:0]<CELL_END;
 end endgenerate
 wire [3:0] column;
 assign column[0]=|(cell_select&16'haaaa);
 assign column[1]=|(cell_select&16'hcccc);
 assign column[2]=|(cell_select&16'hf0f0);
 assign column[3]=|(cell_select&16'hff00);
 // Cell origins modulo 32 are 24,16,8,0. In the active cell the modular
 // subtraction is exactly its 0..23 pixel offset, with no divider.
 wire [4:0] gx=px[4:0]-{~column[1:0],3'b000};
 reg [5:0] glyph;reg healthy;
 function [5:0] hexglyph(input [3:0] value);
  begin case(value)
   10:hexglyph=6'd20;11:hexglyph=6'd21;12:hexglyph=6'd22;
   13:hexglyph=6'd23;14:hexglyph=6'd24;15:hexglyph=6'd25;
   default:hexglyph={2'b0,value};
  endcase end
 endfunction
 always @(*) begin
  glyph=6'd11;healthy=1;
  case(row)
   0:begin
    healthy=odo_valid;
    case(column)
    0:glyph=6'd30;
    1:glyph=6'd31;
    2:glyph=6'd12;
    3:glyph=6'd11;
     13,14:glyph=6'd15;
     default:if(column>=4&&column<=11)glyph=odo_valid?{2'b0,path_bcd[(11-column)*4+:4]}:
       column==4?6'd43:column==5?6'd44:6'd11;
    endcase
   end
   1:begin
    healthy=odo_valid;
    case(column)
    0:glyph=6'd32;
    1:glyph=6'd33;
    2:glyph=6'd12;
    3:glyph=6'd11;
     4:glyph=!odo_valid?6'd43:net_negative?6'd10:6'd13;
     14,15:glyph=6'd15;
     default:if(column>=5&&column<=12)glyph=odo_valid?{2'b0,net_bcd[(12-column)*4+:4]}:
       column==5?6'd44:6'd11;
    endcase
   end
   2:begin
    case(column)
    0:glyph=6'd34;
    1:glyph=6'd35;
    2:glyph=6'd36;
    3:glyph=6'd12;
    4:glyph=6'd11;
    5:glyph=6'd0;
    6:glyph=6'd19;
     default:if(column>=7&&column<=10)glyph=hexglyph(reasons[(10-column)*4+:4]);
    endcase
   end
   3:begin
    healthy=car_valid;
    case(column)
    0:glyph=6'd37;
    1:glyph=6'd38;
    2:glyph=6'd12;
    3:glyph=6'd11;
     4:glyph=!car_valid?6'd43:car_locked?6'd50:6'd51;
     5:glyph=car_valid?6'd11:6'd44;
     default:glyph=6'd11;
    endcase
   end
   4:begin
    healthy=car_valid;
    case(column)
    0:glyph=6'd39;
    1:glyph=6'd40;
    2:glyph=6'd36;
    3:glyph=6'd12;
    4:glyph=6'd11;
     5:glyph=car_valid?6'd0:6'd43;
     6:glyph=car_valid?6'd19:6'd44;
     default:if(column>=7&&column<=10)glyph=car_valid?hexglyph(car_fault[(10-column)*4+:4]):6'd11;
    endcase
   end
   5:begin
    healthy=direction!=3;
    case(column)
    0:glyph=6'd41;
    1:glyph=6'd42;
    2:glyph=6'd12;
    3:glyph=6'd11;
     4:glyph=direction==0?6'd49:direction==1?6'd47:direction==2?6'd48:6'd43;
     5:glyph=direction==3?6'd44:6'd11;
     default:glyph=6'd11;
    endcase
   end
   default:begin glyph=6'd11;healthy=0;end
  endcase
 end
 wire [47:0] word=font[{prep_glyph,prep_row}];
 wire [23:0] font_foreground=word[47:24];
 wire foreground=font_foreground[prep_bit];
 wire outline=word[prep_bit];
 always @(posedge clk)begin
  if(rst)begin
   x<=0;y<=0;m_axis_tvalid<=0;m_axis_tdata<=0;m_axis_tuser<=0;m_axis_tlast<=0;
   reasons<=0;car_fault<=0;car_valid<=0;car_locked<=1;odo_valid<=0;net_negative<=0;
   direction<=3;path_bcd<=0;net_bcd<=0;conversion<=0;net_binary<=0;counter<=0;stage<=2;
   committed_frames<=0;
   prep_valid<=0;prep_user<=0;prep_last<=0;prep_overlay<=0;prep_healthy<=0;
   prep_data<=0;prep_glyph<=13;prep_row<=0;prep_bit<=0;
  end else begin
   if(out_take)begin
    m_axis_tvalid<=prep_valid;
    if(prep_valid)begin
     m_axis_tdata<=prep_overlay ? (foreground?(prep_healthy?24'hffffff:24'he0e0e0):outline?24'h101010:prep_data) : prep_data;
     m_axis_tuser<=prep_user;m_axis_tlast<=prep_last;
    end
   end
   if(take)begin
    prep_valid<=s_axis_tvalid;
    if(s_axis_tvalid)begin
     prep_data<=s_axis_tdata;prep_glyph<=glyph;prep_row<=ty[4:0];prep_bit<=5'd23-gx;
     prep_overlay<=band&&stage==2;prep_healthy<=healthy;
     prep_user<=s_axis_tuser;prep_last<=s_axis_tlast;
     if(s_axis_tlast)begin x<=0;y<=py==HEIGHT-1?0:py+1'b1;end
     else begin x<=px+1'b1;y<=py;end
    end
   end
   if(take&&s_axis_tvalid&&s_axis_tuser)begin
    committed_frames<=committed_frames+1'b1;
    reasons<=state_reasons;car_valid<=state_car_valid;car_locked<=state_car_locked;car_fault<=state_car_fault;
    odo_valid<=state_odometry_valid&&range_ok;net_negative<=state_displacement_q16[63];
    direction<=!state_speed_valid?3:state_speed_q16==0?0:state_speed_q16[31]?2:1;
    conversion<={32'b0,state_path_q16[47:16]};net_binary<=net_abs[47:16];
    counter<=0;stage<=0;
   end else if(stage!=2)begin
    conversion<=next_conversion;counter<=counter+1'b1;
    if(counter==31)begin
     counter<=0;
     if(stage==0)begin path_bcd<=next_conversion[63:32];conversion<={32'b0,net_binary};stage<=1;end
     else begin net_bcd<=next_conversion[63:32];stage<=2;end
    end
   end
  end
 end
endmodule
`resetall
