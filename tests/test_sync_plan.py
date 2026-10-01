import unittest

from sync_plan import plan


class SyncPlanTests(unittest.TestCase):
    def setUp(self):
        self.local = [{'id': 1, 'title': 'Portal', 'platform': 'PC - Steam', 'status': 'Хочу пройти', 'notes': 'keep'}]
        self.remote = [{'sync_key': '42', 'title': 'Portal', 'platform': 'PC', 'status': 'Хочу пройти'}]
        self.links = [{'local_id': 1, 'remote_id': '42', 'local_status': 'Хочу пройти', 'remote_status': 'Хочу пройти'}]

    def action(self):
        return plan(self.local, self.remote, self.links)[0]['action']

    def test_local_change_pushes(self):
        self.local[0]['status'] = 'Играю'
        self.assertEqual(self.action(), 'push')

    def test_remote_change_pulls(self):
        self.remote[0]['status'] = 'Пройдено'
        self.assertEqual(self.action(), 'pull')

    def test_two_changes_need_choice(self):
        self.local[0]['status'] = 'Играю'
        self.remote[0]['status'] = 'Пройдено'
        self.assertEqual(self.action(), 'conflict')

    def test_converged_changes_equal(self):
        self.local[0]['status'] = self.remote[0]['status'] = 'Играю'
        self.assertEqual(self.action(), 'equal')

    def test_no_baseline_never_overwrites(self):
        self.links[0].pop('local_status')
        self.remote[0]['status'] = 'Играю'
        self.assertEqual(self.action(), 'conflict')

    def test_deleted_remote_is_not_deleted_locally(self):
        self.remote.clear()
        self.assertEqual(self.action(), 'missing')
        self.assertEqual(self.local[0]['notes'], 'keep')

    def test_unique_titles_link_without_write(self):
        self.assertEqual(plan(self.local, self.remote, [])[0]['action'], 'link')
        self.assertEqual(self.local[0]['status'], 'Хочу пройти')

    def test_repeated_playthroughs_need_choice(self):
        self.remote.append(dict(self.remote[0], sync_key='43'))
        self.assertEqual(plan(self.local, self.remote, [])[0]['action'], 'ambiguous')

    def test_new_local_needs_catalog_match(self):
        self.assertEqual(plan(self.local, [], [])[0]['action'], 'match_required')

    def test_new_remote_can_be_imported(self):
        self.assertEqual(plan([], self.remote, [])[0]['action'], 'local_add')

    def test_links_reject_duplicate_targets(self):
        with self.assertRaises(ValueError):
            plan(self.local, self.remote, self.links * 2)


if __name__ == '__main__':
    unittest.main()
