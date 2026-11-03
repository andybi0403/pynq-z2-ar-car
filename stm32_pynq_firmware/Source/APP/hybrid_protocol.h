#ifndef HYBRID_PROTOCOL_H
#define HYBRID_PROTOCOL_H
#include "safe_control.h"
typedef struct {
    uint32_t session, query_seq, command_seq;
    uint8_t initialized, query_seen, command_seen;
} HybridSession;
/* 2=query to answer, 1=accepted command/release, 0=rejected and locked. */
int hybrid_receive(SafeControl *s, HybridSession *h, const char *p, size_t n, uint32_t now);
uint16_t hybrid_crc16(const char *p, size_t n);
size_t hybrid_report(char *out, size_t capacity, const SafeControl *s,
    const HybridSession *h, uint32_t request, uint32_t us_seq, unsigned us_age,
    unsigned us_valid, unsigned mm, uint32_t ir_seq, unsigned ir_age,
    unsigned ir_valid, unsigned ir, int left, int right);
void safe_local_sample(SafeControl *s, uint16_t mm, uint8_t valid,
                       uint32_t sample_ms, uint8_t ir, uint8_t ir_valid, uint32_t now);
#endif
