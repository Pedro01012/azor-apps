"""Single-owner telemetry. HTTP readers never spawn a second collector."""
import copy
import threading
import time

class CpuCounter:
    def __init__(self,clock=time.monotonic,minimum_interval=.5):
        self.clock=clock;self.minimum_interval=minimum_interval
        self.lock=threading.Lock();self.previous=None;self.at=None;self.value=None
    def sample(self,read):
        with self.lock:
            at=self.clock()
            if self.at is not None and at-self.at<self.minimum_interval:return self.value
            now=read()
            if now is None:return None
            old=self.previous;self.previous=now;self.at=at
            if old is None:self.value=None;return None
            idle,kernel,user=(b-a for a,b in zip(old,now))
            total=kernel+user
            self.value=round(100*(total-idle)/total,1) if total>0 and 0<=idle<=total and kernel>=0 and user>=0 else None
            return self.value

class DemandSampler:
    IDLE_GRACE=8.
    def __init__(self,collect,release=lambda:None,on_error=lambda message:None):
        self.collect=collect;self.release=release;self.on_error=on_error
        self._lock=threading.RLock();self._wake=threading.Event()
        self._thread=None;self._sample=None;self._demand_until=0.;self.interval=1.5
        self.error=None
    def request(self,interval=None):
        with self._lock:
            if interval is not None:self.interval=min(5.,max(1.,float(interval)))
            self._demand_until=time.monotonic()+self.IDLE_GRACE
            if self._thread is None:
                self._wake.clear()
                self._thread=threading.Thread(target=self._loop,name='azor-monitor-sampler',daemon=True)
                self._thread.start()
            sample=copy.deepcopy(self._sample)
            age=max(0.,time.time()-sample['ts']) if sample else None
            if sample is None or age>max(5.,self.interval*3):
                return {'ts':None,'loading':True,'stale':sample is not None,'age_s':age,'error':self.error}
            return {**sample,'loading':False,'stale':False,'age_s':round(age,2),'error':self.error}
    def _loop(self):
        while True:
            with self._lock:
                if time.monotonic()>self._demand_until:
                    # Keep ownership through release so a new worker cannot lose its feed.
                    try:self.release()
                    except Exception as exc:self.on_error(str(exc))
                    self._thread=None
                    return
                interval=self.interval
            try:
                sample=self.collect()
                with self._lock:self._sample=sample;self.error=None
            except Exception as exc:
                with self._lock:self.error=str(exc)
                self.on_error(str(exc))
            self._wake.wait(interval);self._wake.clear()
    def stop(self):
        with self._lock:self._demand_until=0.;self._wake.set()
    def wait_stopped(self,timeout=3):
        with self._lock:worker=self._thread
        if worker and worker is not threading.current_thread():worker.join(timeout)
        return not (worker and worker.is_alive())
