#include "../Source/APP/safe_control.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

/*
 * 这是不接真实小车也能运行的主机单元测试。
 * 它直接调用 safe_control.c 的“纯逻辑”部分，用假时间、假距离和假蓝牙帧
 * 检查状态机是否符合预期；因此可以先验证安全规则，再接入 STM32 硬件。
 */
static SafeControl s;
static const char *stop="$0,0,0,0,0,0,0,0,0,0#";
static const char *go="$1,0,0,0,0,0,0,0,0,0#";

/* 给控制逻辑喂一组传感器快照。测试中 sample_ms 与 now 相同，代表新数据。 */
static void sense(uint32_t now, unsigned ir, unsigned valid, unsigned mm) {
 safe_sensors(&s,now,(uint8_t)ir,(uint8_t)valid,(uint16_t)mm,now);
}

/* 模拟收到一整帧蓝牙数据。 */
static void frame(const char *p,uint32_t now) { (void)safe_frame(&s,p,strlen(p),now); }

/*
 * 测试统一的人工重新使能流程：
 * 传感器连续正常 → 发送停车帧 → 解除上电锁存。
 */
static void arm(uint32_t now) {
 safe_init(&s); sense(now,0,1,1000);
 sense(now+100,0,1,1000); sense(now+200,0,1,1000);
 sense(now+300,0,1,1000); frame(stop,now+300); assert(!s.latched);
}
int main(void) {
 int l,r;

 /* 上电未使能时，即使收到前进指令，电机输出也必须为 0。 */
 safe_init(&s); frame(go,0); safe_outputs(&s,&l,&r); assert(l==0&&r==0);

 /* 解除锁存后验证蓝牙前进、红外触发和人工重新使能。 */
 arm(0); frame(go,301); safe_outputs(&s,&l,&r); assert(l==1800&&r==1800);
 sense(302,1,1,1000); assert(s.latched && (s.reason&FAULT_IR));
 sense(303,0,1,1000); frame(go,304); assert(s.latched && s.command==STOP);
 sense(403,0,1,1000); sense(503,0,1,1000); sense(603,0,1,1000);
 frame(go,603); assert(s.latched); frame(stop,603); assert(!s.latched);
 frame(go,604); assert(s.command==FORWARD);

 /* 超声波近障只屏蔽前进；后退和转向仍可用于脱离障碍。 */
 sense(605,0,1,200); assert(!s.latched && s.distance_blocked && (s.reason&FAULT_DISTANCE));
 frame(go,605); safe_outputs(&s,&l,&r);
 assert(l==0&&r==0);
 frame("$2,0,0,0,0,0,0,0,0,0#",606); safe_outputs(&s,&l,&r);
 assert(l<0&&r<0);
 sense(607,0,1,249); assert(s.distance_blocked && !s.clear_tracking);
 sense(608,0,1,250); assert(!s.distance_blocked && !(s.reason&FAULT_DISTANCE));
 arm(1000); frame(go,1301); sense(1302,0,0,0); assert(s.reason&FAULT_SENSOR);

 /* 传感器长期不更新、蓝牙指令过期、非法帧都必须停车。 */
 arm(2000); frame(go,2301); safe_tick(&s,2500); assert(s.reason&FAULT_SENSOR);
 arm(3000); frame(go,3301);
 sense(3400,0,1,1000); sense(3500,0,1,1000); sense(3600,0,1,1000);
 sense(3700,0,1,1000); sense(3800,0,1,1000);
 frame(go,3801); assert(s.latched && (s.reason&FAULT_LINK));
 arm(4000); frame("$4WD,MODE31#",4301); assert(s.latched);
 arm(5000); frame("$1#",5301); assert(s.latched && (s.reason&FAULT_FRAME));
 arm(6000); frame("$9,0,0,0,0,0,0,0,0,0#",6301); assert(s.latched);
 arm(7000); frame("$2,0,0,0,0,0,0,0,0,0#",7301);
 safe_outputs(&s,&l,&r); assert(l<0&&r<0);
 sense(7302,2,1,1000); safe_outputs(&s,&l,&r); assert(l==0&&r==0);
 arm(8000); frame("$0,1,0,0,0,0,0,0,0,0#",8301);
 safe_outputs(&s,&l,&r); assert(l<0&&r>0);
 { unsigned i; for(i=0;i<20;i++) frame("$1,0,0,1,0,0,0,0,0,0#",8302+i); }
 safe_outputs(&s,&l,&r); assert(l==SAFE_MAX_PWM&&r==SAFE_MAX_PWM);
 arm(0xfffffe00u); frame(go,0xfffffe00u+301u);
 sense(0xfffffe00u+400u,0,1,1000);
 sense(0xfffffe00u+500u,0,1,1000);
 sense(0xfffffe00u+600u,0,1,1000); assert(!s.latched);
 sense(0xfffffe00u+700u,0,1,1000);
 sense(0xfffffe00u+801u,0,1,1000); assert(s.reason&FAULT_LINK);
 arm(9000); sense(9301,1,1,1000); frame(stop,9302); assert(s.latched);
 arm(10000); frame("$3,0,0,0,0,0,0,0,0,0#",10301);
 safe_outputs(&s,&l,&r); assert(l==0&&r>0);
 frame("$4,0,0,0,0,0,0,0,0,0#",10302);
 safe_outputs(&s,&l,&r); assert(l>0&&r==0);
 frame("$0,2,0,0,0,0,0,0,0,0#",10303);
 safe_outputs(&s,&l,&r); assert(l>0&&r<0);
 frame(stop,10304); safe_outputs(&s,&l,&r); assert(l==0&&r==0);
 arm(11000); frame("$4WD,PTZ180#",11301); assert(s.latched);
 arm(12000); frame("$1,0,0,2,0,0,0,0,0,0#",12301);
 assert(s.speed==1500); /* Decrease really decreases (vendor minimum bug). */

 /* 逐个破坏字符和长度，确认解析器不会越界，也不会误放行。 */
 { size_t i; char damaged[22];
   for(i=0;i<21;i++) {
     memcpy(damaged,go,22); damaged[i]='X'; arm(0);
     assert(!safe_frame(&s,damaged,21,301)); assert(s.latched);
   }
 }
 /* Frame lengths and fields must be validated before indexing. */
 { size_t n; for(n=0;n<21;n++) { arm(0); assert(!safe_frame(&s,go,n,301)); } }

 /*
  * PYNQ $P 帧路径：合法驱动、校验和失败、距离上报、250ms 租约、
  * 近障屏蔽正分量。解锁条件：dist_source=1 后距离与有效性完全来自 $P 帧。
  * 测试帧的校验和由脚本按 sum('$'..'N')&0xFF 生成，与固件算法一致。
  */
 { /* 锁存下收到合法 $P 帧：帧被接受、数据更新，但不产生运动输出，也不解锁。 */
   safe_init(&s); sense(0,0,1,1000);
   assert(safe_pframe(&s,"$P,1200,1200,1,0888,0,0F#",sizeof("$P,1200,1200,1,0888,0,0F#")-1,50));
   assert(s.latched && s.dist_source==1 && s.distance_mm==888);
   safe_outputs(&s,&l,&r); assert(l==0&&r==0);
 }
 { /* PYNQ 距离有效后停止帧解锁，再 $P 驱动 RAW 输出。 */
   arm(1000);
   assert(safe_pframe(&s,"$P,0,0,1,1000,0,D2#",sizeof("$P,0,0,1,1000,0,D2#")-1,1400));
   frame(stop,1401); assert(!s.latched);
   assert(safe_pframe(&s,"$P,1200,1200,1,0888,0,0F#",sizeof("$P,1200,1200,1,0888,0,0F#")-1,1500));
   assert(s.command==DRIVE_RAW);
   safe_outputs(&s,&l,&r); assert(l==1200&&r==1200);
   /* PYNQ 上报近障 200mm：正分量清零，负分量保留脱困。 */
   assert(safe_pframe(&s,"$P,1200,-800,1,0200,1,FC#",sizeof("$P,1200,-800,1,0200,1,FC#")-1,1600));
   safe_outputs(&s,&l,&r); assert(l==0&&r==-800);
   assert(s.distance_blocked);
   /* 距离恢复 250mm 后正分量恢复。 */
   assert(safe_pframe(&s,"$P,900,900,1,0250,2,AC#",sizeof("$P,900,900,1,0250,2,AC#")-1,1700));
   safe_outputs(&s,&l,&r); assert(l==900&&r==900);
 }
 { /* 校验和错误帧必须被拒绝并计数，不得刷新租约。 */
   arm(3000);
   assert(safe_pframe(&s,"$P,0,0,1,1000,0,D2#",sizeof("$P,0,0,1,1000,0,D2#")-1,3400));
   frame(stop,3401); assert(!s.latched);
   { unsigned drops=s.drop_count;
     assert(!safe_pframe(&s,"$P,1000,1000,1,0888,0,00#",sizeof("$P,1000,1000,1,0888,0,00#")-1,3500));
     assert(s.drop_count==drops+1); assert(s.latched); }
   /* 合法帧携带 V=0：PYNQ 声明距离无效，立即 FAULT_SENSOR 锁车。 */
   assert(safe_pframe(&s,"$P,0,0,0,0,2,42#",sizeof("$P,0,0,0,0,2,42#")-1,3600));
   assert(s.latched && (s.reason&FAULT_SENSOR));
 }
 { /* PYNQ 停帧保护：$P 帧同时刷新数据年龄与命令租约。
    * 199ms 时两者都新鲜；260ms 时数据过期(200ms)先于租约(250ms)触发，
    * 两类故障位都会被记录，形成双保险。 */
   arm(6000);
   assert(safe_pframe(&s,"$P,0,0,1,1000,0,D2#",sizeof("$P,0,0,1,1000,0,D2#")-1,6400));
   frame(stop,6401); assert(!s.latched);
   assert(safe_pframe(&s,"$P,800,800,1,0888,4,BD#",sizeof("$P,800,800,1,0888,4,BD#")-1,6500));
   assert(s.command==DRIVE_RAW && !s.latched);
   safe_tick(&s,6500+199); assert(!s.latched);
   safe_tick(&s,6500+260);
   assert(s.latched && (s.reason&(FAULT_SENSOR|FAULT_LINK)));
   /* 锁车后 motor 输出为 0。 */
   safe_outputs(&s,&l,&r); assert(l==0&&r==0);
 }

 /* P1-1 校验位置绑定回归（演示版格式）：插入字符必须整帧拒绝。 */
 { unsigned d; uint32_t lease;
   arm(12000);
   d = s.drop_count; lease = s.command_ms;
   assert(!safe_pframe(&s,"$P,0,0,1,1000,0,X,D2#",sizeof("$P,0,0,1,1000,0,X,D2#")-1,12300));
   assert(!safe_pframe(&s,"$P,0,0,1,1000,0,Y,D2#",sizeof("$P,0,0,1,1000,0,Y,D2#")-1,12400));
   assert(s.drop_count==d+2 && s.latched && s.command_ms==lease);
   arm(13000);
   assert(!safe_pframe(&s,"$P,0,0,1,1000,0,,D2#",sizeof("$P,0,0,1,1000,0,,D2#")-1,13100)); /* 插逗号 */
   arm(14000);
   assert(!safe_pframe(&s,"$P,0,0,1,1000,0,5,D2#",sizeof("$P,0,0,1,1000,0,5,D2#")-1,14100)); /* 插字段 */
   /* 修复后合法边界帧（演示版格式，校验和已独立核验）。 */
   arm(15000);
   assert(safe_pframe(&s,"$P,0,0,1,0,0,41#",sizeof("$P,0,0,1,0,0,41#")-1,15300));            /* 最短 16 */
   assert(safe_pframe(&s,"$P,-2400,-2400,1,9999,9,84#",sizeof("$P,-2400,-2400,1,9999,9,84#")-1,15400)); /* 最长 27 */
   assert(s.left_req==-2400 && s.right_req==-2400);
 }
 puts("PASS: boot lock, manual rearm, IR both sides, distance/hysteresis,");
 puts("sensor invalid/stale, command expiry, malformed/mode frames, PWM clamp, wrap,");
 puts("PYNQ $P frames (checksum, ext distance, RAW drive, 250ms lease).");
 return 0;
}
