"""Deploy the final complete candidate; verify hashes rather than names."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp'))
import video_six_uart_deploy_20261009 as deploy
deploy.REFERENCE=ROOT/'pynq_fpga/lab/task7_8_lab_only_v09_qei_quality_20261012_r1'
deploy.REMOTE_REFERENCE='/home/xilinx/qei_quality_20261012_candidate_r1'
deploy.OUT=ROOT/'pynq_fpga/preintegration/evidence/qei_retest_20261012'
deploy.deploy('v09_qei_retest_20261012_r2','qei_retest_20261012_candidate_r2')
