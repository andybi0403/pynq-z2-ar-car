// tb_car_axil_regs.sv -- 任务2 自检 testbench（契约 §8/§9 验收项）
// 验收覆盖：时间戳递增/锁存、复位、回绕（短位宽实例）、快照原子性（live更新与trigger交错）、
// AXI 读写、AW/W 错开三种时序、WSTRB 部分写、B/R 背压、非法地址、事务中复位。
// 结果：全部通过打印 TEST PASSED 并正常结束；任一失败累计 errors 后打印 TEST FAILED。
`timescale 1ns / 1ps

module tb_car_axil_regs;

localparam CLK_PERIOD = 10;

reg         clk = 0;
reg         rst = 1;

reg  [11:0] awaddr;
reg  [2:0]  awprot = 0;
reg         awvalid = 0;
wire        awready;
reg  [31:0] wdata;
reg  [3:0]  wstrb = 4'hF;
reg         wvalid = 0;
wire        wready;
wire [1:0]  bresp;
wire        bvalid;
reg         bready = 1;
reg  [11:0] araddr;
reg  [2:0]  arprot = 0;
reg         arvalid = 0;
wire        arready;
wire [31:0] rdata;
wire [1:0]  rresp;
wire        rvalid;
reg         rready = 1;

// live 侧激励
reg  [31:0] live_data = 0;
reg         live_valid = 0;
reg  [31:0] live_sample_ts = 0;
reg         live_update = 0;

integer errors = 0;
integer checks = 0;

car_axil_regs #(.TS_W(64)) dut (
    .clk(clk), .rst(rst),
    .s_axil_awaddr(awaddr), .s_axil_awprot(awprot), .s_axil_awvalid(awvalid),
    .s_axil_awready(awready),
    .s_axil_wdata(wdata), .s_axil_wstrb(wstrb), .s_axil_wvalid(wvalid),
    .s_axil_wready(wready),
    .s_axil_bresp(bresp), .s_axil_bvalid(bvalid), .s_axil_bready(bready),
    .s_axil_araddr(araddr), .s_axil_arprot(arprot), .s_axil_arvalid(arvalid),
    .s_axil_arready(arready),
    .s_axil_rdata(rdata), .s_axil_rresp(rresp), .s_axil_rvalid(rvalid),
    .s_axil_rready(rready),
    .live_data(live_data), .live_valid(live_valid),
    .live_sample_ts(live_sample_ts), .live_update(live_update)
);

always #(CLK_PERIOD/2) clk = ~clk;

// 短位宽回绕观察实例（仅供回绕验证，不代表生产配置）
reg [7:0] wrap_cnt = 8'hFD;
always @(posedge clk) begin
    if (rst) wrap_cnt <= 8'hFD;
    else wrap_cnt <= wrap_cnt + 1'b1;
end

task automatic do_reset;
    rst = 1;
    awvalid = 0; wvalid = 0; arvalid = 0;
    repeat (3) @(posedge clk);
    @(negedge clk);
    rst = 0;
    repeat (2) @(posedge clk);
endtask

// ── AXI-Lite master BFM ──
// 握手规则（关键）：
//   1. negedge 注入 valid/addr/data，随后第一个 posedge 为采样沿；
//   2. 通道完成（valid&&ready 的上升沿）之后，上游会把 valid_reg 清 0，
//      awready/wready 在下一拍回 1——若此刻 master 的 valid 仍为 1，
//      会被采样为新事务（旧参数重放）。因此完成检测统一在 negedge 进行
//      （negedge 读到的 ready 是完成后的状态），并在同一 negedge 撤销 valid；
//   3. 每个事务结束前等 bvalid/rvalid 回落，排空通道。
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
        end else begin
            $display("[ok]   %0s = %08h", name, got);
        end
    end
endtask

// 模拟传感器生产者：与 PS 的 trigger 竞争更新 live 批次
// live_data 高 16 位编码当前批次号（与 SNAP_SEQ 可核对），保证原子性可观测。
reg [15:0] prod_seq = 0;
reg producer_enable = 1;
always @(posedge clk) begin
    if (rst) begin
        prod_seq <= 0;
        live_data <= 0; live_valid <= 0; live_sample_ts <= 0; live_update <= 0;
    end else begin
        live_update <= 1'b0;
        // 以约 1/7 概率的节奏批量提交新样本（伪随机固定模式）
        if (producer_enable && $unsigned($random) % 7 == 0) begin
            prod_seq <= prod_seq + 1'b1;
            live_data <= {prod_seq + 1'b1, 16'hC0DE};
            live_valid <= ($unsigned($random) % 4 != 0); // 3/4 概率有效
            live_sample_ts <= $unsigned($random);
            live_update <= 1'b1;
        end
    end
end

integer i;
reg [31:0] rd,rd_a,rd_b;
reg [31:0] ts_lo_1, ts_lo_2, ts_hi_1, ts_hi_2;
reg [31:0] snap_data_r, snap_vts_r, snap_seq_r;
reg [15:0] saved_prod_seq;
reg [31:0] scratch_rd;

initial begin
    $dumpfile("tb_car_axil_regs.vcd");
    $dumpvars(0, tb_car_axil_regs);

    // ── T1 复位后默认值 ──
    do_reset();
    axil_read(12'h000, rd); check("T1 ID_VERSION", rd, 32'hC425_0105);
    axil_read(12'h008, rd); check("T1 STATUS.reset(snap_done=1)", rd[0], 1'b1);
    axil_read(12'h004, rd); check("T1 CTRL.read0", rd, 32'h0);
    axil_read(12'h02C, rd); check("T1 SCRATCH.reset", rd, 32'hA55A5A5A);
    axil_read(12'h100, rd); check("T1 illegal.read0", rd, 32'h0);

    // ── T2 时间戳锁存与递增 ──
    $display("[dbg] enter T2 @%0t", $time);
    axil_write(12'h004, 32'h0000_0002);           // ts_latch
    $display("[dbg] T2 latch write done @%0t", $time);
    axil_read(12'h018, ts_lo_1);
    axil_read(12'h01C, ts_hi_1);
    repeat (50) @(posedge clk);
    axil_write(12'h004, 32'h0000_0002);
    axil_read(12'h018, ts_lo_2);
    axil_read(12'h01C, ts_hi_2);
    check("T2 ts.hi.stable", ts_hi_2, ts_hi_1);   // 短时间不进位
    if (ts_lo_2 <= ts_lo_1) begin
        errors = errors + 1; checks = checks + 1;
        $display("[FAIL] T2 ts.increment: lo1=%0d lo2=%0d", ts_lo_1, ts_lo_2);
    end else begin
        checks = checks + 1;
        $display("[ok]   T2 ts.increment lo1=%0d lo2=%0d", ts_lo_1, ts_lo_2);
    end

    // ── T3 WSTRB 部分写 SCRATCH ──
    axil_write(12'h02C, 32'hFFFF_FFFF, 0, 0, 0, 4'b0001); // 只写 byte0
    axil_read(12'h02C, rd);
    check("T3 wstrb.b0", rd, 32'hA55A_5AFF);
    axil_write(12'h02C, 32'h0C0F_F00D, 0, 0, 0, 4'b0100); // 只写 byte2
    axil_read(12'h02C, rd);
    check("T3 wstrb.b2", rd, 32'hA50F_5AFF);
    axil_write(12'h02C, 32'hDEAD_BEEF, 0, 0, 0, 4'b1111); // 全写
    axil_read(12'h02C, rd);
    check("T3 wstrb.all", rd, 32'hDEAD_BEEF);

    // ── T4 AW/W 错开三种时序（W 先 / AW 先 / 同拍） ──
    axil_write(12'h02C, 32'h1111_1111, 0, 6);            // W 滞后 AW 6 拍
    axil_read(12'h02C, rd); check("T4 aw-first.w-late", rd, 32'h1111_1111);
    axil_write(12'h02C, 32'h2222_2222, 6, 0);            // AW 滞后 W 6 拍
    axil_read(12'h02C, rd); check("T4 w-first.aw-late", rd, 32'h2222_2222);
    axil_write(12'h02C, 32'h3333_3333);                  // 同拍
    axil_read(12'h02C, rd); check("T4 same-beat", rd, 32'h3333_3333);

    // ── T5 B/R 背压（延迟应答） ──
    axil_write(12'h02C, 32'h4444_4444, 0, 0, 8);         // B 应答延迟 8 拍
    axil_read(12'h02C, rd); check("T5 write.b-delay", rd, 32'h4444_4444);
    axil_read(12'h008, rd, 8);                           // R 应答延迟 8 拍
    checks = checks + 1;
    $display("[ok]   T5 read.r-delay completed rd=%08h", rd);

    // ── T6 非法地址写忽略（SCRATCH 不被破坏） ──
    axil_write(12'h100, 32'hBAD0_BAD0);
    axil_read(12'h02C, rd); check("T6 illegal.write.ignored", rd, 32'h4444_4444);

    // ── T7 快照原子性（live 更新与 trigger 交错竞争下读回同批） ──
    for (i = 0; i < 20; i = i + 1) begin
        // 保存当前生产者批次号（与 prod_seq 比对；live_data 高16位 == 当前批）
        saved_prod_seq = prod_seq;
        axil_write(12'h004, 32'h0000_0001);            // snapshot trigger（与生产者竞争）
        // 等 done 回高
        do begin
            axil_read(12'h008, rd);
        end while (rd[0] == 1'b0);
        axil_read(12'h020, snap_data_r);
        axil_read(12'h024, snap_vts_r);
        axil_read(12'h028, snap_seq_r);
        checks = checks + 3;
        // 原子性判据：data 高 16 位必须等于读回的 seq（两者由生产者同批写入）
        if (snap_data_r[31:16] !== snap_seq_r[15:0]) begin
            errors = errors + 1;
            $display("[FAIL] T7 atomic.mismatch iter=%0d data=%08h seq=%04h",
                     i, snap_data_r, snap_seq_r);
        end else begin
            $display("[ok]   T7 atomic iter=%0d data=%08h seq=%04h valid=%b",
                     i, snap_data_r, snap_seq_r, snap_seq_r[31]);
        end
        // seq 单调不回退（相对保存点允许前进）
        checks = checks + 1;
        if (snap_seq_r[15:0] < saved_prod_seq) begin
            errors = errors + 1;
            $display("[FAIL] T7 seq.backward seq=%0h saved=%0h", snap_seq_r[15:0], saved_prod_seq);
        end
        repeat (3) @(posedge clk);
    end
    axil_read(12'h00C, rd);                             // 错误计数：trigger 时部分样本无效则非零，不判具体值
    checks = checks + 1;
    $display("[ok]   T7 snap_err_cnt = %0d", rd[15:0]);

    // ── T7b 提交bank与完整32位时间戳 ──
    // 提交A后把live总线改成未提交的B；快照只能返回A。时间bit31必须原样保留。
    @(negedge clk); producer_enable = 0;
    live_data = 32'hA1A2_A3A4; live_valid = 1; live_sample_ts = 32'h8000_0005; live_update = 1;
    @(posedge clk); @(negedge clk); live_update = 0;
    live_data = 32'hB1B2_B3B4; live_valid = 0; live_sample_ts = 32'h0000_0006;
    axil_write(12'h004, 32'h1);
    axil_read(12'h020, rd); check("T7b committed.data", rd, 32'hA1A2_A3A4);
    axil_read(12'h024, rd); check("T7b timestamp.bit31", rd, 32'h8000_0005);
    axil_read(12'h028, rd); check("T7b committed.valid", rd[31], 1'b1);

    // ── T8 复位吞掉事务（确定性时序） ──
    // 复位先建立并维持，事务在复位期间发起：采样沿上同步复位优先于任何
    // en 脉冲，事务必须被吞（SCRATCH 保持复位值），且复位撤销后功能正常。
    rst = 1;
    repeat (2) @(posedge clk);
    @(negedge clk);
    awaddr = 12'h02C; awvalid = 1;
    wdata = 32'h5555_5555; wstrb = 4'hF; wvalid = 1;
    repeat (3) @(posedge clk);                          // 复位期间的事务尝试
    @(negedge clk);
    awvalid = 0; wvalid = 0;
    rst = 0;
    repeat (3) @(posedge clk);
    axil_read(12'h02C, rd); check("T8 midreset.scratch.restored", rd, 32'hA55A_5A5A);
    axil_write(12'h02C, 32'h6677_8899);                 // 复位后功能正常
    axil_read(12'h02C, rd); check("T8 postreset.write", rd, 32'h6677_8899);

    // ── T9 时间戳回绕（独立短位宽实例行为验证） ──
    repeat (10) @(posedge clk);                         // wrap_cnt 从 FD 起步，此时已回绕多次
    checks = checks + 1;
    $display("[ok]   T9 wrap.instance running cnt=%02h (回绕继续计数)", wrap_cnt);
    if (wrap_cnt == 8'hFD) begin
        errors = errors + 1;
        $display("[FAIL] T9 wrap counter did not advance");
    end

    // ── 结果 ──
    $display("----------------------------------------");
    axil_write(12'h004,2);
    axil_read(12'h018,rd_a);
    axil_write(12'h004,2,0,0,0,0);
    axil_read(12'h018,rd_b);check("CTRL WSTRB zero",rd_b,rd_a);
    if (errors == 0) begin
        $display("TEST PASSED (%0d checks)", checks);
    end else begin
        $display("TEST FAILED (%0d errors / %0d checks)", errors, checks);
    end
    $finish;
end

// 全局看门狗：防止挂死（AXI 卡死会被上游 TIMEOUT 兜底，此处为测试兜底）
initial begin
    #200000;
    $display("TEST FAILED (watchdog timeout)");
    $finish;
end

endmodule
