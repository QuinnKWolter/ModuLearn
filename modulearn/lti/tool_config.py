from pylti1p3.tool_config import ToolConfAbstract

class DjangoToolConf(ToolConfAbstract):
    def __init__(self, config):
        super().__init__()
        self._config = config

    def find_registration(self, iss, client_id=None):
        # Access registration data by issuer URL
        issuer_config = self._config.get(iss)
        if issuer_config and (client_id is None or client_id == issuer_config['client_id']):
            return {
                'issuer': iss,
                'client_id': issuer_config['client_id'],
                'auth_login_url': issuer_config['auth_login_url'],
                'auth_token_url': issuer_config['auth_token_url'],
                'auth_audience': issuer_config['auth_audience'],
                'key_set_url': issuer_config['key_set_url'],
                'key_set': None,
                'private_key_file': issuer_config['private_key_file'],
                'public_key_file': issuer_config['public_key_file'],
                'deployment_ids': issuer_config['deployment_ids'],
            }
        return None