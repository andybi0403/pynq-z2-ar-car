"""Presentation-only motion estimates. Never used for control or acceptance.

All published numbers are labelled estimates; raw registers and their validity
are left untouched. A stationary assumption is explicit, not inferred from a
zero drive request. Nonzero PWM prediction requires an explicit measured model.
"""
import json
import math
from pathlib import Path

TICK_HZ = 100_000_000


class MeasuredDriveModel:
    def __init__(self, payload):
        if (not isinstance(payload, dict) or set(payload) != {'schema','measured','provenance','points'}
                or payload['schema'] != 'car-display-drive-model/v1'
                or payload['measured'] is not True
                or not isinstance(payload['provenance'], str) or not payload['provenance'].strip()):
            raise ValueError('display model requires measured data and provenance')
        points = payload['points']
        if not isinstance(points, list) or len(points) < 2:
            raise ValueError('display model needs zero plus at least one measured PWM point')
        previous = (-1, -1)
        for point in points:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError('display model points must be [PWM, mm/s]')
            pwm, speed = point
            if (type(pwm) is not int or not 0 <= pwm <= 2400 or type(speed) not in (int,float)
                    or not math.isfinite(speed) or not 0 <= speed <= 5000
                    or pwm <= previous[0] or speed < previous[1]):
                raise ValueError('invalid or unordered display model point')
            previous = (pwm, speed)
        if points[0] != [0,0]:
            raise ValueError('display model must start at [0,0]')
        self.points = tuple(tuple(p) for p in points)
        self.provenance = payload['provenance']

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text('utf8')))

    def payload(self):
        return {'schema':'car-display-drive-model/v1','measured':True,
                'provenance':self.provenance,'points':[list(p) for p in self.points]}

    def speed(self, pwm):
        magnitude = abs(pwm)
        if magnitude > self.points[-1][0]:
            return None  # No extrapolation beyond measured PWM.
        for (p0,v0),(p1,v1) in zip(self.points,self.points[1:]):
            if p0 <= magnitude <= p1:
                value = v0 + (v1-v0)*(magnitude-p0)/(p1-p0)
                return -value if pwm < 0 else value
        return None


