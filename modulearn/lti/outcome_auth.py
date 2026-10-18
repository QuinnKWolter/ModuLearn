"""Authenticate LTI 1.1 outcome signatures and bind them to the XML body."""
import base64
import hashlib
import hmac
from django.core.cache import cache
from oauthlib.oauth1 import RequestValidator, SignatureOnlyEndpoint


class OutcomeValidator(RequestValidator):
    enforce_ssl = False  # Django may sit behind a TLS-terminating reverse proxy.
    client_key_length = (1, 512)
    nonce_length = (1, 512)
    allowed_signature_methods = ['HMAC-SHA1']
    dummy_client = 'invalid-lti-client'

    def __init__(self, key, secret):
        self.key, self.secret = key, secret

    def validate_client_key(self, client_key, request):
        return hmac.compare_digest(client_key, self.key)

    def get_client_secret(self, client_key, request):
        return self.secret if client_key == self.key else 'invalid-lti-secret'

    def validate_timestamp_and_nonce(self, client_key, timestamp, nonce, request, **kwargs):
        # oauthlib checks timestamp freshness. Consume the nonce only after
        # signature and body verification, so invalid requests cannot reserve it.
        return True


def authenticate_outcome(request, config):
    """Return (valid, duplicate); identical signed retries are acknowledged once."""
    key, secret = config.get('consumer_key', ''), config.get('consumer_secret', '')
    if not key or not secret:
        return False, False
    endpoint = SignatureOnlyEndpoint(OutcomeValidator(key, secret))
    try:
        valid, signed = endpoint.validate_request(request.build_absolute_uri(), http_method='POST',
            headers={'Authorization': request.META.get('HTTP_AUTHORIZATION', ''), 'Content-Type': 'application/xml'})
    except (ValueError, TypeError):
        return False, False
    expected = base64.b64encode(hashlib.sha1(request.body).digest()).decode('ascii')
    supplied = dict(signed.params).get('oauth_body_hash', '') if signed else ''
    if not valid or not isinstance(supplied, str) or not hmac.compare_digest(supplied, expected):
        return False, False
    identity = hashlib.sha256(f'{key}:{signed.timestamp}:{signed.nonce}'.encode()).hexdigest()
    nonce_key = 'lti-outcome-nonce:' + identity
    fingerprint = hashlib.sha256(request.body).hexdigest()
    previous = cache.get(nonce_key)
    if previous is None:
        request._verified_lti_nonce = (nonce_key, fingerprint)
        return True, False
    return hmac.compare_digest(previous, fingerprint), True


def remember_outcome(request):
    identity = getattr(request, '_verified_lti_nonce', None)
    if identity:
        cache.set(identity[0], identity[1], 660)
