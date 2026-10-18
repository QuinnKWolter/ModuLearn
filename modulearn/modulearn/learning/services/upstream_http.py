"""Verified HTTPS for Pitt servers that omit their intermediate certificate."""
import requests
from requests.adapters import HTTPAdapter
from .slc_catalog import _tls_context


class PittTLSAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_context'] = _tls_context('https://adapt2.sis.pitt.edu/')
        return super().init_poolmanager(*args, **kwargs)


def pitt_session():
    session = requests.Session()
    session.mount('https://adapt2.sis.pitt.edu/', PittTLSAdapter())
    session.mount('https://pawscomp2.sis.pitt.edu/', PittTLSAdapter())
    return session
