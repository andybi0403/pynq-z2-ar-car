#include "../Source/APP/safe_control.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

/*
 * PYNQ 完整对接版主机单元测试。
 * 本版本传感器全部在 PYNQ 上：距离、有效性和红外位图只来自 $P 帧，
 * 因此测试不再调用 safe_sensors——所有快照都由 safe_pframe 写入。
 * 测试帧校验和由脚本按 sum('$'..'N')&0xFF 生成，与固件算法一致。
 */
static SafeControl s;
static const char *stop="$0,0,0,0,0,0,0,0,0,0#";
static const char *go="$1,0,0,0,0,0,0,0,0,0#";

static void frame(const char *p,uint32_t now) { (void)safe_frame(&s,p,strlen(p),now); }

/*
 * 人工重新使能流程（对接版）：先喂一串“距离有效且正常”的 $P 帧，
 * 让 clear_tracking 持续 300ms，再发停止帧解锁。
 */
static void arm(uint32_t now) {
 unsigned t;
 safe_init(&s);
 for(t=0;t<=300;t+=100)
  assert(safe_pframe(&s,"$P,0,0,1,1000,0,0,2E#",sizeof("$P,0,0,1,1000,0,0,2E#")-1,now+t));
 frame(stop,now+300); assert(!s.latched);
}
int main(void) {
 int l,r;

 /* 上电未使能时，即使收到前进驱动帧，电机输出也必须为 0。 */
 safe_init(&s); assert(safe_pframe(&s,"$P,1200,1200,1,0888,0,0,6B#",sizeof("$P,1200,1200,1,0888,0,0,6B#")-1,50));
 assert(s.latched && s.distance_mm==888 && s.valid && s.ir==0);
 safe_outputs(&s,&l,&r); assert(l==0&&r==0);

 /* 解锁后 $P 帧直接驱动左右轮 RAW 输出。 */
 arm(1000);
 assert(safe_pframe(&s,"$P,1200,1200,1,0888,0,0,6B#",sizeof("$P,1200,1200,1,0888,0,0,6B#")-1,1500));
 assert(s.command==DRIVE_RAW);
 safe_outputs(&s,&l,&r); assert(l==1200&&r==1200);

 /* 红外来自 $P 帧字段，只告警；本帧请求零输出但不锁车。 */
 assert(safe_pframe(&s,"$P,0,0,1,1000,3,5,36#",sizeof("$P,0,0,1,1000,3,5,36#")-1,1600));
 assert(!s.latched && !(s.reason&FAULT_IR) && s.ir==3);
 safe_outputs(&s,&l,&r); assert(l==0&&r==0);

 /* 红外清除且距离正常后，停止帧可解锁。 */
 { unsigned t;
   for(t=2000;t<=2300;t+=100)
    assert(safe_pframe(&s,"$P,0,0,1,1000,0,0,2E#",sizeof("$P,0,0,1,1000,0,0,2E#")-1,t));
   frame(stop,2300); assert(!s.latched);
 }

 /* 近障回差：200mm 只清正向分量，250mm 恢复，负向永远保留。 */
 assert(safe_pframe(&s,"$P,1200,-800,1,0200,0,1,58#",sizeof("$P,1200,-800,1,0200,0,1,58#")-1,3000));
 safe_outputs(&s,&l,&r); assert(l==0&&r==-800);
 assert(s.distance_blocked && (s.reason&FAULT_DISTANCE));
 assert(safe_pframe(&s,"$P,900,900,1,0250,0,2,08#",sizeof("$P,900,900,1,0250,0,2,08#")-1,3100));
 safe_outputs(&s,&l,&r); assert(l==900&&r==900);
 assert(!s.distance_blocked && !(s.reason&FAULT_DISTANCE));

 /* PYNQ 声明距离无效（V=0）：立即 FAULT_SENSOR 锁车。 */
 arm(4000);
 assert(safe_pframe(&s,"$P,0,0,0,0,0,2,9E#",sizeof("$P,0,0,0,0,0,2,9E#")-1,4300));
 assert(s.latched && (s.reason&FAULT_SENSOR) && !s.valid);

 /* 双保险时间线：200ms 数据过期先于 250ms 租约，两个故障位都记录。 */
 arm(5000);
 assert(safe_pframe(&s,"$P,800,800,1,0888,0,4,19#",sizeof("$P,800,800,1,0888,0,4,19#")-1,5400));
 assert(s.command==DRIVE_RAW && !s.latched);
 safe_tick(&s,5400+199); assert(!s.latched);
 safe_tick(&s,5400+260);
 assert(s.latched && (s.reason&FAULT_SENSOR) && (s.reason&FAULT_LINK));
 safe_outputs(&s,&l,&r); assert(l==0&&r==0);

 /* 校验和错误帧被拒绝并计数，不得刷新租约。 */
 arm(6000);
 assert(safe_pframe(&s,"$P,0,0,1,1000,0,0,2E#",sizeof("$P,0,0,1,1000,0,0,2E#")-1,6300));
 frame(stop,6301); assert(!s.latched);
 { unsigned d=s.drop_count;
   assert(!safe_pframe(&s,"$P,1000,1000,1,0888,0,0,00#",sizeof("$P,1000,1000,1,0888,0,0,00#")-1,6400));
   assert(s.drop_count==d+1 && s.latched && (s.reason&FAULT_FRAME)); }

 /* 逐字段破坏：长度、字段数、字段范围都必须拒绝。 */
 { const char *bad[]={"$P,1200,1200,1,0888,0#",         /* 缺 IR/N/C */
                      "$P,1200,1200,1,0888,0,0#",       /* 缺校验和 */
                      "$P,1200,1200,1,0888,0,0,6B",     /* 无井号 */
                      "$P,1200,1200,2,0888,0,0,6B#",    /* V 越界 */
                      "$P,1200,1200,1,0888,4,0,6B#",    /* IR 越界 */
                      "$P,1200,1200,1,0888,0,A,6B#",    /* N 越界 */
                      "$P,1200,1200,1,10000,0,0,6B#",   /* MMM 越界 */
                      "$X,1200,1200,1,0888,0,0,6B#"};   /* 前缀错 */
   size_t i;
   for(i=0;i<8;i++) { arm(7000);
     assert(!safe_pframe(&s,bad[i],strlen(bad[i]),7100)); }
 }
 /* 合法边界帧：±2400/9999/IR=3 都要被解析接受（IR=3 锁车属预期语义）。 */
 arm(7200);
 assert(safe_pframe(&s,"$P,-2400,2400,1,9999,3,9,B6#",sizeof("$P,-2400,2400,1,9999,3,9,B6#")-1,7300));
 assert(s.left_req==-2400 && s.right_req==2400 && s.distance_mm==9999);
 assert(!(s.reason&FAULT_IR));
 /* 时间回绕：帧与租约检查在 uint32 回绕边界附近必须正常。 */
 { uint32_t base=0xfffffe00u;
   arm(base);
   assert(safe_pframe(&s,"$P,0,0,1,1000,0,0,2E#",sizeof("$P,0,0,1,1000,0,0,2E#")-1,base+400));
   frame(stop,base+401); assert(!s.latched);
   assert(safe_pframe(&s,"$P,800,800,1,0888,0,4,19#",sizeof("$P,800,800,1,0888,0,4,19#")-1,base+500));
   safe_tick(&s,base+500+260);
   assert(s.latched && (s.reason&FAULT_LINK));
 }
 /* 蓝牙十字段帧兼容路径（USB 诊断 $ARM# 使用）：坏帧仍须拒绝。 */
 arm(9000); frame("$1#",9301); assert(s.latched && (s.reason&FAULT_FRAME));
 arm(9500); frame(go,9801); assert(s.command==FORWARD);
 frame("$0,1,0,0,0,0,0,0,0,0#",9802); assert(s.command==SPIN_LEFT);
 frame(stop,9803); assert(!s.latched);

 /* 控制源切换必须废弃旧传感器快照。修复前，clear_tracking 与 valid 会
  * 留存，旧源的兼容 STOP 帧可在剩余的新鲜窗口内绕过重新采样而解锁。 */
 arm(10000);
 assert(s.valid && s.clear_tracking && !s.latched);
 assert(safe_pframe(&s,"$P,1200,-800,1,1000,0,0,56#",sizeof("$P,1200,-800,1,1000,0,0,56#")-1,10400));
 assert(s.left_req==1200 && s.right_req==-800);
 safe_source_handover(&s);
 assert(s.latched && !s.valid && !s.clear_tracking);
 assert(s.left_req==0 && s.right_req==0);
 frame(stop,10499);
 assert(s.latched && (s.reason&FAULT_SENSOR));
 safe_outputs(&s,&l,&r); assert(l==0&&r==0);

 /* P1-1 校验位置绑定回归：N 与校验和之间的插入字符必须整帧拒绝。
  * 反例帧的 X/Y 不参与校验和（其和恰为 2E），修复前会被静默跳过而接受。 */
 { unsigned d; uint32_t lease;
   arm(12000);
   d = s.drop_count; lease = s.command_ms;
   assert(!safe_pframe(&s,"$P,0,0,1,1000,0,0,X,2E#",sizeof("$P,0,0,1,1000,0,0,X,2E#")-1,12300));
   assert(!safe_pframe(&s,"$P,0,0,1,1000,0,0,Y,2E#",sizeof("$P,0,0,1,1000,0,0,Y,2E#")-1,12400));
   assert(s.drop_count==d+2 && s.latched && s.command_ms==lease);
   arm(13000);
   assert(!safe_pframe(&s,"$P,0,0,1,1000,0,0,,2E#",sizeof("$P,0,0,1,1000,0,0,,2E#")-1,13100)); /* 插逗号 */
   arm(14000);
   assert(!safe_pframe(&s,"$P,0,0,1,1000,0,0,5,2E#",sizeof("$P,0,0,1,1000,0,0,5,2E#")-1,14100)); /* 插字段 */
   /* 修复后合法边界帧必须仍被接受（校验和已独立脚本核验）。 */
   arm(15000);
   assert(safe_pframe(&s,"$P,0,0,1,0,0,0,9D#",sizeof("$P,0,0,1,0,0,0,9D#")-1,15300));            /* 最短 18 */
   assert(safe_pframe(&s,"$P,-2400,-2400,1,9999,3,9,E3#",sizeof("$P,-2400,-2400,1,9999,3,9,E3#")-1,15400)); /* 最长 29 */
   assert(s.left_req==-2400 && s.right_req==-2400 && s.distance_mm==9999);
   assert(!(s.reason&FAULT_IR)); /* IR=3 只保留真实告警状态 */
 }
 puts("PASS: boot lock, IR from $P frame, RAW drive, distance hysteresis,");
 puts("V=0 sensor fault, 200/250ms dual guard, checksum rejection,");
 puts("field validation, PWM clamp, time wrap, source-handover isolation,");
 puts("legacy frame path.");
 return 0;
}
