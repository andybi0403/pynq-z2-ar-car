"""Display-only path estimate from actual STM32 PWM reports; never a control input."""
import json,math
from pathlib import Path

class DemoMileage:
    def __init__(self, config):
        if config.get('schema')!='car-demo-mileage/v1' or config.get('measured') is not False:
            raise ValueError('explicit unmeasured demo mileage model required')
        factor=config.get('mm_per_pwm_second')
        if type(factor) not in (int,float) or not math.isfinite(factor) or not 0<factor<=10:
            raise ValueError('invalid mileage factor')
        self.factor=float(factor);self.path=0.;self.previous=None;self.gaps=0
        self.config=dict(config)

    @classmethod
    def load(cls,path):return cls(json.loads(Path(path).read_text('utf8')))

    def update(self,car,sequence,received_s,now_s,session=None):
        valid=bool(car is not None and type(sequence) is int and
                   type(received_s) in (int,float) and math.isfinite(received_s) and
                   math.isfinite(now_s) and 0<=now_s-received_s<.7 and
                   all(type(car.get(k)) is int and abs(car[k])<=400 for k in ('left','right')))
        if not valid:
            if self.previous is not None:self.gaps+=1
            self.previous=None
        else:
            pwm=(abs(car['left'])+abs(car['right']))/2
            old=self.previous
            current=(session,sequence,received_s,pwm)
            if old is not None and current[:2]!=old[:2]:
                dt=received_s-old[2]
                if session==old[0] and sequence>old[1] and 0<dt<.7:
                    # Trapezoid between two actual reports, not requested PWM.
                    self.path+=(old[3]+pwm)*.5*self.factor*dt
                else:self.gaps+=1
            if old is None or current[:2]!=old[:2]:self.previous=current
        return {'estimated':True,'available':valid,'travelled_mm':self.path,
                'source':'stm32_actual_pwm_elapsed_time','measured':False,
                'model':dict(self.config),'excluded_gaps':self.gaps,
                'display_only':True}
