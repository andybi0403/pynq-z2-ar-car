"""Independent wire CRC/request/output and raw-S1 -> PL register audit."""
from pathlib import Path
import sys,json,re,binascii,hashlib,collections
out=Path(__file__).resolve().parent
prefix=sys.argv[1] if len(sys.argv)>1 else 'fixed_runtime'
raw=(out/(prefix+'_uart_rx.bin')).read_bytes()
tx=(out/(prefix+'_uart_tx.bin')).read_bytes().splitlines()
rows=[json.loads(l) for l in (out/(prefix+'_samples.jsonl')).read_text(encoding='utf8').splitlines()]
summary=json.loads((out/(prefix+'_acceptance_summary.json')).read_text(encoding='utf8'))
queries=set();tx_types=collections.Counter()
for p in tx:
 if p==b'$PSTOP#':tx_types['PSTOP']+=1;continue
 assert p.startswith(b'$Q1,') and p.endswith(b'#'),'unexpected motor/control packet'
 body,check=p[:-1].rsplit(b',',1)
 assert binascii.crc_hqx(body,0xffff)==int(check,16),'TX CRC mismatch'
 session,request=map(int,body[4:].split(b','));queries.add((session,request));tx_types['Q1']+=1
reports=[];keys=('session','request','us_seq','us_age_ms','us_valid','mm','ir_seq','ir_age_ms','ir_valid','ir','left','right','lock','fault','drop')
for p in re.findall(rb'\$S1,[^$#]*#',raw):
 body,check=p[:-1].rsplit(b',',1)
 assert binascii.crc_hqx(body,0xffff)==int(check,16),'RX CRC mismatch'
 v=list(map(int,body[4:].split(b',')));assert len(v)==15
 r=dict(zip(keys,v));assert (r['session'],r['request']) in queries
 assert r['lock']==1 and r['left']==r['right']==0
 assert not r['us_valid'] or 0<=r['us_age_ms']<200
 assert not r['ir_valid'] or 0<=r['ir_age_ms']<100
 reports.append(r)
assert reports
# The measurement counter is sampled before close(). The worker is joined
# during close, which can drain its one already outstanding reply afterward.
drained_after_window=len(reports)-summary['state_reports']
assert drained_after_window in (0,1)
if drained_after_window:
 assert reports[-1]['request']==max(q for _,q in queries)
assert all(a['request']<b['request'] for a,b in zip(reports,reports[1:]))
assert len({r['session'] for r in reports})==1
us=collections.defaultdict(set);ir=collections.defaultdict(set)
for r in reports:
 us[r['us_seq']&65535].add(r['mm']);ir[r['ir_seq']&65535].add(r['ir'])
matched={'us':0,'ir':0};first_valid={'us':None,'ir':None}
for row in rows:
 assert row['permit'] is False
 if row['state']:assert row['state']['lock']==1 and row['state']['left']==row['state']['right']==0
 reg=row['registers']
 if reg['US_META']>>31:
  assert reg['US_DATA']>>12==0
  assert (reg['US_DATA']&4095) in us[reg['US_META']&65535]
  matched['us']+=1
  if first_valid['us'] is None:first_valid['us']=row['elapsed_s']
 if reg['IR_META']>>31:
  assert reg['IR_STATUS']&4
  assert (reg['IR_STATUS']&3) in ir[reg['IR_META']&65535]
  matched['ir']+=1
  if first_valid['ir'] is None:first_valid['ir']=row['elapsed_s']
checks={'raw_crc_and_request_match':True,'all_feedback_locked_zero':True,'no_motor_release_or_drive_sent':True,'PL_values_correspond_to_wire_samples':True,'both_PL_channels_valid_over_90_percent':all(n>len(rows)*.9 for n in matched.values()),'production_acceptance_passed':summary['passed']}
if 'first_target_ir_low16' in summary:
 first_ir_row=next(r for r in rows if r['registers']['IR_META']>>31)
 checks['upper_half_first_sample_accepted']=bool(
     0x8000 <= (first_ir_row['registers']['IR_META']&65535) <= 0xffff and
     0x9000 <= summary['first_target_ir_low16'] < 0xb000)
audit={'kind':'INDEPENDENT_HARDWARE_UART_PL_AUDIT','prefix':prefix,'reports':len(reports),'reports_measured_before_close':summary['state_reports'],'reply_drained_during_close':drained_after_window,'tx_types':dict(tx_types),'samples':len(rows),'matched_valid_PL_samples':matched,'first_valid_PL_seconds':first_valid,'first_IR_low16':reports[0]['ir_seq']&65535,'distance_range_mm':[min(r['mm'] for r in reports),max(r['mm'] for r in reports)],'checks':checks,'passed':all(checks.values()),'wire_sha256':hashlib.sha256(raw).hexdigest()}
(out/(prefix+'_independent_audit.json')).write_text(json.dumps(audit,indent=2),encoding='utf8')
print(json.dumps(audit,indent=2))
if not audit['passed']:raise SystemExit(1)
