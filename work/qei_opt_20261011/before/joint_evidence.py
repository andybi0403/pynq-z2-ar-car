"""Recompute joint evidence from raw logs; software records cannot pass hardware gates."""
from pathlib import Path
import argparse
import bisect
import json
import math
import sys
import re

HERE=Path(__file__).resolve().parent
if not (HERE/'perception_replay.py').is_file():
    sys.path.insert(0,str(HERE.parents[1]/'host'))

from frame_association import FrameAssociator
from frame_metadata import encode as encode_frame_metadata
from association_metrics import AssociationMetrics, distribution
from frame_pipeline import FrameMetrics
from perception_replay import SNAPSHOT_REGISTER_NAMES
import car_regs as reg
from runtime_identity import sha256,RUNTIME_FILES,expected_identity_from_package


def rows(path):
    with Path(path).open(encoding='utf-8') as stream:
        for n,line in enumerate(stream,1):
            try:item=json.loads(line)
            except (ValueError,TypeError) as exc:raise ValueError(f'journal line {n}: invalid JSON') from exc
            if not isinstance(item,dict):raise ValueError(f'journal line {n}: object required')
            yield item


def integer(value, name, lo=0, hi=(1<<64)-1):
    if type(value) is not int or not lo<=value<=hi:raise ValueError(f'invalid {name}')
    return value


def number(value,name,lo=0):
    if type(value) not in (int,float) or not math.isfinite(value) or value<lo:
        raise ValueError(f'invalid {name}')
    return value


def acquisition_failures(raw, *, require_odometry=False):
    """Check acquisition health independently of temporal frame association.

    IR_TS describes state changes, so a stationary clear IR state is not aged.
    Odometry also retains its last edge time while stationary.
    """
    failures=[]
    for name in ('US','IR','QEI0','QEI1','RISK'):
        if not raw[name+'_META'] & 0x80000000:
            failures.append(name.lower()+' acquisition invalid')
    if (raw['US_DATA'] >> 12) & 15:
        failures.append('ultrasonic acquisition fault')
    if not raw['IR_STATUS'] & 4 or raw['IR_STATUS'] & 3:
        failures.append('infrared unstable or obstacle present')
    if require_odometry:
        for channel in range(2):
            meta=raw[f'ODOM{channel}_META']
            if not meta & 0x80000000 or meta & 0x40000000:
                failures.append(f'odometry{channel} invalid or faulted')
    return failures


