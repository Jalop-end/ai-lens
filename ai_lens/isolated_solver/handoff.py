"""UI-neutral generation gate. Call select as soon as a new task becomes current."""
from dataclasses import dataclass
import threading

@dataclass(frozen=True)
class Ticket:
    generation: int
    request_id: str

class LatestOnly:
    """No result cache: caller must clear displayed old result when selecting a task."""
    def __init__(self):
        self._lock=threading.Lock()
        self._generation=0
        self._current=None
    def select(self,request_id):
        if type(request_id) is not str or not request_id:
            raise ValueError('a validated request identifier is required')
        with self._lock:
            self._generation+=1
            self._current=Ticket(self._generation,request_id)
            return self._current
    def invalidate(self):
        with self._lock:
            self._generation+=1
            self._current=None
    def accepts(self,ticket,answer):
        with self._lock:
            return (type(ticket) is Ticket and ticket==self._current
                    and type(answer) is dict and answer.get('request_id')==ticket.request_id)
