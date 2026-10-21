/* PYNQ 完整对接版安全策略：纯 C 逻辑层，固件与主机测试共用。
 * 传感器全部在 PYNQ 侧，本层只消费 $P 帧上报的数据。 */
#include "safe_control.h"
#include <string.h>

void safe_init(SafeControl *s) {
    /* 上电默认锁车：必须先停车、确认传感器正常，再允许人工重新启动。 */
    memset(s, 0, sizeof(*s));
    s->latched=1; s->reason=FAULT_START; s->speed=1800;
}
void safe_fault(SafeControl *s, uint8_t reason) {
    /* 故障采用锁存方式，故障消失后也不会自动恢复之前的行驶命令。 */
    s->latched=1; s->command=STOP; s->reason |= reason;
}
void safe_source_handover(SafeControl *s) {
    /*
     * 新控制源不能继承旧源的“传感器仍新鲜”窗口。仅调用 safe_fault 会保留
     * valid/clear_tracking，随后到达的兼容 STOP 帧可能在 200 ms 窗口内完成
     * 解锁。源切换因此显式废弃快照和待执行 RAW 请求；距离回差状态保留为
     * 保守限制，必须由新源的有效 $P 帧更新后才能重新建立解锁条件。
     */
    safe_fault(s,FAULT_START);
    s->valid=0;
    s->clear_tracking=0;
    s->left_req=0;
    s->right_req=0;
}
void safe_tick(SafeControl *s, uint32_t now) {
    uint8_t fault=0;

    /* 每个控制周期都重新检查故障，而不是只在收到 $P 帧时检查。 */
    if (s->ir) fault |= FAULT_IR;
    if (!s->valid || (uint32_t)(now-s->sample_ms)>=SAFE_SENSOR_AGE_MS)
        fault |= FAULT_SENSOR;
    else if (s->distance_mm<=SAFE_STOP_MM) {
        /* 超声波近障是“方向性限制”：只屏蔽正向输出，不锁死整车。 */
        s->distance_blocked=1;
        s->reason |= FAULT_DISTANCE;
    } else if (s->distance_blocked && s->distance_mm>=SAFE_RELEASE_MM) {
        /* 使用释放阈值形成回差，避免临界距离来回切换。 */
        s->distance_blocked=0;
        s->reason &= (uint8_t)~FAULT_DISTANCE;
    }

    /* command_ms 是“运动租约”：持续收不到新 $P 帧就停车。 */
    if (s->command!=STOP && (uint32_t)(now-s->command_ms)>=SAFE_COMMAND_MS)
        fault |= FAULT_LINK;
    if (fault) safe_fault(s,fault);

    /* 只有红外清除、距离足够大且数据未过期，才开始人工解锁计时。 */
    if (!s->ir && s->valid && s->distance_mm>=SAFE_RELEASE_MM &&
        (uint32_t)(now-s->sample_ms)<SAFE_SENSOR_AGE_MS) {
        if (!s->clear_tracking) { s->clear_tracking=1; s->clear_ms=now; }
    } else s->clear_tracking=0;
}
int safe_frame(SafeControl *s, const char *p, size_t n, uint32_t now) {
    unsigned i; uint8_t cmd;
    safe_tick(s,now); /* Expired/faulted commands cannot refresh themselves. */

    /* MODE 帧只记录为故障，不允许通过模式切换绕过启动锁。 */
    if (n==12 && memcmp(p,"$4WD,MODE",9)==0 && p[11]=='#' &&
        p[9]>='0' && p[9]<='6' && (p[10]=='0'||p[10]=='1')) {
        /* Mode selection never enables unattended motion. */
        safe_fault(s,FAULT_MODE);
        return 1;
    }
    /* 原车运动帧固定为 $d,d,d,d,d,d,d,d,d,d#，共 21 个字符。 */
    if (n!=21 || p[0]!='$' || p[20]!='#') goto bad;
    for(i=0;i<10;i++) {
        /* 逐字段检查格式，避免把任意串口字符当成运动指令。 */
        if(p[1+2*i]<'0'||p[1+2*i]>'9') goto bad;
        if(i<9 && p[2+2*i]!=',') goto bad;
    }
    if(p[1]>'4'||p[3]>'2'||p[5]>'1'||p[7]>'2'||p[9]>'2'||
       p[11]!='0'||p[13]>'8'||p[15]>'1'||p[17]>'1'||p[19]!='0') goto bad;
    cmd=(uint8_t)(p[1]-'0');
    /* 原协议用第 2 个字段区分原地旋转，覆盖普通方向命令。 */
    if(p[3]=='1') cmd=SPIN_LEFT;
    if(p[3]=='2') cmd=SPIN_RIGHT;
    if(cmd==STOP) {
        s->command=STOP;
        /* 停车指令本身不能立即解锁，必须安全距离持续 CLEAR_MS。 */
        if(s->clear_tracking && (uint32_t)(now-s->clear_ms)>=SAFE_CLEAR_MS) {
            s->latched=0; s->reason=0;
        }
    } else if(!s->latched) {
        /* 允许后退/转向脱离障碍；前进在 distance_blocked 时由输出层屏蔽。 */
        s->command=cmd;
    }
    /* 速度调节只改变目标 PWM，不代表真实车速；真实车速以后由编码器测量。 */
    if(p[7]=='1') s->speed+=300;
    if(p[7]=='2') s->speed-=300;
    if(s->speed>SAFE_MAX_PWM) s->speed=SAFE_MAX_PWM;
    if(s->speed<600) s->speed=600;
    s->command_ms=now;
    return 1;
bad:
    /* 错帧不会刷新 command_ms，同时进入锁存停车。 */
    safe_fault(s,FAULT_FRAME);
    return 0;
}
/*
 * PYNQ 驱动帧：$P,<L>,<R>,<V>,<MMM>,<IR>,<N>,<C>#
 *   L/R  左右轮 PWM，带符号十进制，范围 -2400..2400，正=前进；
 *   V    PYNQ 侧超声波有效性 0/1，0 表示本次数据不可信；
 *   MMM  PYNQ PL 测得的距离 mm，0..9999，V=0 时忽略数值本身；
 *   IR   红外位图 0..3，bit0 左 bit1 右，1=检测到障碍；红外硬件在 PYNQ 上；
 *   N    序号 0..9 循环，本机只校验格式，丢帧核对由 PYNQ 侧完成；
 *   C    校验和：'$' 到 N 字段所有字符 ASCII 和的低 8 位，两位大写十六进制。
 * 示例（校验和与实现一致）：$P,1200,1200,1,0888,0,0,xx#
 * 红外触发、V=0、数据过期、租约超时、校验失败都会锁存停车；帧解析逐
 * 字段检查格式，任何越界、缺字段或校验失败都算 FAULT_FRAME。
 */
