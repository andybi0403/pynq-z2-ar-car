"""Interpret PL display processing; never used as actuator feedback or permit."""
TICK_HZ=100_000_000
IR_DISPLAY_MAX_AGE_MS=200
TREND_NAMES=('unknown','stable','approaching','receding')


def state_from_registers(raw,ticks):
    def age_ms(name):
        elapsed=(int(ticks)-raw.get(name,0))&0xffffffff
        return elapsed/100_000 if elapsed<0x80000000 else None
    latest=age_ms('US_FILTER_LATEST_TS');oldest=age_ms('US_FILTER_OLDEST_TS')
    meta=raw.get('US_FILTER_META',0)
    valid=bool(meta&0x80000000 and latest is not None and latest<200 and oldest is not None and oldest<500)
    trend_word=raw.get('US_TREND_STATE',0);trend_valid=valid and bool(trend_word&0x80000000) and (trend_word&3)!=0
    delta=raw.get('US_TREND_DELTA_MM',0)&0xffff
    if delta&0x8000:delta-=0x10000
    ir_age=age_ms('IR_TS')
    # The bridge already enforces the raw 100ms IR acquisition deadline.
    # A video frame follows that snapshot, so allow its bounded display age
    # to include snapshot cadence. Explicit invalid bits still invalidate now.
    ir_valid=bool(raw.get('IR_META',0)&0x80000000 and raw.get('IR_STATUS',0)&4 and ir_age is not None and ir_age<IR_DISPLAY_MAX_AGE_MS)
    car=raw.get('SNAP_CAR_STATE',0)
    return {'raw_mm':raw.get('US_DATA',0)&4095,
            'filtered_mm':raw.get('US_FILTER_MM',0)&4095 if valid else None,
            'filter_valid':valid,'sample_count':(meta>>16)&3,'sample_sequence':meta&65535,
            'source_ticks':raw.get('US_FILTER_LATEST_TS',0),'support_start_ticks':raw.get('US_FILTER_OLDEST_TS',0),
            'filter_age_ms':latest,'support_span_ms':((raw.get('US_FILTER_LATEST_TS',0)-raw.get('US_FILTER_OLDEST_TS',0))&0xffffffff)/100_000,
            'trend':TREND_NAMES[trend_word&3] if trend_valid else 'unknown','trend_valid':trend_valid,
            'window_ms':raw.get('US_TREND_DT',0)/100_000,'closing_delta_mm':delta,
            'ir_mask':raw.get('IR_STATUS',0)&3,'ir_valid':ir_valid,
            'car_locked':bool(car&1),'car_valid':bool(car&2)}
