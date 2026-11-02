"""Bounded journal worker; disk and JSON work never runs on submitters."""
import pickle
import json
import queue
import threading
import time

def snapshot_copy(value):
    """Detach trusted in-process telemetry without Python recursive deepcopy.

    Bytes are created and consumed here, never accepted from an external input.
    Pickle preserves nested mutation isolation and shared references.
    """
    return pickle.loads(pickle.dumps(value, protocol=4))

class AsyncJournal:
    def __init__(self, stream, capacity=4096, max_pending_bytes=16777216):
        self.stream=stream
        self.queue=queue.Queue(maxsize=capacity)
        self.lock=threading.Lock()
        self.stopping=threading.Event()
        self.max_pending_bytes=max_pending_bytes;self.pending_bytes=0
        self.accepted=0; self.written=0; self.dropped=0; self.flushes=0
        self.error=None
        self.worker=threading.Thread(target=self._run,name='journal-writer',daemon=True)
        self.worker.start()
    def submit(self, item, critical=False):
        # Callers may mutate their own state immediately after this returns.
        # C-level immutable snapshot avoids two Python traversals per record.
        # Only internal objects enter this queue; never deserialize external bytes.
        frozen=pickle.dumps(item,protocol=4)
        size=len(frozen)
        with self.lock:
            if self.stopping.is_set() or self.error:
                self.dropped+=1
                return False
            if size>1048576 or self.pending_bytes+size>self.max_pending_bytes:
                self.dropped+=1
                return False
            try:self.queue.put_nowait((frozen,critical,size))
            except queue.Full:
                self.dropped+=1
                return False
            self.pending_bytes+=size
            self.accepted+=1
            return True
    def snapshot(self):
        with self.lock:
            return {'policy':'async_bounded_1s_or_256KiB_critical_flush',
                    'records':self.accepted,'written_records':self.written,
                    'dropped_records':self.dropped,'pending_records':self.queue.qsize(),
                    'pending_bytes':self.pending_bytes,'snapshot_encoding':'internal_pickle4','flushes':self.flushes,'error':self.error}
    def _run(self):
        pending=[]; size=0; flushed=time.monotonic()
        def flush():
            nonlocal size,flushed
            if pending:
                self.stream.write(''.join(pending));self.stream.flush()
                pending.clear();size=0;flushed=time.monotonic()
                with self.lock:self.flushes+=1
        try:
            while not self.stopping.is_set() or not self.queue.empty():
                try:item,critical,charge=self.queue.get(timeout=.1)
                except queue.Empty:
                    if time.monotonic()-flushed>=1:flush()
                    continue
                with self.lock:self.pending_bytes-=charge
                line=json.dumps(pickle.loads(item),separators=(',',':'))+'\n'
                if len(line)>1048576:raise ValueError('journal record exceeds 1MiB')
                pending.append(line);size+=len(line)
                with self.lock:self.written+=1
                if critical or size>=262144 or time.monotonic()-flushed>=1:flush()
            flush()
        except Exception as exc:
            with self.lock:self.error=type(exc).__name__+': '+str(exc)
    def close(self, timeout=3):
        with self.lock:self.stopping.set()
        self.worker.join(timeout)
        state=self.snapshot()
        if self.worker.is_alive():raise TimeoutError('journal writer did not terminate; stream retained')
        if state['error'] or state['dropped_records']:
            raise RuntimeError('journal evidence incomplete: '+str(state))
