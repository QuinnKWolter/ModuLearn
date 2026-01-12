"""
Tests for LTI Tool Consumer functionality.

Run with:
    python manage.py test lti
"""
import os
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from lti.models import LTILaunchCache, LTIOutcomeLog
from lti.services import (
    create_base_lti_body,
    create_lti_body,
    get_launch_url,
    sign_lti_request,
    build_um_url,
    parse_outcome_xml,
    create_outcome_response,
    validate_identifier,
    generate_source_id,
)
from lti.config import get_tool_config, is_tool_configured, list_configured_tools


class LTIServicesTestCase(TestCase):
    """Tests for LTI service layer functions."""
    
    def test_create_base_lti_body(self):
        """Test base LTI body creation contains required fields."""
        body = create_base_lti_body(
            source_id='user1_group1_activity1',
            usr='user1',
            grp='group1',
            sub='activity1',
            outcome_service_url='https://example.com/lti/outcome/'
        )
        
        # Check required LTI fields
        self.assertEqual(body['lti_message_type'], 'basic-lti-launch-request')
        self.assertEqual(body['lti_version'], 'LTI-1p0')
        self.assertEqual(body['user_id'], 'user1')
        self.assertEqual(body['roles'], 'Learner')
        self.assertEqual(body['lis_outcome_service_url'], 'https://example.com/lti/outcome/')
        self.assertEqual(body['lis_result_sourcedid'], 'user1_group1_activity1')
    
    def test_generate_source_id(self):
        """Test source_id generation is deterministic."""
        source_id = generate_source_id('user1', 'group1', 'activity1')
        self.assertEqual(source_id, 'user1_group1_activity1')
        
        # Same inputs should give same output
        source_id2 = generate_source_id('user1', 'group1', 'activity1')
        self.assertEqual(source_id, source_id2)
    
    def test_validate_identifier_valid(self):
        """Test identifier validation with valid inputs."""
        self.assertEqual(validate_identifier('user123', 'usr'), 'user123')
        self.assertEqual(validate_identifier('test-user_01', 'usr'), 'test-user_01')
        self.assertEqual(validate_identifier('user@example.com', 'usr'), 'user@example.com')
    
    def test_validate_identifier_invalid(self):
        """Test identifier validation rejects invalid inputs."""
        with self.assertRaises(ValueError):
            validate_identifier('', 'usr')  # Empty
        
        with self.assertRaises(ValueError):
            validate_identifier('user<script>', 'usr')  # Invalid chars
        
        with self.assertRaises(ValueError):
            validate_identifier('a' * 300, 'usr')  # Too long
    
    @patch.dict(os.environ, {'CODECHECK_KEY': 'test_key', 'CODECHECK_SECRET': 'test_secret', 'CODECHECK_LAUNCH': 'https://codecheck.io/lti'})
    def test_get_launch_url_default(self):
        """Test launch URL without modifier."""
        # Clear cached config
        from lti import config
        config.get_tool_configs.cache_clear() if hasattr(config.get_tool_configs, 'cache_clear') else None
        
        url = get_launch_url('codecheck', 'activity1')
        self.assertEqual(url, 'https://codecheck.io/lti')
    
    @patch.dict(os.environ, {'CTAT_KEY': 'test_key', 'CTAT_SECRET': 'test_secret', 'CTAT_LAUNCH': 'https://ctat.example.com'})
    def test_get_launch_url_with_modifier(self):
        """Test launch URL with URL modifier (CTAT)."""
        url = get_launch_url('ctat', 'problem1')
        self.assertEqual(url, 'https://ctat.example.com/mg_problem1')
    
    def test_sign_lti_request(self):
        """Test OAuth signing adds required OAuth params."""
        body = {'user_id': 'test', 'lti_message_type': 'basic-lti-launch-request'}
        
        signed = sign_lti_request(
            body=body,
            consumer_key='test_key',
            consumer_secret='test_secret',
            launch_url='https://example.com/lti'
        )
        
        # Check OAuth params are added
        self.assertIn('oauth_consumer_key', signed)
        self.assertIn('oauth_signature', signed)
        self.assertIn('oauth_timestamp', signed)
        self.assertIn('oauth_nonce', signed)
        self.assertEqual(signed['oauth_consumer_key'], 'test_key')
        self.assertEqual(signed['oauth_signature_method'], 'HMAC-SHA1')
    
    def test_parse_outcome_xml_valid(self):
        """Test parsing valid LTI outcome XML."""
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
        <imsx_POXEnvelopeRequest xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
          <imsx_POXBody>
            <replaceResultRequest>
              <resultRecord>
                <sourcedGUID>
                  <sourcedId>user1_group1_activity1</sourcedId>
                </sourcedGUID>
                <result>
                  <resultScore>
                    <textString>0.85</textString>
                  </resultScore>
                </result>
              </resultRecord>
            </replaceResultRequest>
          </imsx_POXBody>
        </imsx_POXEnvelopeRequest>'''
        
        source_id, score = parse_outcome_xml(xml)
        self.assertEqual(source_id, 'user1_group1_activity1')
        self.assertEqual(score, '0.85')
    
    def test_parse_outcome_xml_invalid(self):
        """Test parsing invalid XML raises ValueError."""
        with self.assertRaises(ValueError):
            parse_outcome_xml(b'not valid xml')
        
        # Missing sourcedId
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
        <imsx_POXEnvelopeRequest xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
          <imsx_POXBody/>
        </imsx_POXEnvelopeRequest>'''
        with self.assertRaises(ValueError):
            parse_outcome_xml(xml)
    
    def test_create_outcome_response_success(self):
        """Test creating success outcome response XML."""
        xml = create_outcome_response(True, 'Score recorded')
        self.assertIn('success', xml)
        self.assertIn('Score recorded', xml)
        self.assertIn('imsx_POXEnvelopeResponse', xml)
    
    def test_create_outcome_response_failure(self):
        """Test creating failure outcome response XML."""
        xml = create_outcome_response(False, 'Error occurred')
        self.assertIn('failure', xml)
        self.assertIn('Error occurred', xml)
    
    @patch.dict(os.environ, {'CODECHECK_KEY': 'k', 'CODECHECK_SECRET': 's', 'CODECHECK_LAUNCH': 'https://cc.io'})
    def test_build_um_url(self):
        """Test UM service URL building."""
        url = build_um_url(
            base_um_url='http://um.example.com/api',
            tool_name='codecheck',
            source_id='user1_group1_activity1',
            score='0.85',
            usr='user1',
            grp='group1',
            sub='activity1',
            sid='session1',
            svc='modulearn',
            cid='course1'
        )
        
        self.assertIn('um.example.com', url)
        self.assertIn('app=56', url)  # CodeCheck app_id
        self.assertIn('act=codecheck', url)
        self.assertIn('res=0.85', url)
        self.assertIn('usr=user1', url)