def inspect(journal, summary, *, minimum_duration_s=1800, require_hardware=True,
            expected_identity=None, min_fps=25, max_interval_p95_ms=50,
            max_submit_p95_ms=100, max_uncertainty_ms=5, max_control_gap_ms=150):
    number(minimum_duration_s,'minimum duration')
    for name,value in [('minimum fps',min_fps),('maximum interval',max_interval_p95_ms),
                       ('maximum submission latency',max_submit_p95_ms),('maximum uncertainty',max_uncertainty_ms),
                       ('maximum control gap',max_control_gap_ms)]:
        if number(value,name)<=0:raise ValueError(f'{name} must be positive')
    report=json.loads(Path(summary).read_text(encoding='utf-8'))
    if report.get('schema')!='car-joint-summary/v1':raise ValueError('joint summary schema mismatch')
    if sha256(journal)!=report.get('journal_sha256'):raise ValueError('joint journal SHA-256 mismatch')
    header=None;end=None;anchors=[];statuses=[];sample_times=[];previous_epoch=None;config_changes=0
    for item in rows(journal):
        kind=item.get('type')
        if header is None:
            if kind!='header' or item.get('schema')!='car-joint-session/v1':raise ValueError('missing joint header')
            header=item
            if item.get('contract_version')!=reg.CONTRACT_VERSION or item.get('contract_id')!=reg.INTEGRATED_ID:
                raise ValueError('joint register contract mismatch')
            if item.get('tick_hz')!=100_000_000:raise ValueError('joint tick frequency mismatch')
            if type(item.get('hardware')) is not bool:raise ValueError('hardware must be boolean')
            if item.get('motion_allowed') is not False or item.get('motor_disconnected') is not True:
                raise ValueError('joint log must be a disconnected zero-output session')
            continue
        if end is not None:raise ValueError('records found after end marker')
        if kind=='sample':
            if item.get('index')!=len(anchors):raise ValueError('sample index missing/reordered')
            epoch=integer(item.get('clock_anchor',{}).get('epoch'),'epoch',0,65535)
            if previous_epoch is not None and epoch!=(previous_epoch+1)&65535:raise ValueError('snapshot epoch froze/skipped')
            previous_epoch=epoch
            raw=item.get('registers')
            if not isinstance(raw,dict) or set(raw)!=set(SNAPSHOT_REGISTER_NAMES):raise ValueError('incomplete raw snapshot')
            for name,value in raw.items():integer(value,name,0,0xFFFFFFFF)
            a=item['clock_anchor'];before=integer(a.get('host_before_ns'),'clock before');after=integer(a.get('host_after_ns'),'clock after')
            ticks=integer(a.get('pl_ticks64'),'PL clock')
            if before>after or a.get('host_anchor_ns')!=(before+after)//2 or a.get('anchor_uncertainty_ns')!=(after-before+1)//2:
                raise ValueError('clock bracket/uncertainty inconsistent')
            if anchors and before<anchors[-1]['host_after_ns']:raise ValueError('clock brackets overlap or reverse')
            if anchors and ticks<anchors[-1]['pl_ticks64']:raise ValueError('64-bit PL clock reversed/reset')
            if anchors:
                previous=anchors[-1]
                elapsed_ns=a['host_anchor_ns']-previous['host_anchor_ns']
                pl_elapsed_ns=(ticks-previous['pl_ticks64'])*10
                # Account for both read brackets plus scheduling/clock drift.
                uncertainty=a['anchor_uncertainty_ns']+previous['anchor_uncertainty_ns']
                tolerance_ns=uncertainty+max(5_000_000,elapsed_ns//100)
                if abs(pl_elapsed_ns-elapsed_ns)>tolerance_ns:
                    raise ValueError('PL clock elapsed time disagrees with host brackets')
            if item.get('pl_ticks64')!=ticks or item.get('host_monotonic_ns')!=after:raise ValueError('sample anchor mismatch')
            if item.get('control',{}).get('requested_pwm')!=[0,0] or item.get('control',{}).get('output_pwm')!=[0,0]:
                raise ValueError('nonzero request/output in LAB joint log')
            anchors.append({**a,'registers':raw});sample_times.append(after)
        elif kind=='status':
            statuses.append(item)
        elif kind=='calibration':config_changes+=1
        elif kind=='end':end=item
        elif kind!='frame':raise ValueError(f'unknown journal record {kind!r}')
    if not header or not end or len(anchors)<2:raise ValueError('incomplete joint session')
    if report.get('session_id')!=header.get('session_id') or end.get('session_id')!=header.get('session_id'):
        raise ValueError('mixed session identities')
    if report.get('hardware') is not header['hardware']:raise ValueError('summary changed hardware classification')
    if config_changes==0 and report.get('identity')!=header.get('identity'):raise ValueError('summary changed identity')
    if expected_identity is not None and header.get('identity')!=expected_identity:raise ValueError('package/configuration identity mismatch')
    started=integer(header.get('started_host_ns'),'start');ended=integer(end.get('ended_host_ns'),'end')
    duration=(ended-started)/1e9
    if duration<0 or sample_times[0]<started or sample_times[-1]>ended:raise ValueError('samples outside active interval')
    if abs(number(report.get('duration_observed_s'),'observed duration')-duration)>.005:raise ValueError('summary duration disagrees with raw log')
    metrics=FrameMetrics();association=AssociationMetrics();frame_count=0;frame_times=[];display_frames={}
    keys=[a['host_after_ns'] for a in anchors]
    for item in rows(journal):
        if item.get('type')!='frame':continue
        received=integer(item.get('received_host_ns'),'frame reception')
        submitted=integer(item.get('submitted_host_ns'),'frame submission')
        if not started<=received<=submitted<=ended:raise ValueError('frame outside active interval')
        selected=bisect.bisect_right(keys,received)-1
        broker=FrameAssociator()
        if selected>=0:
            a=anchors[selected]
            broker.publish(host_before_ns=a['host_before_ns'],host_after_ns=a['host_after_ns'],pl_ticks64=a['pl_ticks64'],
                           registers=a['registers'],epoch=a['epoch'])
        recomputed=broker.associate(integer(item.get('frame_id'),'frame id'),received,submitted)
        if recomputed['valid']:
            recomputed['display_metadata_words']=encode_frame_metadata(recomputed)
        if {k:v for k,v in item.items() if k!='type'}!=recomputed:raise ValueError('frame association differs from raw snapshot/time replay')
        association.observe(recomputed);metrics.observe(received);frame_count+=1
        frame_times.append((received,submitted))
        if recomputed['valid']:
            display_frames[item['frame_id']]=(recomputed['epoch'],recomputed['estimated_frame_pl_ticks64'])
    timing=association.summary();video=metrics.summary()
    if report.get('association_metrics')!=timing or report.get('video_metrics')!=video:
        raise ValueError('summary timing metrics disagree with raw replay')
    if report.get('samples')!=len(anchors) or end.get('samples')!=len(anchors) or report.get('frames')!=frame_count or end.get('frames')!=frame_count:
        raise ValueError('summary/end counts disagree with raw journal')
    failures=[]
    for anchor in anchors:
        failures.extend(acquisition_failures(anchor['registers'],require_odometry=require_hardware))
    if require_hardware and header['hardware'] is not True:failures.append('hardware evidence is missing; software fixture cannot pass')
    if require_hardware and expected_identity is None:failures.append('expected package/configuration identity is missing')
    if require_hardware:
        identity=header.get('identity',{})
        code=identity.get('runtime_sources',{})
        digests=[identity.get(name) for name in ('bit_sha256','hwh_sha256','manifest_sha256')]
        if not isinstance(code,dict) or set(code)!=set(RUNTIME_FILES):failures.append('runtime source binding is incomplete')
        else:digests.extend(code.values())
        if any(not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value) for value in digests):
            failures.append('artifact/runtime hash binding is invalid')
        try:
            from calibration_config import CalibrationConfig
            configuration=CalibrationConfig.from_payload(identity.get('calibration',{}))
            if configuration.measured is not True:failures.append('calibration is nominal rather than measured')
        except (ValueError,TypeError,KeyError):failures.append('measured calibration provenance is missing')
    if duration<minimum_duration_s:failures.append('active session shorter than required duration')
    if config_changes:failures.append('calibration changed during acceptance interval; rerun with fixed configuration')
    if end.get('failures') or report.get('failures') or report.get('passed') is not True:failures.append('session recorded failures')
    gaps=[(b-a)/1e6 for a,b in zip(sample_times,sample_times[1:])]
    if max(gaps+[0])>max_control_gap_ms:failures.append('control gap exceeded threshold')
    if (sample_times[0]-started)/1e6>max_control_gap_ms or (ended-sample_times[-1])/1e6>max_control_gap_ms:
        failures.append('control samples do not cover session start/end')
    if len(statuses)!=len(anchors):failures.append('status coverage does not match control sampling')
    fresh_sequences=set();safe_responses=[];previous_sequence=-1;previous_rx=None
    observed_sofs=set();osd_latencies=[];display_ages=[]
    for index,status in enumerate(statuses):
        car=status.get('car');age=status.get('car_age_s');sequence=integer(status.get('car_sequence'),'CAR sequence')
        status_time=integer(status.get('host_monotonic_ns'),'status time')
        if not started<=status_time<=ended:raise ValueError('status outside active interval')
        if index<len(anchors) and (status.get('epoch')!=anchors[index]['epoch'] or status_time<sample_times[index]):
            raise ValueError('status/control snapshot mismatch')
        if sequence<previous_sequence:raise ValueError('CAR sequence reversed')
        valid=car is not None and age is not None and 0<=number(age,'CAR age')<.7
        if status.get('car_valid') is not valid:raise ValueError('CAR validity disagrees with reception age')
        if valid:
            for key,lo,hi in [('left',-2400,2400),('right',-2400,2400),('lock',0,1),
                              ('fault',0,65535),('mm',0,9999),('ir',0,3),('drop',0,0xFFFFFFFF)]:
                integer(car.get(key),'CAR '+key,lo,hi)
            rx_estimate=status_time-int(age*1e9)
            if sequence==previous_sequence and previous_rx is not None and abs(rx_estimate-previous_rx)>10_000_000:
                raise ValueError('repeated CAR feedback had its reception time renewed')
            previous_rx=rx_estimate
            if car.get('left')!=0 or car.get('right')!=0 or car.get('lock')!=1:failures.append('CAR was not locked zero')
            fresh_sequences.add(sequence)
            safe_responses.append((status_time-started)/1e6)
        elif (integer(status.get('host_monotonic_ns'),'status time')-started)/1e6>300:
            failures.append('CAR feedback stale/missing after startup')
        if status.get('display',{}).get('OSD_ERRORS',0)!=0:failures.append('OSD frame format errors')
        if require_hardware and (status_time-started)>3_000_000_000:
            display=status.get('display',{})
            required=('DISPLAY_FRAME_ID','DISPLAY_FRAME_STATE','DISPLAY_FRAME_TS_LO','DISPLAY_FRAME_TS_HI',
                      'DISPLAY_HEADER_ERRORS','DISPLAY_TAG_COUNT','DISPLAY_FRAME_AGE','DISPLAY_REPEATS')
            required+=('DISPLAY_FRAME_SOF_LO','DISPLAY_FRAME_SOF_HI')
            if any(name not in display for name in required):
                failures.append('display frame identity evidence missing')
            else:
                for name in required:integer(display[name],name,0,0xffffffff)
                identity=(display['DISPLAY_FRAME_STATE']>>16,
                          display['DISPLAY_FRAME_TS_LO']|(display['DISPLAY_FRAME_TS_HI']<<32))
                if display_frames.get(display['DISPLAY_FRAME_ID'])!=identity:
                    failures.append('displayed frame identity differs from submitted historical state')
                if display['DISPLAY_FRAME_STATE']&3!=3 or display['DISPLAY_FRAME_AGE']>=20_000_000:
                    failures.append('displayed historical frame stale or invalid')
                if display['DISPLAY_HEADER_ERRORS']!=0:failures.append('display metadata prefix errors')
                if display['DISPLAY_TAG_COUNT']==0:failures.append('no displayed metadata SOF')
                sof=display['DISPLAY_FRAME_SOF_LO']|(display['DISPLAY_FRAME_SOF_HI']<<32)
                observed=(display['DISPLAY_TAG_COUNT'],sof)
                if sof<identity[1]:failures.append('OSD SOF acceptance precedes associated reception')
                if index<len(anchors):
                    a=anchors[index]
                    upper=a['pl_ticks64']+(status_time-a['host_anchor_ns']+a['anchor_uncertainty_ns'])//10+500_000
                    if sof>upper:failures.append('OSD acceptance timestamp beyond observed PL clock')
                if observed not in observed_sofs:
                    observed_sofs.add(observed)
                    osd_latencies.append((sof-identity[1])/100_000)
                    display_ages.append(display['DISPLAY_FRAME_AGE']/100_000)
        previous_sequence=sequence
    if not safe_responses or min(safe_responses)>300:failures.append('no fresh locked-zero STOP response within 300ms')
    if len(fresh_sequences)<max(2,int(duration/.7)):failures.append('insufficient distinct fresh CAR feedback')
    if require_hardware and not osd_latencies:failures.append('no sampled OSD acceptance timing evidence')
    if max(osd_latencies+[0])>=200:failures.append('OSD acceptance frame age reached 200ms')
    if header.get('video_enabled') is not True:failures.append('joint video evidence missing')
    if frame_times and ((frame_times[0][0]-started)/1e9>3 or (ended-frame_times[-1][1])/1e6>200):
        failures.append('camera frames do not cover active session start/end')
    if timing['invalid_associations']:failures.append('invalid frame association')
    if video['measured_fps'] is None or video['measured_fps']<min_fps:failures.append('decoded frame fps below threshold')
    if video['interval_p95_ms'] is None or video['interval_p95_ms']>max_interval_p95_ms:failures.append('decoded frame interval p95 exceeded threshold')
    drops=video['inferred_drops'];drop_rate=drops/(frame_count+drops) if frame_count+drops else 1
    if drop_rate>.05:failures.append('inferred decoded-frame drop rate exceeded 5 percent')
    if timing['receive_to_submit_ms']['p95'] is None or timing['receive_to_submit_ms']['p95']>max_submit_p95_ms:failures.append('software submission p95 exceeded threshold')
    if timing['clock_uncertainty_ms']['max'] is None or timing['clock_uncertainty_ms']['max']>max_uncertainty_ms:failures.append('clock uncertainty exceeded threshold')
    for name in ('us','qei0','qei1','risk'):
        if timing[name+'_age_ms']['max'] is None or timing[name+'_age_ms']['max']>=200:
            failures.append(f'{name} frame-associated sample exceeded 200ms age')
    return {'schema':'car-joint-audit/v1','hardware':header['hardware'],'passed':not failures,
            'failures':sorted(set(failures)),'duration_s':duration,'samples':len(anchors),'frames':frame_count,
            'control_gap_ms':distribution(gaps),'association_metrics':timing,'video_metrics':video,
            'acquisition_health_checked':True,'odometry_health_required':require_hardware,
            'sampled_osd_acceptance_ms':distribution(osd_latencies),
            'sampled_displayed_frame_age_ms':distribution(display_ages),
            'osd_timing_scope':'sampled PL base-OSD SOF acceptance, may omit intermediate frames; not HDMI scanout',
            'journal_sha256':sha256(journal),'summary_sha256':sha256(summary),
            'thresholds':{'minimum_duration_s':minimum_duration_s,'min_fps':min_fps,
                          'max_interval_p95_ms':max_interval_p95_ms,'max_submit_p95_ms':max_submit_p95_ms,
                          'max_uncertainty_ms':max_uncertainty_ms,'max_control_gap_ms':max_control_gap_ms,
                          'max_sample_age_ms':200,'max_inferred_drop_rate':.05},
            'scope':'log consistency and decoded-frame software timing; no exposure/scanout proof'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--minimum-duration',type=float,default=1800)
    parser.add_argument('--software-only',action='store_true')
    parser.add_argument('--expected-identity',type=Path)
    parser.add_argument('--package-dir',type=Path)
    parser.add_argument('--calibration',type=Path)
    args=parser.parse_args()
    if (args.package_dir is None)!=(args.calibration is None):
        parser.error('--package-dir and --calibration must be supplied together')
    if args.package_dir is not None and args.expected_identity is not None:
        parser.error('select verified package files or a software expected identity')
    if not args.software_only and args.package_dir is None:
        parser.error('hardware audit requires --package-dir and --calibration from the tested deployment')
    try:
        expected=(expected_identity_from_package(args.package_dir,args.calibration) if args.package_dir else
                  json.loads(args.expected_identity.read_text(encoding='utf-8')) if args.expected_identity else None)
        result=inspect(args.directory/'joint.jsonl',args.directory/'joint_summary.json',minimum_duration_s=args.minimum_duration,
                       require_hardware=not args.software_only,
                       expected_identity=expected)
        (args.directory/'joint_audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print('JOINT_EVIDENCE_'+('PASS' if result['passed'] else 'FAIL')+' '+json.dumps(result))
        raise SystemExit(0 if result['passed'] else 1)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print(f'JOINT_EVIDENCE_INVALID: {exc}',file=__import__('sys').stderr);raise SystemExit(1)
