from pylti1p3.contrib.django import DjangoCacheDataStorage
from django.core.cache import cache

class CacheDataStorage(DjangoCacheDataStorage):
    def get_nonce(self, nonce):
        print(f"Getting nonce from cache: nonce_{nonce}")
        return cache.get(f'nonce_{nonce}')

    def save_nonce(self, nonce, expires_in):
        cache.set(f'nonce_{nonce}', True, timeout=expires_in)
        print(f"Nonce saved in cache: nonce_{nonce}")

    def delete_nonce(self, nonce):  # Deleting nonce after use
        cache.delete(f'nonce_{nonce}')

    def get_state(self, state):
        return cache.get(f'state_{state}')

    def save_state(self, state, state_data):
        cache.set(f'state_{state}', state_data, timeout=3600)

    def delete_state(self, state):  # Deleting state after use
        cache.delete(f'state_{state}')