static int pnum(const char *p, size_t n, size_t *i, int *out) {
    /* 解析一个可选符号的十进制整数，成功时 *i 指向字段后的逗号或结束检查点。 */
    int neg=0, v=0, digits=0;
    if(*i<n && (p[*i]=='-'||p[*i]=='+')) { neg=(p[*i]=='-'); (*i)++; }
    while(*i<n && p[*i]>='0' && p[*i]<='9') {
        v=v*10+(p[*i]-'0'); (*i)++; digits++;
        if(digits>5) return 0; /* PWM 数值最多 4 位；最多容忍 5 位，6 位直接拒绝。 */
    }
    if(!digits) return 0;
    *out = neg ? -v : v;
    return 1;
}
int safe_pframe(SafeControl *s, const char *p, size_t n, uint32_t now) {
    size_t i=3, cs_pos; unsigned sum=0, csum; int L,R,V,MMM,IR;

    /* 最长帧：$P,-2400,-2400,0,9999,3,9,XX# = 29 字符。 */
    if(n<15 || n>29 || memcmp(p,"$P,",3)!=0 || p[n-1]!='#') goto bad;
    if(!pnum(p,n,&i,&L)) goto bad;
    if(i>=n || p[i]!=',') goto bad;
    i++;
    if(!pnum(p,n,&i,&R)) goto bad;
    if(i>=n || p[i]!=',') goto bad;
    i++;
    if(p[i]<'0'||p[i]>'1') goto bad;
    V=p[i]-'0';
    i++;
    if(i>=n || p[i]!=',') goto bad;
    i++;
    if(!pnum(p,n,&i,&MMM)) goto bad;
    if(MMM<0 || MMM>9999) goto bad;
    if(i>=n || p[i]!=',') goto bad;
    i++;
    if(p[i]<'0'||p[i]>'3') goto bad;
    IR=p[i]-'0';
    i++;
    if(i>=n || p[i]!=',') goto bad;
    i++;
    if(p[i]<'0'||p[i]>'9') goto bad; /* N 序号仅校验格式，由 PYNQ 侧核对丢帧。 */
    i++;
    if(i>=n || p[i]!=',') goto bad;
    /* 校验和覆盖 '$' 到 N 字段的所有字符（不含 N 后的逗号），两位大写十六进制。
     * 解析终点必须严格落在帧尾逗号上（i == n-4）：否则 N 与校验和之间的任何
     * 插入字符（如 $P,0,0,1,1000,0,0,X,2E# 中的 X）既不参与校验也不被解析，
     * 会形成可注入的旁路字段。 */
    cs_pos=i;
    if(i != n-4) goto bad;
    for(size_t k=0;k<cs_pos;k++) sum=(sum+(unsigned char)p[k])&0xFFu;
    /* 帧尾布局：... , N , CH CL #  →  p[n-4]=',' p[n-3]=CH p[n-2]=CL p[n-1]='#' */
    if(n<4 || p[n-4]!=',' || p[n-1]!='#') goto bad;
    if(p[n-3]>='0'&&p[n-3]<='9') csum=(unsigned)(p[n-3]-'0');
    else if(p[n-3]>='A'&&p[n-3]<='F') csum=(unsigned)(p[n-3]-'A'+10);
    else goto bad;
    if(p[n-2]>='0'&&p[n-2]<='9') csum=csum*16u+(unsigned)(p[n-2]-'0');
    else if(p[n-2]>='A'&&p[n-2]<='F') csum=csum*16u+(unsigned)(p[n-2]-'A'+10);
    else goto bad;
    if(csum!=sum) goto bad;

    /* 校验通过后先更新传感器快照，再做状态检查，保证 tick 用同一批数据。
     * 注意：与 safe_frame 不同，本函数开头不先用旧快照 tick——$P 帧是
     * 对接版唯一的传感器来源，帧间隔内数据必然在“老化”，若先检查会把
     * 正常到达的新帧误判为过期。已锁存的状态不会被本帧解锁，安全不变。 */
    s->ir=(uint8_t)IR;
    if(V) { s->valid=1; s->distance_mm=(uint16_t)MMM; s->sample_ms=now; }
    else { s->valid=0; }
    safe_tick(s,now);
    if(L>SAFE_MAX_PWM) L=SAFE_MAX_PWM;
    if(L<-SAFE_MAX_PWM) L=-SAFE_MAX_PWM;
    if(R>SAFE_MAX_PWM) R=SAFE_MAX_PWM;
    if(R<-SAFE_MAX_PWM) R=-SAFE_MAX_PWM;
    s->left_req=L; s->right_req=R;
    if(!s->latched) s->command=DRIVE_RAW;
    s->command_ms=now; /* 驱动帧同时是心跳：刷新运动租约。 */
    return 1;
bad:
    s->drop_count++;
    safe_fault(s,FAULT_FRAME);
    return 0;
}
void safe_outputs(const SafeControl *s, int *left, int *right) {
    /* 默认输出为 0；锁车时直接返回，保证故障优先级高于驾驶请求。 */
    *left=0; *right=0;
    if(s->latched) return;
    if(s->command==DRIVE_RAW) {
        /* 近障屏蔽语义与 FORWARD 一致：只清正向分量，保留反向脱困能力。 */
        *left = (s->distance_blocked && s->left_req>0) ? 0 : s->left_req;
        *right= (s->distance_blocked && s->right_req>0) ? 0 : s->right_req;
        return;
    }
    if(s->distance_blocked && s->command==FORWARD) return;
    switch(s->command) {
    case FORWARD: *left=s->speed; *right=s->speed; break;
    case BACKWARD: *left=-s->speed; *right=-s->speed; break;
    case LEFT: *right=s->speed; break;
    case RIGHT: *left=s->speed; break;
    case SPIN_LEFT: *left=-s->speed; *right=s->speed; break;
    case SPIN_RIGHT: *left=s->speed; *right=-s->speed; break;
    default: break;
    }
}
