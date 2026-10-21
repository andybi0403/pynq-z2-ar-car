"""Persist concurrent software-only traces and prove hardware gates stay closed."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'host'))
sys.path.insert(0,str(ROOT/'tests'))
from test_joint_runtime import JointTests
from joint_evidence import inspect
from runtime_identity import runtime_hashes


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('output must be a new or empty evidence directory')
    runner=JointTests().runner(args.output)
    runner.identity={'fixture':True,'runtime_sources':runtime_hashes(),
                     'scope':'synthetic sensors/serial/display; real worker threads and child frame stream'}
    result=runner.run(3)
    audit=inspect(args.output/'joint.jsonl',args.output/'joint_summary.json',
                  minimum_duration_s=2.9,require_hardware=False)
    blocked=inspect(args.output/'joint.jsonl',args.output/'joint_summary.json')
    for name,value in [('joint_audit.json',audit),('hardware_gate_expected_fail.json',blocked)]:
        (args.output/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    if not result['passed'] or not audit['passed'] or blocked['passed']:
        print('JOINT_SOFTWARE_EVIDENCE_FAIL '+json.dumps(audit));return 1
    print(f"JOINT_SOFTWARE_EVIDENCE_PASS samples={audit['samples']} frames={audit['frames']} hardware=false")
    return 0


if __name__=='__main__':raise SystemExit(main())