class LTILaunchCacheTestCase(TestCase):
    """Tests for LTI launch cache model."""
    
    def test_create_cache_entry(self):
        """Test creating a cache entry."""
        entry = LTILaunchCache.get_or_create_cache(
            source_id='test_user_test_group_test_activity',
            tool='codecheck',
            usr='test_user',
            grp='test_group',
            sub='test_activity',
            cid='course1',
            ttl_hours=24,
            module_id=123
        )
        
        self.assertIsNotNone(entry.id)
        self.assertEqual(entry.tool, 'codecheck')
        self.assertEqual(entry.usr, 'test_user')
        self.assertEqual(entry.module_id, 123)
        self.assertFalse(entry.is_expired())
    
    def test_cache_entry_parses_integer_ids(self):
        """Test that integer usr/grp are parsed into user_id/course_instance_id."""
        entry = LTILaunchCache.get_or_create_cache(
            source_id='10_5_activity',
            tool='codecheck',
            usr='10',  # Django user ID
            grp='5',   # CourseInstance ID
            sub='activity',
            module_id=42
        )
        
        self.assertEqual(entry.user_id, 10)
        self.assertEqual(entry.course_instance_id, 5)
        self.assertEqual(entry.module_id, 42)
    
    def test_cache_expiry(self):
        """Test cache entry expiry detection."""
        entry = LTILaunchCache.get_or_create_cache(
            source_id='expiry_test',
            tool='codecheck',
            usr='user',
            grp='group',
            sub='activity',
            ttl_hours=1
        )
        
        # Not expired initially
        self.assertFalse(entry.is_expired())
        
        # Manually set to past
        entry.expires_at = timezone.now() - timedelta(hours=1)
        entry.save()
        
        self.assertTrue(entry.is_expired())
    
    def test_get_valid_cache_returns_valid(self):
        """Test get_valid_cache returns non-expired entry."""
        LTILaunchCache.get_or_create_cache(
            source_id='valid_test',
            tool='codecheck',
            usr='user',
            grp='group',
            sub='activity',
            ttl_hours=24
        )
        
        entry = LTILaunchCache.get_valid_cache('valid_test')
        self.assertIsNotNone(entry)
        self.assertEqual(entry.source_id, 'valid_test')
    
    def test_get_valid_cache_returns_none_for_expired(self):
        """Test get_valid_cache returns None for expired entry."""
        entry = LTILaunchCache.get_or_create_cache(
            source_id='expired_test',
            tool='codecheck',
            usr='user',
            grp='group',
            sub='activity',
            ttl_hours=1
        )
        
        # Expire it
        entry.expires_at = timezone.now() - timedelta(hours=1)
        entry.save()
        
        result = LTILaunchCache.get_valid_cache('expired_test')
        self.assertIsNone(result)
    
    def test_cleanup_expired(self):
        """Test cleanup_expired removes only expired entries."""
        # Create valid entry
        LTILaunchCache.get_or_create_cache(
            source_id='valid',
            tool='codecheck',
            usr='user',
            grp='group',
            sub='activity',
            ttl_hours=24
        )
        
        # Create expired entry
        expired = LTILaunchCache.get_or_create_cache(
            source_id='expired',
            tool='codecheck',
            usr='user',
            grp='group',
            sub='activity2',
            ttl_hours=1
        )
        expired.expires_at = timezone.now() - timedelta(hours=1)
        expired.save()
        
        count = LTILaunchCache.cleanup_expired()
        self.assertEqual(count, 1)
        
        # Valid entry should still exist
        self.assertTrue(LTILaunchCache.objects.filter(source_id='valid').exists())
        self.assertFalse(LTILaunchCache.objects.filter(source_id='expired').exists())


