import json,subprocess,time
before=time.time();mono=time.monotonic()
subprocess.run(['date','-u','-s','@'+str(1791912149.560232)],check=True,capture_output=True,text=True)
after=time.time();elapsed=time.monotonic()-mono
assert 0<=elapsed<5
print(json.dumps({'kind':'BOARD_WALL_CLOCK_SYNC','before_epoch':before,'after_epoch':after,
                 'PC_source_epoch':1791912149.560232,'monotonic_elapsed_s':elapsed,
                 'scope':'calendar alignment only; UART/PL/STM32 ages remain monotonic'}))
