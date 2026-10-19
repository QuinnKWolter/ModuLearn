from unittest.mock import patch
import pymysql
from django.test import SimpleTestCase, override_settings
from dashboard.kt_db_connection import get_paws_db_connection
from accounts.knowledgetree_auth import KnowledgeTreeAuthService, KnowledgeTreeAPIConnectionError


@override_settings(PAWS_DATABASE={
    'HOST': 'mysql.internal', 'PORT': 3307, 'USER': 'test', 'PASSWORD': 'test-password',
    'AGGREGATE_SCHEMA': 'aggregate_test', 'KNOWLEDGETREE_SCHEMA': 'kt_test',
    # Old deployment variables/configuration must no longer enable tunneling.
    'USE_SSH': True, 'SSH_HOST': 'obsolete.invalid',
})
class DirectDatabaseTests(SimpleTestCase):
    @patch('dashboard.kt_db_connection.pymysql.connect')
    def test_connects_to_configured_database_and_closes(self, connect):
        connection = get_paws_db_connection()
        self.assertTrue(connection.connect()[0])
        self.assertEqual(connect.call_args.kwargs['host'], 'mysql.internal')
        self.assertEqual(connect.call_args.kwargs['port'], 3307)
        self.assertEqual(connect.call_args.kwargs['database'], 'aggregate_test')
        self.assertEqual(connect.call_args.kwargs['connect_timeout'], 10)
        connection.disconnect()
        connect.return_value.close.assert_called_once()
        self.assertIsNone(connection.get_connection())

    @patch('dashboard.kt_db_connection.pymysql.connect', side_effect=pymysql.OperationalError(2003, 'unreachable'))
    def test_database_failure_is_reported_without_connection(self, connect):
        connection = get_paws_db_connection()
        self.assertFalse(connection.connect()[0])
        self.assertIsNone(connection.get_connection())
        connection.disconnect()

    @override_settings(KNOWLEDGETREE={'AUTH_ENABLED': True})
    @patch('dashboard.kt_db_connection.pymysql.connect')
    def test_kt_database_auth_still_validates_password_and_closes(self, connect):
        service = KnowledgeTreeAuthService()
        cursor = connect.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {'UserID': 7, 'Login': 'learner', 'Name': 'Learner',
            'Pass': service._md5_hash('correct'), 'email': ''}
        cursor.fetchall.return_value = []
        self.assertIsNone(service.authenticate_via_database('learner', 'wrong'))
        result = service.authenticate_via_database('learner', 'correct')
        self.assertEqual(result['user_id'], 7)
        self.assertEqual(connect.return_value.close.call_count, 2)
        self.assertIn('`kt_test`.ent_user', cursor.execute.call_args_list[0].args[0])

    @override_settings(KNOWLEDGETREE={'AUTH_ENABLED': True, 'AUTH_METHOD': 'api', 'AUTH_FALLBACK': True})
    def test_api_success_skips_database_and_api_outage_can_fallback(self):
        service = KnowledgeTreeAuthService()
        with patch.object(service, '_check_rate_limit'), patch.object(service, '_reset_rate_limit'), \
                patch.object(service, 'authenticate_via_api', return_value={'user_id': 7}) as api, \
                patch.object(service, 'authenticate_via_database', return_value={'user_id': 8}) as database:
            self.assertEqual(service.authenticate('learner', 'password')['user_id'], 7)
            database.assert_not_called()
            api.side_effect = KnowledgeTreeAPIConnectionError('offline')
            self.assertEqual(service.authenticate('learner', 'password')['user_id'], 8)
            database.assert_called_once()
