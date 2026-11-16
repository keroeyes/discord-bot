"""Offline approval experiment. Never imports or calls the bot or a service.

Not an authorization service: identities and consent must be authenticated by
the host before any future integration. In-memory state fails closed on restart.
"""
from dataclasses import dataclass
import math
import secrets
import threading
import time


@dataclass(frozen=True)
class Proposal:
    actor: str
    job: str
    target: str
    expires_at: float


class ApprovalProbe:
    """Single-process, bounded, one-use approvals for a fake delete operation.

    target is a synthetic resource/revision digest, not user memory. A token is
    opaque; no caller-supplied claim of approval can create a pending proposal.
    Consumption and the fake effect share one lock. Real external effects would
    require durable dispatch records and backend idempotency, not just this lock.
    """
    def __init__(self, *, clock=time.monotonic, capacity=128):
        if type(capacity) is not int or capacity < 1:
            raise ValueError('Invalid capacity')
        self.clock = clock
        self.capacity = capacity
        self._pending = {}
        self._lock = threading.Lock()
        self.executions = 0

    def _now(self):
        now = self.clock()
        if not math.isfinite(now):
            raise ValueError('Invalid clock')
        return now

    @staticmethod
    def _validate_binding(actor, job, target):
        if any(not isinstance(x, str) or not x.strip() or len(x) > 256
               for x in (actor, job, target)):
            raise ValueError('Invalid proposal binding')

    def propose(self, actor, job, target, *, ttl=60):
        self._validate_binding(actor, job, target)
        if isinstance(ttl, bool) or not isinstance(ttl, (int, float)):
            raise ValueError('Invalid expiry')
        if not math.isfinite(ttl) or not 0 < ttl <= 300:
            raise ValueError('Invalid expiry')
        with self._lock:
            now = self._now()
            self._pending = {key: value for key, value in self._pending.items()
                             if value.expires_at > now}
            # One pending proposal per actor/job; revising the target revokes
            # the previous token instead of leaving old consent usable.
            self._pending = {key: value for key, value in self._pending.items()
                             if (value.actor, value.job) != (actor, job)}
            if len(self._pending) >= self.capacity:
                raise ValueError('Approval capacity reached')
            token = secrets.token_hex(32)
            self._pending[token] = Proposal(actor, job, target, now + ttl)
            return token

    def fake_delete(self, token, actor, job, target):
        """Return accepted/rejected; the only effect is a synthetic counter."""
        self._validate_binding(actor, job, target)
        if not isinstance(token, str) or len(token) != 64:
            return False
        with self._lock:
            proposal = self._pending.get(token)
            if proposal is None:
                return False
            if self._now() >= proposal.expires_at:
                del self._pending[token]
                return False
            if (actor, job, target) != (proposal.actor, proposal.job, proposal.target):
                return False
            del self._pending[token]
            self.executions += 1
            return True


if __name__ == '__main__':
    probe = ApprovalProbe()
    approval = probe.propose('synthetic-user', 'synthetic-job', 'synthetic-revision')
    accepted = probe.fake_delete(approval, 'synthetic-user', 'synthetic-job', 'synthetic-revision')
    replay = probe.fake_delete(approval, 'synthetic-user', 'synthetic-job', 'synthetic-revision')
    if not accepted or replay or probe.executions != 1:
        raise SystemExit('offline approval probe failed')
    print('offline approval probe: accepted once; replay rejected; no service called')
