/* UART v3: query replies bind sample age to a fresh host request. Heartbeats
 * never refresh local sensor timestamps or the independent movement lease. */
#include "hybrid_protocol.h"
#include <string.h>
#include <limits.h>
#include <stdio.h>

uint16_t hybrid_crc16(const char *p, size_t n) {
    uint16_t crc=0xffffu;
    size_t i; unsigned b;
    for(i=0;i<n;i++) {
        crc^=(uint16_t)((uint16_t)(unsigned char)p[i]<<8);
        for(b=0;b<8;b++) crc=(uint16_t)((crc&0x8000u)?((uint32_t)crc<<1)^0x1021u:(uint32_t)crc<<1);
    }
    return crc;
}
size_t hybrid_report(char *out, size_t capacity, const SafeControl *s,
    const HybridSession *h, uint32_t request, uint32_t us_seq, unsigned us_age,
    unsigned us_valid, unsigned mm, uint32_t ir_seq, unsigned ir_age,
    unsigned ir_valid, unsigned ir, int left, int right) {
    int n,m;
    if(!h->initialized || capacity<10u || us_age>65535u || ir_age>65535u ||
       us_valid>1u || ir_valid>1u || mm>4095u || ir>3u) return 0;
    n=snprintf(out,capacity,
        "$S1,%lu,%lu,%lu,%u,%u,%u,%lu,%u,%u,%u,%d,%d,%u,%u,%u",
        (unsigned long)h->session,(unsigned long)request,(unsigned long)us_seq,
        us_age,us_valid,mm,(unsigned long)ir_seq,ir_age,ir_valid,ir,
        left,right,s->latched,s->reason,s->drop_count);
    if(n<=0 || (size_t)n>=capacity-8u) return 0;
    m=snprintf(out+n,capacity-(size_t)n,",%04X#\r\n",(unsigned)hybrid_crc16(out,(size_t)n));
    return m==8?(size_t)n+8u:0u;
}
static int hex(char c) {
    if(c>='0'&&c<='9') return c-'0';
    if(c>='A'&&c<='F') return c-'A'+10;
    return -1;
}
static int fresh(uint32_t next, uint32_t old) {
    uint32_t d=next-old;
    return d!=0u && d<0x80000000u;
}
static int number(const char *p, size_t end, size_t *i, uint32_t *v, int *negative) {
    unsigned digits=0;
    *v=0; *negative=0;
    if(*i<end && p[*i]=='-') { *negative=1; (*i)++; }
    while(*i<end && p[*i]>='0'&&p[*i]<='9') {
        unsigned digit=(unsigned)(p[*i]-'0');
        if(*v>(UINT32_MAX-digit)/10u || ++digits>10u) return 0;
        *v=*v*10u+digit; (*i)++;
    }
    return digits!=0;
}
void safe_local_sample(SafeControl *s, uint16_t mm, uint8_t valid,
                       uint32_t sample_ms, uint8_t ir, uint8_t ir_valid, uint32_t now) {
    s->distance_mm=mm; s->sample_ms=sample_ms;
    (void)ir_valid; /* IR availability is telemetry, never a motor prerequisite. */
    s->valid=(uint8_t)(valid != 0);
    s->ir=ir&3u;
    safe_tick(s,now);
}
int hybrid_receive(SafeControl *s, HybridSession *h, const char *p, size_t n, uint32_t now) {
    size_t end,i=4,k; unsigned checksum=0; int x,neg;
    uint32_t session,seq,v; int left=0,right=0; char kind;
    if(n==7 && !memcmp(p,"$PSTOP#",7)) { safe_fault(s,FAULT_START); return 1; }
    if(n<13 || n>64 || p[0]!='$' || p[2]!='1' || p[3]!=',' || p[n-1]!='#') goto bad;
    kind=p[1]; if(kind!='Q'&&kind!='D'&&kind!='R') goto bad;
    end=n-6; if(p[end]!=',') goto bad;
    for(k=end+1;k<n-1;k++) { x=hex(p[k]); if(x<0) goto bad; checksum=checksum*16u+(unsigned)x; }
    if(checksum!=hybrid_crc16(p,end)) goto bad;
    if(!number(p,end,&i,&session,&neg)||neg||!session||i>=end||p[i++]!=',') goto bad;
    if(!number(p,end,&i,&seq,&neg)||neg) goto bad;
    if(kind=='D') {
        if(i>=end||p[i++]!=',') goto bad;
        if(!number(p,end,&i,&v,&neg)||v>SAFE_MAX_PWM) goto bad;
        left=neg?-(int)v:(int)v;
        if(i>=end||p[i++]!=',') goto bad;
        if(!number(p,end,&i,&v,&neg)||v>SAFE_MAX_PWM) goto bad;
        right=neg?-(int)v:(int)v;
    }
    if(i!=end) goto bad;
    if(kind=='Q') {
        if(!h->initialized || h->session!=session) {
            memset(h,0,sizeof(*h)); h->session=session; h->initialized=1;
            safe_fault(s,FAULT_START); s->clear_tracking=0;
            s->left_req=0; s->right_req=0;
        }
        if(h->query_seen && !fresh(seq,h->query_seq)) goto bad;
        h->query_seq=seq; h->query_seen=1;
        return 2;
    }
    if(!h->initialized || h->session!=session ||
       (h->command_seen && !fresh(seq,h->command_seq))) goto bad;
    h->command_seq=seq; h->command_seen=1;
    safe_tick(s,now);
    if(kind=='R') {
        /* Release is explicit and cannot carry/replay a driving request. */
        s->left_req=0; s->right_req=0;
        return safe_frame(s,"$0,0,0,0,0,0,0,0,0,0#",21,now);
    }
    s->left_req=left; s->right_req=right;
    if(!s->latched) s->command=DRIVE_RAW;
    s->command_ms=now;
    return 1;
bad:
    if(s->drop_count!=UINT16_MAX) s->drop_count++;
    safe_fault(s,FAULT_FRAME);
    return 0;
}
