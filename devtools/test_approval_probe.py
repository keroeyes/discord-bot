import concurrent.futures
import unittest

from approval_probe import ApprovalProbe


class ApprovalProbeTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.probe = ApprovalProbe(clock=lambda: self.now)
        self.binding = ('synthetic-user', 'synthetic-job', 'synthetic-revision')
        self.token = self.probe.propose(*self.binding, ttl=10)

    def test_normal_approval_executes_once(self):
        self.assertTrue(self.probe.fake_delete(self.token, *self.binding))
        self.assertEqual(self.probe.executions, 1)

    def test_replay_never_executes_twice(self):
        self.assertTrue(self.probe.fake_delete(self.token, *self.binding))
        self.assertFalse(self.probe.fake_delete(self.token, *self.binding))
        self.assertEqual(self.probe.executions, 1)

    def test_other_user_is_rejected_without_consuming_owner_approval(self):
        self.assertFalse(self.probe.fake_delete(self.token, 'other', *self.binding[1:]))
        self.assertEqual(self.probe.executions, 0)
        self.assertTrue(self.probe.fake_delete(self.token, *self.binding))

    def test_other_job_is_rejected(self):
        self.assertFalse(self.probe.fake_delete(self.token, self.binding[0], 'other', self.binding[2]))
        self.assertEqual(self.probe.executions, 0)

    def test_changed_target_is_rejected(self):
        self.assertFalse(self.probe.fake_delete(self.token, *self.binding[:2], 'changed'))
        self.assertEqual(self.probe.executions, 0)

    def test_reproposal_revokes_old_approval(self):
        new = self.probe.propose(*self.binding[:2], 'changed')
        self.assertFalse(self.probe.fake_delete(self.token, *self.binding))
        self.assertEqual(self.probe.executions, 0)
        self.assertTrue(self.probe.fake_delete(new, *self.binding[:2], 'changed'))

    def test_expiry_boundary_is_rejected(self):
        self.now = 110.0
        self.assertFalse(self.probe.fake_delete(self.token, *self.binding))
        self.assertEqual(self.probe.executions, 0)

    def test_unknown_token_cannot_authorize(self):
        self.assertFalse(self.probe.fake_delete('0' * 64, *self.binding))
        self.assertEqual(self.probe.executions, 0)

    def test_parallel_replay_has_only_one_effect(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.probe.fake_delete(self.token, *self.binding), range(32)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(self.probe.executions, 1)

    def test_new_instance_does_not_restore_approval(self):
        other = ApprovalProbe(clock=lambda: self.now)
        self.assertFalse(other.fake_delete(self.token, *self.binding))
        self.assertEqual(other.executions, 0)

    def test_invalid_bindings_and_expiries_are_rejected(self):
        for ttl in [0, -1, 301, True, '60', float('nan'), float('inf')]:
            with self.subTest(ttl=ttl), self.assertRaises(ValueError):
                self.probe.propose(*self.binding, ttl=ttl)
        for actor in ['', ' ', None, 'x' * 257]:
            with self.subTest(actor=actor), self.assertRaises(ValueError):
                self.probe.propose(actor, *self.binding[1:])
        self.assertEqual(self.probe.executions, 0)

    def test_capacity_is_bounded_and_expired_entries_are_reclaimed(self):
        probe = ApprovalProbe(clock=lambda: self.now, capacity=1)
        probe.propose(*self.binding, ttl=10)
        with self.assertRaises(ValueError):
            probe.propose('other', 'other-job', 'other-revision')
        self.now = 110.0
        token = probe.propose('other', 'other-job', 'other-revision')
        self.assertTrue(probe.fake_delete(token, 'other', 'other-job', 'other-revision'))


if __name__ == '__main__':
    unittest.main()
