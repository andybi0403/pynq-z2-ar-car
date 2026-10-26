#include "../Source/APP/hybrid_protocol.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static SafeControl s;
static HybridSession h;
static char packet[180];
static int send(const char *body,uint32_t now) {
    int n=snprintf(packet,sizeof(packet),"%s,%04X#",body,(unsigned)hybrid_crc16(body,strlen(body)));
    assert(n>0);
    return hybrid_receive(&s,&h,packet,(size_t)n,now);
}
static void sample(uint32_t now) { safe_local_sample(&s,1000,1,now,0,1,now); }
int main(void) {
    int left,right; unsigned t;
    assert(hybrid_crc16("123456789",9)==0x29b1);
    safe_init(&s); memset(&h,0,sizeof(h));
    sample(0); assert(send("$Q1,123,1",0)==2); assert(s.latched);
    for(t=1;t<=400;t++) sample(t);
    assert(send("$R1,123,1",400)==1); assert(!s.latched);
    assert(send("$D1,123,2,600,700",400)==1);
    safe_outputs(&s,&left,&right); assert(left==600&&right==700);
    /* Query/drive traffic cannot refresh the physical sample timestamp. */
    assert(send("$Q1,123,2",500)==2); assert(send("$D1,123,3,600,700",550)==1);
    assert(s.sample_ms==400);
    safe_tick(&s,600); safe_outputs(&s,&left,&right);
    assert(s.latched&&(s.reason&FAULT_SENSOR)&&left==0&&right==0);
    /* A changed sensor batch cannot automatically release the fault. */
    sample(650); assert(s.latched);
    assert(send("$D1,999,4,1,1",650)==0);
    assert(send("$Q1,999,1",650)==2); assert(h.session==999&&s.latched);
    assert(send("$Q1,999,1",650)==0); /* replay */
    assert(hybrid_receive(&s,&h,"$PREL#",6,650)==0); /* old release */
    assert(hybrid_receive(&s,&h,"$P,0,0,1,1000,0,0,2E#",23,650)==0);
    assert(send("$D1,999,1,2401,0",650)==0);
    assert(send("$D1,999,1,0,0,X",650)==0);
    safe_init(&s); memset(&h,0,sizeof(h)); sample(0);
    assert(send("$Q1,1,4294967295",0)==2);
    assert(send("$Q1,1,0",1)==2); /* genuine sequence wrap */
    for(t=1;t<=400;t++)sample(t);
    assert(send("$R1,1,4294967295",400)==1);
    assert(send("$D1,1,0,500,-500",400)==1);
    for(t=401;t<=650;t++)sample(t);
    assert(s.latched&&(s.reason&FAULT_LINK)); /* samples cannot renew lease */
    safe_init(&s); sample(0xfffffff0u);
    safe_tick(&s,0x10u); assert(!(s.reason&FAULT_SENSOR));
    safe_tick(&s,0xb8u); assert(s.reason&FAULT_SENSOR); /* 200 ms wrap */
    safe_init(&s); safe_local_sample(&s,1000,1,0,0,0,0);
    assert(!(s.reason&FAULT_SENSOR)); /* IR loss does not invalidate fresh US. */
    memset(&h,0,sizeof(h)); assert(send("$Q1,222,1",0)==2);
    for(t=1;t<=400;t++)safe_local_sample(&s,1000,1,t,3,0,t);
    assert(send("$R1,222,1",400)==1); assert(!s.latched);
    assert(send("$D1,222,2,500,500",400)==1);
    safe_outputs(&s,&left,&right);assert(left==500&&right==500);
    safe_local_sample(&s,1000,0,401,3,0,401);
    assert(s.latched&&(s.reason&FAULT_SENSOR)); /* US loss still stops. */
    safe_init(&s); memset(&h,0,sizeof(h)); sample(0);
    assert(send("$Q1,123,1",0)==2);
    assert(hybrid_report(packet,sizeof(packet),&s,&h,1,7,20,1,1000,8,1,1,0,0,0)>0);
    printf("GOLDEN %s",packet);
    assert(hybrid_report(packet,12,&s,&h,1,7,20,1,1000,8,1,1,0,0,0)==0);
    puts("PASS hybrid: CRC, session, replay, wrap, local expiry, independent leases and report");
    return 0;
}
