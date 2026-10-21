// Board-level bridge for the v0.9 production candidates.  It keeps one AXI
// slave in car_perception_top and inserts the pure AXIS OSD in the HDMI path.
// Fresh STM32 state is published by the sole host MMIO owner. Missing/stale
// UART feedback is explicitly invalid, never replaced by a PL STOP proxy.
`resetall
`timescale 1ns/1ps
`default_nettype none
module car_board_video_wrapper(
 (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK", X_INTERFACE_PARAMETER = "XIL_INTERFACENAME aclk, ASSOCIATED_BUSIF S_AXI:S_AXIS:M_AXIS, ASSOCIATED_RESET aresetn, FREQ_HZ 100000000" *) input wire aclk,
 (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST", X_INTERFACE_PARAMETER = "XIL_INTERFACENAME aresetn, POLARITY ACTIVE_LOW" *) input wire aresetn,
 input wire us_echo,output wire us_trig,input wire ir_l_raw,input wire ir_r_raw,
 input wire qei0_a,input wire qei0_b,input wire qei1_a,input wire qei1_b,
 output wire qei_oe_n,

 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWADDR", X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXI, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 12, FREQ_HZ 100000000" *) input wire [11:0] s_axi_awaddr,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWPROT" *) input wire [2:0] s_axi_awprot,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *) input wire s_axi_awvalid,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *) output wire s_axi_awready,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WDATA" *) input wire [31:0] s_axi_wdata,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *) input wire [3:0] s_axi_wstrb,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WVALID" *) input wire s_axi_wvalid,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WREADY" *) output wire s_axi_wready,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *) output wire [1:0] s_axi_bresp,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *) output wire s_axi_bvalid,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *) input wire s_axi_bready,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *) input wire [11:0] s_axi_araddr,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *) input wire [2:0] s_axi_arprot,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *) input wire s_axi_arvalid,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *) output wire s_axi_arready,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RDATA" *) output wire [31:0] s_axi_rdata,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RRESP" *) output wire [1:0] s_axi_rresp,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RVALID" *) output wire s_axi_rvalid,
 (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RREADY" *) input wire s_axi_rready,

 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TDATA", X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXIS, TDATA_NUM_BYTES 3, TUSER_WIDTH 1, HAS_TLAST 1, FREQ_HZ 100000000" *) input wire [23:0] s_axis_tdata,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TVALID" *) input wire s_axis_tvalid,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TREADY" *) output wire s_axis_tready,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TUSER" *) input wire s_axis_tuser,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TLAST" *) input wire s_axis_tlast,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TDATA", X_INTERFACE_PARAMETER = "XIL_INTERFACENAME M_AXIS, TDATA_NUM_BYTES 3, TUSER_WIDTH 1, HAS_TLAST 1, FREQ_HZ 100000000" *) output wire [23:0] m_axis_tdata,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TVALID" *) output wire m_axis_tvalid,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TREADY" *) input wire m_axis_tready,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TUSER" *) output wire m_axis_tuser,
 (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TLAST" *) output wire m_axis_tlast
);
 wire rst=!aresetn;
 wire risk_stop;wire [1:0] risk_level;wire [15:0] risk_reasons;
 wire [11:0] distance_mm;wire distance_valid;wire [31:0] speed_q16;wire speed_valid;
 wire [15:0] osd_frame_errors;
 wire signed [63:0] displacement_q16;wire [63:0] path_q16;wire odometry_valid;
 wire car_valid,car_locked;wire [15:0] car_fault;wire [31:0] display_frames;
 wire [23:0] front_data;wire front_valid,front_ready,front_user,front_last;
 wire [23:0] base_data;wire base_valid,base_ready,base_user,base_last;
 wire [23:0] tagged_data;wire tagged_valid,tagged_ready,tagged_user,tagged_last;
 reg [23:0] pixel_data;reg pixel_valid,pixel_user,pixel_last;wire pixel_ready;
 // Cut the 18-way prefix mux from the font lookup combinational path.
 assign tagged_ready=!pixel_valid||pixel_ready;
 always @(posedge aclk) begin
  if(rst) begin pixel_valid<=0;pixel_data<=0;pixel_user<=0;pixel_last<=0;end
  else if(tagged_ready) begin
   pixel_valid<=tagged_valid;
   if(tagged_valid) begin pixel_data<=tagged_data;pixel_user<=tagged_user;pixel_last<=tagged_last;end
  end
 end
 wire metadata_valid;wire [31:0] metadata_id,metadata_speed;
 wire [15:0] metadata_epoch,metadata_reasons,header_errors;
 wire [63:0] live_ticks,metadata_ticks,metadata_path;
 wire signed [63:0] metadata_displacement;
 wire [11:0] metadata_distance;wire metadata_dv,metadata_sv,metadata_ov;
 wire [1:0] metadata_risk;wire metadata_stop;
 // The window fits in one low word. Match the high words (including the
 // low-word borrow) instead of carrying a 64-bit subtraction through the
 // OSD pixel mux. Explicitly reject a high-word overflow/future timestamp.
 // This is combinational at actual SOF acceptance: backpressure cannot
 // preserve a previously sampled freshness bit beyond its 200 ms window.
 function recent_frame;
  input [63:0] now_value,stamp;
  reg [32:0] low_delta;
  reg high_match;
  begin
   low_delta={1'b0,now_value[31:0]}-{1'b0,stamp[31:0]};
   high_match=low_delta[32] ?
    (stamp[63:32]!=32'hffffffff && now_value[63:32]==stamp[63:32]+32'd1) :
    (now_value[63:32]==stamp[63:32]);
   recent_frame=high_match && low_delta[31:0]<32'd20_000_000;
  end
 endfunction
 wire metadata_fresh=metadata_valid && recent_frame(live_ticks,metadata_ticks);
// Commit historical validity once, at the front-stage accepted SOF.
 // Downstream stalls must not make different display rows disagree.
 reg [31:0] accepted_id,tag_count,repeats;
 reg [63:0] accepted_ticks,accepted_sof;reg [15:0] accepted_epoch;reg accepted_valid,accepted_fresh;
 wire [63:0] accepted_age=live_ticks>=accepted_ticks ? live_ticks-accepted_ticks:64'hffffffffffffffff;
 wire [31:0] accepted_age32=|accepted_age[63:32]?32'hffffffff:accepted_age[31:0];
 wire [31:0] accepted_state={accepted_epoch,14'd0,
  (accepted_valid&&accepted_age<64'd20_000_000),accepted_valid};
 always @(posedge aclk) begin
  if(rst) begin accepted_id<=0;accepted_ticks<=0;accepted_sof<=0;accepted_epoch<=0;accepted_valid<=0;accepted_fresh<=0;tag_count<=0;repeats<=0;end
  else if(pixel_valid&&pixel_ready&&pixel_user) begin
   accepted_id<=metadata_id;accepted_ticks<=metadata_ticks;accepted_epoch<=metadata_epoch;
   accepted_sof<=live_ticks;
   accepted_valid<=metadata_valid;accepted_fresh<=metadata_fresh;tag_count<=tag_count+1'b1;
   if(metadata_valid&&accepted_valid&&metadata_id==accepted_id&&metadata_ticks==accepted_ticks)
    repeats<=repeats+1'b1;
  end
 end

 // SN74LVC245A /OE is externally pulled up to 3.3V.  Before configuration
 // that resistor keeps every QEI output high-impedance; after configuration
 // the synchronized peripheral reset keeps the shifter disabled until this
 // wrapper is ready.  /OE is active low, so normal operation drives it low.
 assign qei_oe_n = ~aresetn;

 car_perception_top perception(
  .clk(aclk),.rst(rst),.us_echo(us_echo),.us_trig(us_trig),.ir_l_raw(ir_l_raw),.ir_r_raw(ir_r_raw),
  .qei0_a(qei0_a),.qei0_b(qei0_b),.qei1_a(qei1_a),.qei1_b(qei1_b),
  .risk_stop_o(risk_stop),.risk_level_o(risk_level),.risk_reasons_o(risk_reasons),
  .osd_distance_mm_o(distance_mm),.osd_distance_valid_o(distance_valid),
  .osd_speed_q16_o(speed_q16),.osd_speed_valid_o(speed_valid),
  .osd_displacement_q16_o(displacement_q16),.osd_path_q16_o(path_q16),
  .osd_odometry_valid_o(odometry_valid),.osd_car_valid_o(car_valid),
  .osd_car_locked_o(car_locked),.osd_car_fault_o(car_fault),
  .osd_errors_i(osd_frame_errors),.osd_frames_i(display_frames),
  .osd_live_ticks_o(live_ticks),.display_frame_id_i(accepted_id),.display_frame_state_i(accepted_state),
  .display_frame_ticks_i(accepted_ticks),.display_header_errors_i(header_errors),
  .display_frame_sof_i(accepted_sof),
  .display_repeats_i(repeats),.display_tag_count_i(tag_count),.display_frame_age_i(accepted_age32),
  .s_axil_awaddr(s_axi_awaddr),.s_axil_awprot(s_axi_awprot),.s_axil_awvalid(s_axi_awvalid),.s_axil_awready(s_axi_awready),
  .s_axil_wdata(s_axi_wdata),.s_axil_wstrb(s_axi_wstrb),.s_axil_wvalid(s_axi_wvalid),.s_axil_wready(s_axi_wready),
  .s_axil_bresp(s_axi_bresp),.s_axil_bvalid(s_axi_bvalid),.s_axil_bready(s_axi_bready),
  .s_axil_araddr(s_axi_araddr),.s_axil_arprot(s_axi_arprot),.s_axil_arvalid(s_axi_arvalid),.s_axil_arready(s_axi_arready),
  .s_axil_rdata(s_axi_rdata),.s_axil_rresp(s_axi_rresp),.s_axil_rvalid(s_axi_rvalid),.s_axil_rready(s_axi_rready));

 car_axis_frame_metadata metadata(
  .clk(aclk),.rst(rst),.s_axis_tdata(s_axis_tdata),.s_axis_tvalid(s_axis_tvalid),.s_axis_tready(s_axis_tready),
  .s_axis_tuser(s_axis_tuser),.s_axis_tlast(s_axis_tlast),.m_axis_tdata(tagged_data),.m_axis_tvalid(tagged_valid),
  .m_axis_tready(tagged_ready),.m_axis_tuser(tagged_user),.m_axis_tlast(tagged_last),
  .metadata_valid(metadata_valid),.frame_id(metadata_id),.snapshot_epoch(metadata_epoch),.frame_pl_ticks(metadata_ticks),
  .distance_mm(metadata_distance),.distance_valid(metadata_dv),.speed_q16(metadata_speed),.speed_valid(metadata_sv),
  .displacement_q16(metadata_displacement),.path_q16(metadata_path),.odometry_valid(metadata_ov),
  .risk_level(metadata_risk),.risk_stop(metadata_stop),.risk_reasons(metadata_reasons),.header_errors(header_errors));
 car_axis_front_overlay front_overlay(
  .clk(aclk),.rst(rst),.s_axis_tdata(pixel_data),.s_axis_tvalid(pixel_valid),.s_axis_tready(pixel_ready),
  .s_axis_tuser(pixel_user),.s_axis_tlast(pixel_last),.m_axis_tdata(front_data),.m_axis_tvalid(front_valid),
  .m_axis_tready(front_ready),.m_axis_tuser(front_user),.m_axis_tlast(front_last),
  .state_valid(metadata_fresh),.state_distance_valid(metadata_dv),.state_distance_mm(metadata_distance),
  .state_risk_level(metadata_risk),.state_stop(metadata_stop));
 car_axis_osd #(.WIDTH(640),.HEIGHT(480),.ENABLE_TEXT(1)) osd(
  .clk(aclk),.rst(rst),.s_axis_tdata(front_data),.s_axis_tvalid(front_valid),.s_axis_tready(front_ready),
  .s_axis_tuser(front_user),.s_axis_tlast(front_last),.m_axis_tdata(base_data),.m_axis_tvalid(base_valid),
  .m_axis_tready(base_ready),.m_axis_tuser(base_user),.m_axis_tlast(base_last),
  .state_risk_level(risk_level),.state_stop(risk_stop),.state_locked(!car_valid||car_locked),
  .state_distance_valid(accepted_fresh&&metadata_dv),.state_speed_valid(accepted_fresh&&metadata_sv),.state_distance_mm(metadata_distance),
  .state_speed_q16(metadata_speed),.frame_error_count(osd_frame_errors));
 car_axis_status_osd #(.WIDTH(640),.HEIGHT(480)) status_osd(
  .clk(aclk),.rst(rst),.s_axis_tdata(base_data),.s_axis_tvalid(base_valid),.s_axis_tready(base_ready),
  .s_axis_tuser(base_user),.s_axis_tlast(base_last),.m_axis_tdata(m_axis_tdata),.m_axis_tvalid(m_axis_tvalid),
  .m_axis_tready(m_axis_tready),.m_axis_tuser(m_axis_tuser),.m_axis_tlast(m_axis_tlast),
  .state_displacement_q16(metadata_displacement),.state_path_q16(metadata_path),.state_odometry_valid(accepted_fresh&&metadata_ov),
  .state_reasons(accepted_fresh?metadata_reasons:16'hffff),.state_car_valid(car_valid),.state_car_locked(car_locked),.state_car_fault(car_fault),
  .state_speed_q16(metadata_speed),.state_speed_valid(accepted_fresh&&metadata_sv),.committed_frames(display_frames));
endmodule
`resetall