class MotionDisplayEstimator:
    def __init__(self, *, model=None, stationary_assumed=False, hold_s=1.,
                 tau_s=.25, slew_mm_s2=600., max_speed_mm_s=2000.):
        if model is not None and not isinstance(model, MeasuredDriveModel):
            raise ValueError('validated measured display model required')
        if type(stationary_assumed) is not bool:
            raise ValueError('stationary assumption must be boolean')
        for value in (hold_s,tau_s,slew_mm_s2,max_speed_mm_s):
            if type(value) not in (int,float) or not math.isfinite(value) or value <= 0:
                raise ValueError('display tuning values must be finite and positive')
        self.model, self.stationary_assumed = model, stationary_assumed
        self.hold_s, self.tau_s = hold_s, tau_s
        self.slew_mm_s2, self.max_speed_mm_s = slew_mm_s2, max_speed_mm_s
        self._epoch = None
        self._last_tick = None
        self._good_tick = None
        self._good_target = None
        self._speed = 0.
        self._displacement = 0.
        self._travelled = 0.
        self._pose_anchored = False

    def configuration(self):
        return {'stationary_assumed':self.stationary_assumed,'hold_s':self.hold_s,
                'tau_s':self.tau_s,'slew_mm_s2':self.slew_mm_s2,
                'max_speed_mm_s':self.max_speed_mm_s,
                'drive_model':self.model.payload() if self.model else None,
                'scope':'display_only_estimates'}

    def _reset(self, epoch):
        self._epoch = epoch
        self._last_tick = self._good_tick = self._good_target = None
        self._speed = self._displacement = self._travelled = 0.
        self._pose_anchored = False

    def update(self, shot, clean_speeds, ticks64, *, car=None, car_age_s=None):
        if type(ticks64) is not int or ticks64 < 0:
            raise ValueError('display requires nonnegative PL ticks')
        epoch = (shot.odometry0.epoch, shot.odometry1.epoch)
        if epoch != self._epoch or (self._last_tick is not None and ticks64 < self._last_tick):
            self._reset(epoch)
        elapsed = 0. if self._last_tick is None else (ticks64-self._last_tick)/TICK_HZ
        self._last_tick = ticks64
        dt = min(elapsed,.1)  # Never integrate an unobserved long interval.
        good_age = None if self._good_tick is None else (ticks64-self._good_tick)/TICK_HZ
        target = None
        mode = 'unavailable'
        expiry = 0.
        reasons = [f'qei{i}_{r}' for i,s in enumerate(clean_speeds) for r in s.reasons]
        feedback = (isinstance(car,dict) and type(car_age_s) in (int,float)
                    and math.isfinite(car_age_s) and 0 <= car_age_s < .2
                    and type(car.get('lock')) is int and car['lock'] in (0,1)
                    and all(type(car.get(n)) is int and -2400 <= car[n] <= 2400 for n in ('left','right')))
        measured = all(s.valid and s.value_q16 is not None for s in clean_speeds)
        if measured:
            left,right = (s.value_q16/65536 for s in clean_speeds)
            # Presentation tolerance, not a validated vehicle fault threshold.
            if abs(left-right) > 80.+.25*max(abs(left),abs(right)):
                measured = False
                reasons.append('wheel_disagreement')
        if self.stationary_assumed:
            target,mode,expiry = 0.,'stationary_assumption',.2
        elif measured:
            age_ticks = max((ticks64-s.source_timestamp)&0xffffffff for s in clean_speeds)
            good_age = age_ticks/TICK_HZ
            if good_age < .2:
                target = (left+right)/2
                self._good_tick = ticks64-age_ticks  # Duplicate reads do not renew it.
                self._good_target = target
                mode,expiry = 'smoothed',.2-good_age
        if target is None and good_age is not None and 0 <= good_age < self.hold_s:
            target,mode,expiry = self._good_target,'hold',self.hold_s-good_age
        if target is None and feedback:
            if car['lock'] and car['left']==car['right']==0:
                target,mode,expiry = 0.,'locked_zero_estimate',.2-car_age_s
            elif self.model is not None and not car['lock']:
                speeds = [self.model.speed(car[n]) for n in ('left','right')]
                if all(v is not None for v in speeds):
                    target,mode,expiry = sum(speeds)/2,'measured_model_estimate',.2-car_age_s
                else:
                    reasons.append('model_outside_measured_range')
        available = target is not None
        if available:
            target = max(-self.max_speed_mm_s,min(self.max_speed_mm_s,target))
            # Stationary demonstration is an explicit assumption, not a QEI observation.
            if mode == 'stationary_assumption':
                self._speed = 0.
            else:
                blend = (target-self._speed)*(-math.expm1(-dt/self.tau_s))
                bound = self.slew_mm_s2*dt
                self._speed += max(-bound,min(bound,blend))
            if mode == 'smoothed' and shot.odometry_valid:
                disp,path = shot.displacement_q16/65536,shot.travelled_q16/65536
                if not self._pose_anchored:
                    self._displacement,self._travelled = disp,path
                    self._pose_anchored = True
                else:
                    bound = (abs(self._speed)+50.)*dt
                    self._displacement += max(-bound,min(bound,disp-self._displacement))
                    self._travelled += max(0.,min(bound,path-self._travelled))
            else:
                self._displacement += self._speed*dt
                self._travelled += abs(self._speed)*dt
        else:
            self._speed = 0.  # A future recovery starts from a neutral display state.
        return {'available':available,'estimated':True,'mode':mode,
                'speed_mm_s':self._speed if available else None,
                'displacement_mm':self._displacement if available else None,
                'travelled_mm':self._travelled if available else None,
                'measurement_age_s':good_age,'valid_for_s':max(0.,expiry),
                'reasons':reasons,'scope':'display_only_estimates'}
