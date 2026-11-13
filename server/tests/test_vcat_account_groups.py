"""Group completion uses actual membership and never guesses from missing names."""
import copy
import unittest
from unittest.mock import Mock

from server.publishing.vcat import VcatClient, READ_TOOLS


class VcatAccountGroupTests(unittest.TestCase):
    def client(self, accounts, memberships=(), groups=()):
        client = object.__new__(VcatClient)
        client.evaluate = Mock(return_value=copy.deepcopy(memberships))
        def call(name, arguments):
            if name == 'vcat_list_accounts':
                start = (arguments['page'] - 1) * arguments['pageSize']
                return {'total': len(accounts), 'list': copy.deepcopy(accounts[start:start + arguments['pageSize']])}
            if name == 'vcat_list_groups':
                return {'total': len(groups), 'list': copy.deepcopy(groups)}
            raise AssertionError(name)
        client.call = Mock(side_effect=call)
        return client

    def account(self, uid='a', platform='Channels', name=None):
        return {'uid': uid, 'platform': platform, 'groupName': name, 'loginStatus': '登录失效'}

    def member(self, uid='a', platform='Channels', group=0):
        return {'uid': uid, 'platform': platform, 'groupId': group}

    def test_default_group_zero_is_named_even_when_login_is_invalid(self):
        client = self.client([self.account()], [self.member()])
        self.assertEqual('默认分组', client.accounts(resolve_groups=True)[0]['groupName'])
        self.assertEqual(['vcat_list_accounts'], [c.args[0] for c in client.call.call_args_list])
        expression = client.evaluate.call_args.args[0]
        self.assertIn('groupId:a.groupId??a.group_id??null', expression)
        self.assertNotIn('return accounts;', expression)

    def test_custom_name_resolved_by_id_including_string_id(self):
        client = self.client([self.account()], [self.member(group='12')], [{'id': 12, 'name': '兔子'}])
        self.assertEqual('兔子', client.accounts(resolve_groups=True)[0]['groupName'])
        client.call.assert_any_call('vcat_list_groups', {})

    def test_existing_names_are_preserved_without_extra_reads(self):
        client = self.client([self.account(name='咩咩')])
        self.assertEqual('咩咩', client.accounts(resolve_groups=True)[0]['groupName'])
        client.evaluate.assert_not_called()

    def test_other_consumers_keep_existing_behavior(self):
        client = self.client([self.account()])
        self.assertIsNone(client.accounts()[0]['groupName'])
        client.evaluate.assert_not_called()

    def test_platform_and_uid_together_identify_membership(self):
        client = self.client([self.account()], [self.member(group=12), self.member(platform='Douyin', group=0)], [{'id': 12, 'name': '兔子'}])
        self.assertEqual('兔子', client.accounts(resolve_groups=True)[0]['groupName'])

    def test_unknown_membership_is_not_assumed_to_be_default(self):
        for memberships in ([], [self.member(group=None)], [self.member(group=0), self.member(group=12)]):
            with self.subTest(memberships=memberships):
                with self.assertRaisesRegex(RuntimeError, '分组返回不完整'):
                    self.client([self.account()], memberships).accounts(resolve_groups=True)

    def test_unknown_custom_group_is_not_assumed_to_be_default(self):
        with self.assertRaisesRegex(RuntimeError, '分组返回不完整'):
            self.client([self.account()], [self.member(group=99)]).accounts(resolve_groups=True)

    def test_incomplete_group_list_and_conflicting_names_are_rejected(self):
        for groups in ({'total': 2, 'list': [{'id': 12, 'name': '兔子'}]},
                       {'total': 2, 'list': [{'id': 12, 'name': '兔子'}, {'id': 12, 'name': '咩咩'}]},
                       {'total': 1, 'list': [None]}):
            with self.subTest(groups=groups):
                client = self.client([self.account()], [self.member(group=12)])
                original = client.call.side_effect
                client.call.side_effect = lambda name, args: groups if name == 'vcat_list_groups' else original(name, args)
                with self.assertRaisesRegex(RuntimeError, '分组返回不完整'):
                    client.accounts(resolve_groups=True)

    def test_whitespace_group_name_is_completed(self):
        client = self.client([self.account(name='  ')], [self.member()])
        self.assertEqual('默认分组', client.accounts(resolve_groups=True)[0]['groupName'])

    def test_empty_accounts_need_no_membership_reads(self):
        client = self.client([])
        self.assertEqual([], client.accounts(resolve_groups=True))
        client.evaluate.assert_not_called()

    def test_all_pages_are_completed(self):
        accounts = [self.account(str(i)) for i in range(123)]
        client = self.client(accounts, [self.member(str(i)) for i in range(123)])
        rows = client.accounts(resolve_groups=True)
        self.assertEqual(123, len(rows))
        self.assertTrue(all(a['groupName'] == '默认分组' for a in rows))
        self.assertEqual([1, 2], [c.args[1]['page'] for c in client.call.call_args_list])

    def test_group_list_is_allowed_on_readonly_connection(self):
        self.assertIn('vcat_list_groups', READ_TOOLS)
        client = object.__new__(VcatClient)
        client.account_data = client.writable = False
        client.request = Mock(return_value={'result': {'content': [{'type': 'text', 'text': '{"total":0,"list":[]}'}]}})
        self.assertEqual({'total': 0, 'list': []}, client.call('vcat_list_groups', {}))
        with self.assertRaises(ValueError):
            client.call('vcat_move_accounts', {'uids': ['a'], 'groupId': 12})


if __name__ == '__main__':
    unittest.main()
