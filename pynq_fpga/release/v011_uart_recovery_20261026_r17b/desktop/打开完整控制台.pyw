from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'tools'))
from open_car_console import main
raise SystemExit(main())
