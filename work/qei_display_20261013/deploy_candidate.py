import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp'))
import video_six_uart_deploy_20261009 as deploy
deploy.REFERENCE=ROOT/'pynq_fpga/lab/task7_8_lab_only_v09_qei_retest_20261012_r2'
deploy.REMOTE_REFERENCE='/home/xilinx/qei_retest_20261012_candidate_r2'
deploy.OUT=ROOT/'pynq_fpga/preintegration/evidence/qei_display_20261013'
deploy.deploy('v09_qei_display_20261013_r2','qei_display_20261013_candidate_r2')
