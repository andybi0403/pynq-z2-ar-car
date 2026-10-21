`timescale 1ns/1ps
module tb_car_frame_metadata;
 reg clk=0;always #5 clk=~clk;
 reg rst=1;reg [23:0] sd;reg sv=0,su=0,sl=0,mr=0;
 wire sr;wire [23:0] md;wire mv,mu,ml;
 wire valid;wire [31:0] fid,speed;wire [15:0] epoch,reasons,errors;
 wire [63:0] ticks,path;wire signed [63:0] displacement;
 wire [11:0] distance;wire dv,vv,ov,stop;wire [1:0] level;
 car_axis_frame_metadata dut(.clk(clk),.rst(rst),.s_axis_tdata(sd),.s_axis_tvalid(sv),
  .s_axis_tready(sr),.s_axis_tuser(su),.s_axis_tlast(sl),.m_axis_tdata(md),
  .m_axis_tvalid(mv),.m_axis_tready(mr),.m_axis_tuser(mu),.m_axis_tlast(ml),
  .metadata_valid(valid),.frame_id(fid),.snapshot_epoch(epoch),.frame_pl_ticks(ticks),
  .distance_mm(distance),.distance_valid(dv),.speed_q16(speed),.speed_valid(vv),
  .displacement_q16(displacement),.path_q16(path),.odometry_valid(ov),
  .risk_level(level),.risk_stop(stop),.risk_reasons(reasons),.header_errors(errors));
 reg [23:0] input_data[0:1287],expected_data[0:1287];
 reg input_user[0:1287],input_last[0:1287],expected_valid[0:1287];
 reg [31:0] expected_id[0:1287];
 reg [23:0] words[0:17];reg [31:0] random_bits=32'h3921abcd;
 integer sent=0,received=0,checks=0,cycles=0,f,i,start_index,size;
 reg stalled=0,accepted=0;reg [25:0] held;
 task check(input bit condition,input string message);
  begin checks=checks+1;if(!condition) $fatal(1,"check %0d: %s",checks,message);end
 endtask
 initial begin
  words[0]=24'hd3a95c;words[1]=24'h010012;words[2]=24'h345678;words[3]=24'habcd12;
  words[4]=24'h00f3e8;words[5]=24'hff0000;words[6]=24'h0000ff;
  words[7]=24'hfe0000;words[8]=24'hffffff;words[9]=24'h00ffff;
  words[10]=24'h030000;words[11]=0;words[12]=0;words[13]=24'h000201;
  words[14]=24'hbcdef0;words[15]=24'h56789a;words[16]=24'h001234;
  words[17]=24'hffffff;for(i=0;i<17;i=i+1) words[17]=words[17]^words[i];
  start_index=0;
  for(f=0;f<6;f=f+1) begin
   size=f==4?8:256;
   for(i=0;i<size;i=i+1) begin
    input_data[start_index+i]=24'h238400+i;
    if(i<18&&f!=2) input_data[start_index+i]=words[i];
    if(f>=3&&i==2) input_data[start_index+i]=words[2]+f;
    if(f>=3&&i==17) input_data[start_index+i]=words[17]^words[2]^(words[2]+f);
    if(f==1&&i==17) input_data[start_index+i]=words[i]^1;
    input_user[start_index+i]=i==0;
    input_last[start_index+i]=(i%64==63)||(f==4&&i==7);
    expected_valid[start_index+i]=f==0||f==3||f==5;
    expected_id[start_index+i]=32'h12345678+(f>=3?f:0);
    expected_data[start_index+i]=(i<18&&expected_valid[start_index+i])?0:input_data[start_index+i];
   end
   start_index=start_index+size;
  end
  repeat(5) @(negedge clk);rst=0;
 end
 always @(negedge clk) if(!rst) begin
  random_bits={random_bits[30:0],random_bits[31]^random_bits[21]^random_bits[1]^random_bits[0]};
  mr=random_bits[0]||random_bits[4];
  // Never change a producer packet until its handshake.
  if(!sv||accepted) begin
   sv=sent<1288 && (random_bits[5]||random_bits[9]);
   if(sent<1288) begin sd=input_data[sent];su=input_user[sent];sl=input_last[sent];end
  end
 end
 always @(posedge clk) if(!rst) begin
  cycles=cycles+1;if(cycles>20000) $fatal(1,"timeout");
  accepted=sv&&sr;
  if(accepted) sent=sent+1;
  if(stalled) begin check(mv,"valid held under backpressure");check({mu,ml,md}==held,"packet held under backpressure");end
  stalled=mv&&!mr;held={mu,ml,md};
  if(mv&&mr) begin
   check(received<1288,"no duplicated output");
   check(md==expected_data[received],"pixel preservation/marker masking");
   check(mu==input_user[received]&&ml==input_last[received],"SOF/EOL preservation");
   if(mu) begin
    check(valid==expected_valid[received],"metadata belongs to this SOF");
    if(valid) begin
     check(fid==expected_id[received]&&epoch==16'habcd,"new frame id and snapshot epoch");
     check(ticks==64'h123456789abcdef0,"64-bit PL reception time");
     check(distance==1000&&dv&&vv&&ov,"historical flags");
     check(speed==32'hffff0000&&displacement==-64'sd131072&&path==196608,"signed physical values");
     check(level==1&&!stop&&reasons==16'h0201,"historical risk reasons");
    end
   end
   received=received+1;
   if(received==1288) begin
    check(sent==1288,"all input packets consumed");check(errors==3,"bad checksum/plain/short headers counted");
    $display("TEST PASSED (%0d checks)",checks);$finish;
   end
  end
 end
endmodule
