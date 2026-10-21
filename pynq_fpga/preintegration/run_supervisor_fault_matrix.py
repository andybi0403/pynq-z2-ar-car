"""Reproducible software fault evidence with actual production C outputs."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host/tests'))
from test_supervisor_c_loop import SupervisorProductionCTests
from supervisor_c_fixture import PRODUCTION_C_IDENTITY


def run(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    results=[]
    for test in unittest.defaultTestLoader.loadTestsFromTestCase(SupervisorProductionCTests):
        result=unittest.TestResult();test.run(result)
        failures=[text for _,text in result.failures+result.errors]
        h=getattr(test,'fixture',None)
        trace={'hardware':False,'pl':'stimulated_register_fixture','uart':'9600_baud_8N1_delivery_model',
               'production_c':PRODUCTION_C_IDENTITY,'scenario':test._testMethodName,
               'passed':result.wasSuccessful(),'failures':failures}
        if h:
            trace.update(control=h.control_log,uart_tx=[{'host_ms':t,'kind':kind,'frame':frame.decode('ascii')} for t,kind,frame in h.sent],
                         stm32_c_events=h.c.log,rejected_intents=h.rejected_intents,
                         mmio_errors=h.errors,pl_command_writes=h.pl.command_writes)
        path=output/(test._testMethodName+'.json')
        path.write_text(json.dumps(trace,indent=2)+'\n',encoding='utf-8')
        results.append({'scenario':test._testMethodName,'passed':result.wasSuccessful(),
                        'trace':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                        'failures':failures})
    files=[ROOT/'host/control_supervisor.py',ROOT/'host/perception_client.py',
           ROOT.parent/'stm32预备程序/pc/pynq_link.py',
           ROOT/'host/tests/supervisor_c_fixture.py',ROOT/'host/tests/test_supervisor_c_loop.py',Path(__file__)]
    report={'schema':'car-supervisor-fault-matrix/v1','hardware':False,
            'scope':'actual host/client/UART encoder and compiled production STM32 policy; simulated PL registers and transport',
            'production_c':PRODUCTION_C_IDENTITY,
            'sources':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
            'scenarios':results,'passed':all(r['passed'] for r in results)}
    (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=run(args.output)
    print('SUPERVISOR_FAULT_MATRIX_'+('PASS' if report['passed'] else 'FAIL')+f" ({len(report['scenarios'])} scenarios; hardware=false)")
    raise SystemExit(0 if report['passed'] else 1)
