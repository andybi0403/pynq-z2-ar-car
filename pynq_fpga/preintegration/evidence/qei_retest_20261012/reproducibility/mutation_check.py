"""Prove new host regression tests reject the saved pre-change algorithm."""
import importlib.util, json, sys, types, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'pynq_fpga/host'))
sys.path.insert(0,str(ROOT/'pynq_fpga/host/tests'))
import test_qei_quality as tests
prior=ROOT/'pynq_fpga/lab/task7_8_lab_only_v09_qei_quality_20261012_r1/qei_quality.py'
name='qei_prior_mutation_reference'
spec=importlib.util.spec_from_file_location(name,prior)
module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
selected=[
 'test_reversal_does_not_publish_the_previous_direction',
 'test_reversal_through_zero_and_other_channel_are_independent',
 'test_sequence_regression_and_half_wrap_ambiguity_are_rejected',
 'test_long_gap_requires_new_window_even_if_latest_batch_is_fresh',
]
saved=tests.QeiDisplayFilter;tests.QeiDisplayFilter=module.QeiDisplayFilter
results=[]
try:
    for method in selected:
        result=unittest.TestResult();tests.QeiQualityTests(method).run(result)
        results.append({'test':method,'failures':len(result.failures),'errors':len(result.errors),'old_algorithm_rejected':bool(result.failures) and not result.errors})
finally:
    tests.QeiDisplayFilter=saved
import qei_quality
saved_fault=qei_quality.fault_reasons
try:
    qei_quality.fault_reasons=module.fault_reasons
    method='test_divider_recovery_does_not_erase_overrun_diagnostic'
    def overrun_rejected():
        decision=tests.evaluate_snapshot(tests.shot(info=1<<12),1000)
        unittest.TestCase().assertFalse(decision.permit)
        unittest.TestCase().assertIn('qei0_velocity_overrun',decision.reasons)
    result=unittest.TestResult();unittest.FunctionTestCase(overrun_rejected).run(result)
    results.append({'test':method,'failures':len(result.failures),'errors':len(result.errors),'old_algorithm_rejected':bool(result.failures) and not result.errors})
finally:
    qei_quality.fault_reasons=saved_fault
assert all(r['old_algorithm_rejected'] for r in results)
print(json.dumps({'scope':'offline algorithm mutation, not hardware','baseline_source':str(prior),'checks':results},indent=2))
