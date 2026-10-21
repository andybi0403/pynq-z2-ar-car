"""Inspect final routed constraints, including bus skew absent from WNS."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
build=ROOT/'pynq_fpga/fpga/build/task7_8_v09_qei_retest_20261012_r2'
timing=build/'timing_integrated_impl.rpt'
bus=build/'task7_8_integrated.runs/impl_1/preintegration_bd_wrapper_bus_skew_routed.rpt'
drc=build/'drc_integrated_impl.rpt'
lines=timing.read_text().splitlines()
head=next(i for i,l in enumerate(lines) if 'WNS(ns)' in l and 'TNS(ns)' in l)
numeric=next(l.split() for l in lines[head+1:] if re.match(r'^\s+[-\d.]+\s+[-\d.]+\s+\d+\s+\d+',l))
assert len(numeric)==12 and float(numeric[0])>=0 and float(numeric[4])>=0 and int(numeric[2])==0 and int(numeric[6])==0
skews=[(status,float(slack)) for status,slack in re.findall(r'Slack \((MET|VIOLATED)\)\s*:\s*([\d.-]+)ns',bus.read_text())]
assert skews and all(status=='MET' and slack>=0 for status,slack in skews)
assert not re.search(r'\|\s*\S+\s*\|\s*(Error|Critical Warning|Warning)\s*\|',drc.read_text())
record={'scope':'routed implementation, not external electrical or motion acceptance',
 'wns_ns':float(numeric[0]),'whs_ns':float(numeric[4]),'setup_failing_endpoints':int(numeric[2]),'hold_failing_endpoints':int(numeric[6]),
 'bus_skew_slacks_ns':[v for _,v in skews],'drc_error_critical_warning_warning_count':0,
 'retained_advisory':'two REQP-181 vendor VDMA BRAM advisories',
 'report_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (timing,bus,drc)}}
out=ROOT/'pynq_fpga/preintegration/evidence/qei_retest_20261012/routed_timing_audit.json'
assert not out.exists();out.write_text(json.dumps(record,indent=2),'utf8')
print(json.dumps(record,indent=2))
