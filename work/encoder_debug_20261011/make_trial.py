import sys
from pathlib import Path
folder = Path(__file__).parent
name, ticks, seconds = sys.argv[1:4]
destination = folder/(name+'.py')
if destination.exists():
    raise FileExistsError(destination)
source = 'TRIAL_NAME = '+repr(name)+'\nFILTER_TICKS = '+str(int(ticks))+'\nDURATION = '+str(int(seconds))+'\n'
destination.write_text(source + (folder/'round2_trial.py').read_text('utf8'), 'utf8')
print(destination)