class LTILaunchViewTestCase(TestCase):
    """Tests for LTI launch view."""
    
    def setUp(self):
        self.client = Client()
    
    def test_launch_missing_params(self):
        """Test launch returns 400 for missing params."""
        response = self.client.get(reverse('lti_launch'))
        self.assertEqual(response.status_code, 400)
        
        response = self.client.get(reverse('lti_launch'), {'tool': 'codecheck'})
        self.assertEqual(response.status_code, 400)
    
    @patch.dict(os.environ, {})
    def test_launch_unconfigured_tool(self):
        """Test launch returns 400 for unconfigured tool."""
        response = self.client.get(reverse('lti_launch'), {
            'tool': 'unknown_tool',
            'sub': 'activity1',
            'usr': 'user1',
            'grp': 'group1'
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'not configured', response.content)
    
    @patch.dict(os.environ, {
        'CODECHECK_KEY': 'test_key',
        'CODECHECK_SECRET': 'test_secret',
        'CODECHECK_LAUNCH': 'https://codecheck.io/lti'
    })
    def test_launch_success(self):
        """Test successful launch returns HTML form."""
        response = self.client.get(reverse('lti_launch'), {
            'tool': 'codecheck',
            'sub': 'activity1',
            'usr': 'user1',
            'grp': 'group1'
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'form', response.content)
        self.assertIn(b'codecheck.io', response.content)
        
        # Check cache entry was created
        self.assertTrue(LTILaunchCache.objects.filter(
            source_id='user1_group1_activity1'
        ).exists())


class LTIOutcomeViewTestCase(TestCase):
    """Tests for LTI outcome view."""
    
    def setUp(self):
        self.client = Client()
        
        # Create a cache entry for testing
        LTILaunchCache.get_or_create_cache(
            source_id='user1_group1_activity1',
            tool='codecheck',
            usr='user1',
            grp='group1',
            sub='activity1',
            cid='course1',
            ttl_hours=24
        )
    
    def test_outcome_non_post(self):
        """Test outcome rejects non-POST requests."""
        response = self.client.get(reverse('lti_outcome'))
        self.assertEqual(response.status_code, 405)
    
    def test_outcome_invalid_xml(self):
        """Test outcome returns failure for invalid XML."""
        response = self.client.post(
            reverse('lti_outcome'),
            data='not valid xml',
            content_type='application/xml'
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'failure', response.content)
    
    def test_outcome_missing_cache(self):
        """Test outcome returns failure when cache entry missing."""
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
        <imsx_POXEnvelopeRequest xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
          <imsx_POXBody>
            <replaceResultRequest>
              <resultRecord>
                <sourcedGUID>
                  <sourcedId>nonexistent_source_id</sourcedId>
                </sourcedGUID>
                <result>
                  <resultScore>
                    <textString>0.85</textString>
                  </resultScore>
                </result>
              </resultRecord>
            </replaceResultRequest>
          </imsx_POXBody>
        </imsx_POXEnvelopeRequest>'''
        
        response = self.client.post(
            reverse('lti_outcome'),
            data=xml,
            content_type='application/xml'
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'failure', response.content)
        self.assertIn(b'not found', response.content)
    
    @patch('modulearn.views_lti.requests.get')
    @patch.dict(os.environ, {
        'CODECHECK_KEY': 'k', 'CODECHECK_SECRET': 's', 'CODECHECK_LAUNCH': 'https://cc.io'
    })
    def test_outcome_success(self, mock_get):
        """Test successful outcome processing."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
        <imsx_POXEnvelopeRequest xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
          <imsx_POXBody>
            <replaceResultRequest>
              <resultRecord>
                <sourcedGUID>
                  <sourcedId>user1_group1_activity1</sourcedId>
                </sourcedGUID>
                <result>
                  <resultScore>
                    <textString>0.85</textString>
                  </resultScore>
                </result>
              </resultRecord>
            </replaceResultRequest>
          </imsx_POXBody>
        </imsx_POXEnvelopeRequest>'''
        
        response = self.client.post(
            reverse('lti_outcome'),
            data=xml,
            content_type='application/xml'
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'success', response.content)
        
        # Check UM service was called
        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        self.assertIn('usr=user1', call_url)
        self.assertIn('res=0.85', call_url)
        
        # Check outcome was logged
        log = LTIOutcomeLog.objects.filter(source_id='user1_group1_activity1').first()
        self.assertIsNotNone(log)
        self.assertTrue(log.success)


class LTIConfigTestCase(TestCase):
    """Tests for LTI configuration."""
    
    @patch.dict(os.environ, {
        'CODECHECK_KEY': '',
        'CODECHECK_SECRET': '',
        'CODECHECK_LAUNCH': ''
    }, clear=False)
    def test_tool_not_configured_without_env(self):
        """Test tool shows as not configured without env vars."""
        self.assertFalse(is_tool_configured('codecheck'))
    
    @patch.dict(os.environ, {
        'CODECHECK_KEY': 'key',
        'CODECHECK_SECRET': 'secret',
        'CODECHECK_LAUNCH': 'https://example.com'
    })
    def test_tool_configured_with_env(self):
        """Test tool shows as configured with env vars."""
        self.assertTrue(is_tool_configured('codecheck'))
    
    def test_get_tool_config_unknown(self):
        """Test get_tool_config returns None for unknown tool."""
        self.assertIsNone(get_tool_config('unknown_tool_xyz'))
    
    @patch.dict(os.environ, {
        'CODECHECK_KEY': 'key',
        'CODECHECK_SECRET': 'secret',
        'CODECHECK_LAUNCH': 'https://example.com'
    })
    def test_list_configured_tools(self):
        """Test list_configured_tools includes configured tools."""
        tools = list_configured_tools()
        self.assertIn('codecheck', tools)
