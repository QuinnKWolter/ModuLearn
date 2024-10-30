from pylti1p3.contrib.django import DjangoCacheDataStorage
from django.core.cache import cache

class CacheDataStorage(DjangoCacheDataStorage):  # Use DjangoCacheDataStorage as the base
    def get_nonce(self, nonce):
        return cache.get(f'nonce_{nonce}')

    def save_nonce(self, nonce, expires_in):
        cache.set(f'nonce_{nonce}', True, timeout=expires_in)

    def get_state(self, state):
        return cache.get(f'state_{state}')

    def save_state(self, state, state_data):
        cache.set(f'state_{state}', state_data, timeout=3600)
