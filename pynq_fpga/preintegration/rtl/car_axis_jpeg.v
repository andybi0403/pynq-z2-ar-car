// Full-resolution RGB -> JPEG transport. Encoder has no output READY, so a
// bounded BRAM FIFO absorbs stalls. Overflow invalidates the entire packet.
// A reserved 32-byte trailer always terminates even a damaged packet; the host
// verifies identity, geometry, byte count, and flags before publishing JPEG.
`timescale 1ns/1ps
`default_nettype none
module car_axis_jpeg #(
 parameter integer VIDEO_WIDTH=1280,VIDEO_HEIGHT=720,FIFO_LOG2=15
)(
 (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 aclk CLK", X_INTERFACE_PARAMETER="XIL_INTERFACENAME aclk, ASSOCIATED_BUSIF S_AXI:S_AXIS:M_AXIS, ASSOCIATED_RESET aresetn, FREQ_HZ 100000000" *) input wire aclk,
 (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 aresetn RST", X_INTERFACE_PARAMETER="XIL_INTERFACENAME aresetn, POLARITY ACTIVE_LOW" *) input wire aresetn,
 input wire [31:0] frame_id,input wire frame_valid,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS TDATA", X_INTERFACE_PARAMETER="XIL_INTERFACENAME S_AXIS, TDATA_NUM_BYTES 3, TUSER_WIDTH 1, HAS_TLAST 1, FREQ_HZ 100000000" *) input wire [23:0] s_axis_tdata,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS TVALID" *) input wire s_axis_tvalid,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS TREADY" *) output wire s_axis_tready,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS TUSER" *) input wire s_axis_tuser,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS TLAST" *) input wire s_axis_tlast,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 M_AXIS TDATA", X_INTERFACE_PARAMETER="XIL_INTERFACENAME M_AXIS, TDATA_NUM_BYTES 1, HAS_TKEEP 1, HAS_TLAST 1, FREQ_HZ 100000000" *) output wire [7:0] m_axis_tdata,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 M_AXIS TVALID" *) output wire m_axis_tvalid,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 M_AXIS TREADY" *) input wire m_axis_tready,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 M_AXIS TKEEP" *) output wire [0:0] m_axis_tkeep,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 M_AXIS TLAST" *) output wire m_axis_tlast,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI AWADDR", X_INTERFACE_PARAMETER="XIL_INTERFACENAME S_AXI, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 5, FREQ_HZ 100000000" *) input wire [4:0] s_axi_awaddr,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *) input wire s_axi_awvalid,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *) output wire s_axi_awready,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WDATA" *) input wire [31:0] s_axi_wdata,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *) input wire [3:0] s_axi_wstrb,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WVALID" *) input wire s_axi_wvalid,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WREADY" *) output wire s_axi_wready,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI BRESP" *) output wire [1:0] s_axi_bresp,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI BVALID" *) output wire s_axi_bvalid,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI BREADY" *) input wire s_axi_bready,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *) input wire [4:0] s_axi_araddr,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *) input wire s_axi_arvalid,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *) output wire s_axi_arready,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RDATA" *) output wire [31:0] s_axi_rdata,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RRESP" *) output wire [1:0] s_axi_rresp,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RVALID" *) output wire s_axi_rvalid,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RREADY" *) input wire s_axi_rready
);
 localparam integer DEPTH=1<<FIFO_LOG2;
 wire encoder_ready,jpeg_valid,jpeg_last,soft_reset;
 wire [7:0] jpeg_data;
 wire reset=!aresetn||soft_reset;
 reg busy,input_done,metadata_ok,overflow,geometry_error;
 reg [31:0] accepted_id,jpeg_bytes,frame_counter;
 reg [15:0] x,y;
 reg trailer_active;reg [5:0] trailer_index;
 wire allow_input=!input_done&&(!s_axis_tuser||!busy);
 assign s_axis_tready=encoder_ready&&allow_input;
 wire input_fire=s_axis_tvalid&&s_axis_tready;
 mjpegzero_enc_top #(.LITE_MODE(0),.RGB_INPUT(1),.IMG_WIDTH(VIDEO_WIDTH),.IMG_HEIGHT(VIDEO_HEIGHT)) encoder(
  .clk(aclk),.rst_n(aresetn),.session_soft_reset(soft_reset),
  .s_axis_vid_tdata(s_axis_tdata),.s_axis_vid_tvalid(s_axis_tvalid&&allow_input),.s_axis_vid_tready(encoder_ready),
  .s_axis_vid_tuser(s_axis_tuser),.s_axis_vid_tlast(s_axis_tlast),
  .m_axis_jpg_tdata(jpeg_data),.m_axis_jpg_tvalid(jpeg_valid),.m_axis_jpg_tlast(jpeg_last),
  .s_axi_awaddr(s_axi_awaddr),.s_axi_awvalid(s_axi_awvalid),.s_axi_awready(s_axi_awready),
  .s_axi_wdata(s_axi_wdata),.s_axi_wstrb(s_axi_wstrb),.s_axi_wvalid(s_axi_wvalid),.s_axi_wready(s_axi_wready),
  .s_axi_bresp(s_axi_bresp),.s_axi_bvalid(s_axi_bvalid),.s_axi_bready(s_axi_bready),
  .s_axi_araddr(s_axi_araddr),.s_axi_arvalid(s_axi_arvalid),.s_axi_arready(s_axi_arready),
  .s_axi_rdata(s_axi_rdata),.s_axi_rresp(s_axi_rresp),.s_axi_rvalid(s_axi_rvalid),.s_axi_rready(s_axi_rready));

 // Trailer: eight little-endian words. Magic "CJPG", ABI=1, accepted
 // input frame ID, flags (valid/overflow/geometry), JPEG length, W, H, count.
 reg [31:0] trailer_word;
 always @* begin
  case(trailer_index[5:2])
   0:trailer_word=32'h47504a43;
   1:trailer_word=1;
   2:trailer_word=accepted_id;
   3:trailer_word={29'd0,geometry_error,overflow,metadata_ok};
   4:trailer_word=jpeg_bytes;
   5:trailer_word=VIDEO_WIDTH;
   6:trailer_word=VIDEO_HEIGHT;
   default:trailer_word=frame_counter;
  endcase
 end
 wire [7:0] trailer_byte=trailer_word>>(8*trailer_index[1:0]);
 (* ram_style="block" *) reg [8:0] fifo[0:DEPTH-1];
 reg [FIFO_LOG2-1:0] wr_ptr,rd_ptr;
 reg [FIFO_LOG2:0] used;
 reg [8:0] output_word;reg output_valid;
 assign m_axis_tdata=output_word[7:0];assign m_axis_tlast=output_word[8];
 assign m_axis_tvalid=output_valid;assign m_axis_tkeep=1'b1;
 wire pop=(!output_valid||m_axis_tready)&&(used!=0);
 // Reserve the complete trailer before allowing any payload byte into RAM.
 wire payload_push=jpeg_valid&&!trailer_active&&(used<DEPTH-32);
 wire trailer_push=trailer_active&&(used<DEPTH);
 wire push=payload_push||trailer_push;
 wire packet_done=output_valid&&m_axis_tready&&output_word[8];
 always @(posedge aclk) begin
  if(reset) begin
   wr_ptr<=0;rd_ptr<=0;used<=0;output_valid<=0;output_word<=0;
  end else begin
   case({push,pop})
    2'b10:used<=used+1'b1;
    2'b01:used<=used-1'b1;
    default:used<=used;
   endcase
   if(push) begin
    fifo[wr_ptr]<=trailer_push?{trailer_index==31,trailer_byte}:{1'b0,jpeg_data};
    wr_ptr<=wr_ptr+1'b1;
   end
   if(!output_valid||m_axis_tready) begin
    output_valid<=pop;
    if(pop) begin output_word<=fifo[rd_ptr];rd_ptr<=rd_ptr+1'b1;end
   end
  end
 end
 always @(posedge aclk) begin
  if(reset) begin
   busy<=0;input_done<=0;metadata_ok<=0;overflow<=0;geometry_error<=0;
   accepted_id<=0;jpeg_bytes<=0;frame_counter<=0;x<=0;y<=0;trailer_active<=0;trailer_index<=0;
  end else begin
   if(packet_done) begin busy<=0;input_done<=0;end
   if(input_fire) begin
    if(s_axis_tuser) begin
     busy<=1;accepted_id<=frame_id;metadata_ok<=frame_valid;overflow<=0;geometry_error<=s_axis_tlast;
     jpeg_bytes<=0;x<=1;y<=0;
    end else begin
     if(!busy)geometry_error<=1;
     if(s_axis_tlast!=(x==VIDEO_WIDTH-1))geometry_error<=1;
     if(s_axis_tlast)begin
      x<=0;
      if(y==VIDEO_HEIGHT-1)input_done<=1;else y<=y+1'b1;
     end else x<=x+1'b1;
    end
   end
   if(jpeg_valid)begin
    jpeg_bytes<=jpeg_bytes+1'b1;
    if(!payload_push)overflow<=1;
    if(jpeg_last)begin
     trailer_active<=1;trailer_index<=0;frame_counter<=frame_counter+1'b1;
     if(!input_done)geometry_error<=1;
    end
   end
   if(trailer_push)begin
    if(trailer_index==31)trailer_active<=0;else trailer_index<=trailer_index+1'b1;
   end
  end
 end
endmodule
`default_nettype wire
