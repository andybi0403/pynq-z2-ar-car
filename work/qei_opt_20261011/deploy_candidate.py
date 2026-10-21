"""Deploy exact verified LAB candidate using hashes and the previous UART copy."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp'))
import video_six_uart_deploy_20261009 as deploy
deploy.REFERENCE=ROOT/'pynq_fpga/lab/task7_8_lab_only_v09_video_opt_20261011_r1'
deploy.REMOTE_REFERENCE='/home/xilinx/video_opt_20261011_candidate_a'
deploy.OUT=Path('C:/Users/39909/Documents/Codex/2026-10-11/p-g/outputs/qei_algorithm_20261012')
deploy.OUT.mkdir(parents=True,exist_ok=True)
deploy.deploy('v09_qei_quality_20261012_r1','qei_quality_20261012_candidate_r1')
