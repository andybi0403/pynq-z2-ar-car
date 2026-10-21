`timescale 1ns / 1ps

module tb_car_qei;

localparam CLK_PERIOD = 10;   // 100MHz

reg clk = 0, rst = 1;
reg qei0_a = 0, qei0_b = 0, qei1_a = 0, qei1_b = 0;

// AXI-Lite
reg  [11:0] awaddr; reg [2:0] awprot = 0; reg awvalid = 0; wire awready;
reg  [31:0] wdata;  reg [3:0] wstrb = 4'hF; reg wvalid = 0; wire wready;
wire [1:0]  bresp;  wire bvalid; reg bready = 1;
reg  [11:0] araddr; reg [2:0] arprot = 0; reg arvalid = 0; wire arready;
wire [31:0] rdata;  wire [1:0] rresp; wire rvalid; reg rready = 1;

integer errors = 0, checks = 0;

car_qei_top dut (
    .clk(clk), .rst(rst),
    .qei0_a(qei0_a), .qei0_b(qei0_b),
    .qei1_a(qei1_a), .qei1_b(qei1_b),
    .s_axil_awaddr(awaddr), .s_axil_awprot(awprot), .s_axil_awvalid(awvalid), .s_axil_awready(awready),
    .s_axil_wdata(wdata), .s_axil_wstrb(wstrb), .s_axil_wvalid(wvalid), .s_axil_wready(wready),
    .s_axil_bresp(bresp), .s_axil_bvalid(bvalid), .s_axil_bready(bready),
    .s_axil_araddr(araddr), .s_axil_arprot(arprot), .s_axil_arvalid(arvalid), .s_axil_arready(arready),
    .s_axil_rdata(rdata), .s_axil_rresp(rresp), .s_axil_rvalid(rvalid), .s_axil_rready(rready)
);

always #(CLK_PERIOD/2) clk = ~clk;

// AXI handshake is sampled at the active clock edge; deassert on next negedge.
task automatic axil_write(input [11:0] addr,input [31:0] data,
 input integer aw_delay=0,input integer w_delay=0,input integer b_delay=0,input [3:0] strb=15);
 begin
 @(negedge clk); awaddr=addr;wdata=data;wstrb=strb;bready=0;
 fork
 begin repeat(aw_delay) @(negedge clk);awvalid=1;do @(posedge clk);while(!awready);@(negedge clk);awvalid=0;end
 begin repeat(w_delay) @(negedge clk);wvalid=1;do @(posedge clk);while(!wready);@(negedge clk);wvalid=0;end
 join
 repeat(b_delay) @(negedge clk);
 bready=1;do @(posedge clk);while(!bvalid);
 @(negedge clk);bready=0;
 end
endtask
task automatic axil_read(input [11:0] addr,output [31:0] data,input integer r_delay=0);
 begin
 @(negedge clk); araddr=addr;arvalid=1;rready=0;
 do @(posedge clk);while(!arready);
 @(negedge clk);arvalid=0;
 repeat(r_delay) @(negedge clk);
 rready=1;do @(posedge clk);while(!rvalid);
 data=rdata;@(negedge clk);rready=0;
 end
endtask
task automatic check(input [255:0] name, input [31:0] got, input [31:0] exp);
    begin
        checks = checks + 1;
        if (got !== exp) begin
            errors = errors + 1;
            $display("[FAIL] %0s: got=%08h exp=%08h @%0t", name, got, exp, $time);
        end else
            $display("[ok]   %0s = %08h", name, got);
    end
endtask


task automatic ticks(input integer count);
 repeat(count) @(negedge clk);
endtask
integer phase0=0,phase1=0;
task automatic step0(input integer direction,input integer interval=1000);
 begin
 phase0=(phase0+(direction>0?1:3))%4;
 case(phase0)
 0:{qei0_a,qei0_b}=0;1:{qei0_a,qei0_b}=2;2:{qei0_a,qei0_b}=3;3:{qei0_a,qei0_b}=1;
 endcase
 ticks(interval);
 end
endtask
task automatic step1(input integer direction,input integer interval=1000);
 begin
 phase1=(phase1+(direction>0?1:3))%4;
 case(phase1)
 0:{qei1_a,qei1_b}=0;1:{qei1_a,qei1_b}=2;2:{qei1_a,qei1_b}=3;3:{qei1_a,qei1_b}=1;
 endcase
 ticks(interval);
 end
endtask
reg [31:0] rd,held,seq0,stamp;
integer i;
initial begin
 ticks(5);rst=0;ticks(10);
 axil_read('h000,rd);check("version",rd,'hC4250405);
 axil_write('h168,65536); // simulated 1 mm/count, not a real motor calibration
 axil_write('h17c,65536);
 axil_write('h170,20000);axil_write('h184,20000);
 step0(1);check("first edge invalid",dut.v0_valid,0);
 step0(1);check("T method 100000 mm/s saturate",dut.v0_q16,32'h7fffffff);
 // 10000 clocks => 10000 mm/s => Q16.16 655360000, computed from SI units.
 step0(1,10000);step0(1,10000);
 check("period exact",dut.q0_period,10000);
 check("T method absolute units",dut.v0_q16,655360000);
 step0(-1,10000);check("reverse first invalid",dut.v0_valid,0);
 step0(-1,10000);check("negative velocity",dut.v0_q16,-655360000);
 ticks(21000);check("stationary zero",dut.v0_q16,0);check("stationary valid",dut.v0_valid,1);
 // Frozen stationary observation timestamp must not be refreshed by reads.
 stamp=dut.v0_ts;ticks(1000);check("zero timestamp retained",dut.v0_ts,stamp);
 ticks(20000);check("new no-edge observation",dut.v0_ts!=stamp,1);
 axil_write('h168,0);ticks(10);check("unconfigured invalid",dut.v0_valid,0);
 axil_write('h168,65536);axil_write('h170,0);ticks(10);check("zero timeout invalid",dut.v0_valid,0);
 axil_write('h170,20000);axil_write('h16c,1);ticks(10);check("reserved shift invalid",dut.v0_valid,0);
 axil_write('h16c,0);
 // Independent channels, coincident publication and coherent snapshots.
 fork
 begin repeat(4) step0(1,10000);end
 begin repeat(4) step1(-1,10000);end
 join
 axil_write('h004,1);
 axil_read('h12c,rd);check("snapshot left",rd,655360000);
 axil_read('h144,rd);check("snapshot right",rd,-655360000);
 axil_read('h134,rd);check("snapshot valid bit31",rd[31],1);
 axil_read('h130,stamp);check("timestamp belongs to batch",stamp,dut.v0_ts);
 axil_read('h120,held);step0(1,10000);
 axil_read('h120,rd);check("shadow stable during motion",rd,held);
 axil_write('h004,1,0,0,0,0);axil_read('h120,rd);check("WSTRB zero ignores trigger",rd,held);
 // Decoder illegal transition does not count and invalidates period.
 held=dut.q0_pos;{qei0_a,qei0_b}=~{qei0_a,qei0_b};ticks(10);
 check("illegal no movement",dut.q0_pos,held);check("illegal diagnostic",dut.q0_ill,1);
 check("illegal period invalid",dut.q0_pvalid,0);
 // Reset at nonzero AB establishes baseline, no phantom count.
 rst=1;{qei0_a,qei0_b}=2;ticks(5);rst=0;ticks(15);
 check("nonzero startup count",dut.q0_pos,0);
 phase0=1;step0(-1,1000);check("position wraps negative",dut.q0_pos,32'hffffffff);
 step0(1,1000);check("position wraps positive",dut.q0_pos,0);
 axil_write('h164,20);ticks(50);held=dut.q0_pos;
 qei0_a=~qei0_a;ticks(4);qei0_a=~qei0_a;ticks(40);
 check("glitch no count",dut.q0_pos,held);check("glitch recorded",dut.q0_flt>0,1);
 // A sustained legal edge is accepted after filter window.
 step0(1,1000);check("filtered legal edge",dut.q0_pos,held+1);
 axil_write('h164,0);axil_write('h160,1);ticks(15);
 held=dut.q0_pos;step0(1,1000);check("direction invert",dut.q0_pos,held-1);
 // Saturated edge gap invalidates period rather than wrapping to high speed.
 @(negedge clk);dut.q0.gap=32'hffffffff;ticks(2);check("gap overflow invalid",dut.q0_pvalid,0);
 if(errors==0)$display("TEST PASSED (%0d checks)",checks);
 else $display("TEST FAILED (%0d errors / %0d checks)",errors,checks);
 $finish;
end
initial begin #10000000;$display("TEST FAILED watchdog");$finish;end
endmodule
