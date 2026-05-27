import os
import sys
import warnings
from importlib.util import find_spec
from pathlib import Path
from dotenv import load_dotenv

try:
    from cryptography.utils import CryptographyDeprecationWarning
except Exception:  # pragma: no cover
    CryptographyDeprecationWarning = None

# Suppress deprecation warnings from third-party libraries
warnings.filterwarnings('ignore', category=UserWarning, module='pkg_resources')
warnings.filterwarnings('ignore', category=DeprecationWarning, module='paramiko')
warnings.filterwarnings('ignore', category=DeprecationWarning, module='cryptography')
if CryptographyDeprecationWarning is not None:
    warnings.filterwarnings('ignore', category=CryptographyDeprecationWarning)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from project root .env (one level above BASE_DIR)
env_path = BASE_DIR.parent / '.env'
env_loaded = load_dotenv(dotenv_path=env_path)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-k7s0j45f+h4q_a%8llu@en)@mnbq&e535btz)ce@%6no0uw&i%'

def parse_boolish(value):
    """Parse common boolean environment values; ignore unrelated strings."""
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in ('true', '1', 'yes', 'on'):
        return True
    if normalized in ('false', '0', 'no', 'off'):
        return False
    return None

# Clean, robust environment selection
DEBUG = parse_boolish(os.getenv('DEBUG', 'False'))
if os.getenv('DJANGO_PRODUCTION') and parse_boolish(os.getenv('DJANGO_PRODUCTION')):
    DEBUG = False

IS_PRODUCTION = not DEBUG

import logging
logger = logging.getLogger(__name__)

if env_loaded:
    logger.info(f"Loaded .env file from: {env_path}")
else:
    logger.warning(f".env file not found at: {env_path} - using system environment defaults")

ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    'proxy.personalized-learning.org',
]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'modulearn',
    'accounts',
    'courses',
    'dashboard',
    'main',
    'lti',
    'recruitment',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'lti.middleware.LTIAuthMiddleware',
]

ROOT_URLCONF = 'modulearn.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'modulearn.core.context_processors.app_shell',
            ],
        },
    },
]

WSGI_APPLICATION = 'modulearn.wsgi.application'

# Ensure database directory storage exists cleanly
os.makedirs(BASE_DIR / '../modulearn-storage/db', exist_ok=True)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / '../modulearn-storage/db/db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# =============================================================================
# STATIC & MEDIA ASSET MANAGEMENT
# =============================================================================
FORCE_SCRIPT_NAME = os.getenv('DJANGO_FORCE_SCRIPT_NAME', None)

STATIC_URL = os.getenv('STATIC_URL', '/modulearn-static/' if IS_PRODUCTION else '/static/')
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Pure Django engine—completely sequential, zero background threads
if DEBUG:
    STATICFILES_BACKEND = 'django.contrib.staticfiles.storage.StaticFilesStorage'
else:
    STATICFILES_BACKEND = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': STATICFILES_BACKEND,
    },
}

MEDIA_ROOT = BASE_DIR / 'media'
serve_media_env = parse_boolish(os.getenv('SERVE_MEDIA_FILES'))
SERVE_MEDIA_FILES = serve_media_env if serve_media_env is not None else DEBUG

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.User'
LOGIN_URL = 'accounts:login'

AUTHENTICATION_BACKENDS = [
    'accounts.backends.KnowledgeTreeBackend',
    'django.contrib.auth.backends.ModelBackend',
]

KNOWLEDGETREE = {
    'AUTH_ENABLED': os.getenv('KT_AUTH_ENABLED', 'True').lower() == 'true',
    'AUTH_METHOD': os.getenv('KT_AUTH_METHOD', 'api'),
    'AUTH_FALLBACK': os.getenv('KT_AUTH_FALLBACK', 'True').lower() == 'true',
    'API_URL': os.getenv('KT_API_URL', 'http://adapt2.sis.pitt.edu'),
    'API_TIMEOUT': int(os.getenv('KT_API_TIMEOUT', '10')),
    'SECURITY_CHECK_PATH': os.getenv('KT_SECURITY_CHECK_PATH', '/kt/content/j_security_check'),
}

PAWS_DATABASE = {
    'HOST': os.getenv('PAWS_DB_HOST', '127.0.0.1'),
    'PORT': int(os.getenv('PAWS_DB_PORT', '3306')),
    'USER': os.getenv('PAWS_DB_USER', ''),
    'PASSWORD': os.getenv('PAWS_DB_PASSWORD', ''),
    'KNOWLEDGETREE_SCHEMA': os.getenv('PAWS_DB_KT_SCHEMA', 'portal_test2'),
    'AGGREGATE_SCHEMA': os.getenv('PAWS_DB_AGGREGATE_SCHEMA', 'aggregate'),
    'SSH_HOST': os.getenv('PAWS_DB_SSH_HOST', ''),
    'SSH_PORT': int(os.getenv('PAWS_DB_SSH_PORT', '22')),
    'SSH_USER': os.getenv('PAWS_DB_SSH_USER', ''),
    'SSH_PASSWORD': os.getenv('PAWS_DB_SSH_PASSWORD', ''),
    'SSH_KEY_PATH': os.getenv('PAWS_DB_SSH_KEY_PATH', ''),
    'USE_SSH': os.getenv('PAWS_DB_USE_SSH', 'False').lower() == 'true',
}

if not PAWS_DATABASE['USE_SSH'] and PAWS_DATABASE.get('SSH_HOST') and PAWS_DATABASE.get('SSH_USER'):
    logger.warning(f"SSH credentials provided but PAWS_DB_USE_SSH is False.")

if KNOWLEDGETREE['AUTH_METHOD'] in ('database', 'both'):
    KNOWLEDGETREE['DATABASE'] = PAWS_DATABASE

AGGREGATE = {
    'DATABASE': PAWS_DATABASE,
}

try:
    db_config = PAWS_DATABASE
    logger.info(f"PAWS Database Config registered for host: {db_config['HOST']}")
except Exception:
    pass

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'oauth2_provider.contrib.rest_framework.OAuth2Authentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ),
}

OAUTH2_PROVIDER = {
    'ACCESS_TOKEN_EXPIRE_SECONDS': 3600,
    'AUTHORIZATION_CODE_EXPIRE_SECONDS': 600,
    'ROTATE_REFRESH_TOKEN': True,
    'SCOPES': {
        'read': 'Read scope',
        'write': 'Write scope',
        'lti': 'LTI scope',
    },
}

CORS_ALLOWED_ORIGINS = [
    'https://canvas.instructure.com',
    'https://saltire.lti.app',
]

X_FRAME_OPTIONS = 'SAMEORIGIN'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}', 'style': '{'},
        'simple': {'format': '{levelname} {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'},
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'courses': {'handlers': ['console'], 'level': 'DEBUG', 'propagate': False},
        'dashboard': {'handlers': ['console'], 'level': 'DEBUG', 'propagate': False},
        'lti': {'handlers': ['console'], 'level': 'DEBUG', 'propagate': False},
    },
}

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@example.com'
EMAIL_HOST_PASSWORD = 'your-email-password'

LTI_CONFIG = {
    'https://saltire.lti.app/platform': {
        'client_id': 'saltire.lti.app',
        'auth_login_url': 'https://saltire.lti.app/platform/auth',
        'auth_token_url': 'https://saltire.lti.app/platform/token/3b4f2aae79ac1d451a4911ac3bc00145',
        'key_set_url': 'https://saltire.lti.app/platform/jwks/3b4f2aae79ac1d451a4911ac3bc00145',
        'auth_audience': 'https://saltire.lti.app/platform',
        'deployment_ids': ['6eb84c059ff928e88f0b734420330efa09905105'],
        'public_key_file': './modulearn/public.key',
        'private_key_file': './modulearn/private.key',
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'django_cache_table',
    }
}

SESSION_ENGINE = 'django.contrib.sessions.backends.db'

DEV_HTTPS = os.getenv('MODULEARN_DEV_HTTPS', '').lower() in ('1', 'true', 'yes', 'on')
if DEBUG and not DEV_HTTPS:
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SAMESITE = 'Lax'
    CSRF_COOKIE_SECURE = False
else:
    SESSION_COOKIE_SAMESITE = 'None'
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SAMESITE = 'None'
    CSRF_COOKIE_SECURE = True

LTI_CONSUMER_CONFIG = {
    'client_id': 'external-tool-client-id',
    'public_key_file': './modulearn/public.key',
    'private_key_file': './modulearn/private.key',
}

def get_primary_domain():
    return os.getenv('PRIMARY_DOMAIN', 'http://localhost:8000' if DEBUG else 'https://proxy.personalized-learning.org').rstrip('/')

LTI_TOOL_CONFIG = {
    'title': 'ModuLearn',
    'description': 'A multi-protocol eLearning module bundling and delivery platform',
    'launch_url': f'{get_primary_domain()}{FORCE_SCRIPT_NAME or ""}/lti/launch/',
    'custom_fields': {
        'canvas_course_id': '$Canvas.course.id',
        'canvas_user_id': '$Canvas.user.id'
    },
    'extensions': [
        {
            'platform': 'canvas.instructure.com',
            'settings': {
                'text': 'ModuLearn',
                'icon_url': f'{get_primary_domain()}{STATIC_URL}img/logo_128.png',
                'selection_height': 800,
                'selection_width': 1200,
                'privacy_level': 'public'
            }
        }
    ]
}

CSRF_TRUSTED_ORIGINS = ['https://proxy.personalized-learning.org']
LTI_11_CONSUMER_KEY = 'modulearn_key'
LTI_11_CONSUMER_SECRET = 'modulearn_secret'
USE_X_FORWARDED_HOST = True

UM_SERVICE_URL = os.getenv('UM_SERVICE_URL', 'http://adapt2.sis.pitt.edu/aggregate2/UserActivity')
LTI_CACHE_TTL_HOURS = int(os.getenv('LTI_CACHE_TTL_HOURS', '24'))

# Backward compatibility fallbacks
LTI_TOOL_ENVS = {
    "codecheck": ("CODECHECK_KEY", "CODECHECK_SECRET", "CODECHECK_LAUNCH"),
    "codelab": ("CODELAB_KEY", "CODELAB_SECRET", "CODELAB_LAUNCH"),
    "codeocean": ("CODEOCEAN_KEY", "CODEOCEAN_SECRET", "CODEOCEAN_LAUNCH"),
    "codeworkout": ("CODEWORKOUT_KEY", "CODEWORKOUT_SECRET", "CODEWORKOUT_LAUNCH"),
    "ctat": ("CTAT_KEY", "CTAT_SECRET", "CTAT_LAUNCH"),
    "dbqa": ("DBQA_KEY", "DBQA_SECRET", "DBQA_LAUNCH"),
    "opendsa_problems": ("OPENDSA_PROBLEMS_KEY", "OPENDSA_PROBLEMS_SECRET", "OPENDSA_PROBLEMS_LAUNCH"),
    "opendsa_slideshows": ("OPENDSA_SLIDESHOWS_KEY", "OPENDSA_SLIDESHOWS_SECRET", "OPENDSA_SLIDESHOWS_LAUNCH"),
}

def LTI_URL_BUILDER(tool: str, base: str, sub: str) -> str:
    if tool == "ctat":
        return f"{base.rstrip('/')}/mg_{sub}"
    if tool in ("opendsa_problems", "opendsa_slideshows"):
        return f"{base}?custom_ex_settings=%7B%7D&custom_ex_short_name={sub}"
    return base

PROXY_ALLOWED_HOSTS = {
    "columbus.exp.sis.pitt.edu",
    "pawscomp2.sis.pitt.edu",
    "adapt2.sis.pitt.edu",
    "localhost",
    "127.0.0.1",
}
PROXY_MAX_BYTES = 5 * 1024 * 1024
PROXY_CORS_ORIGIN = 'https://proxy.personalized-learning.org'

# =============================================================================
# PRODUCTION PROXY ROUTING CORRECTION
# =============================================================================
if IS_PRODUCTION:
    class FixProxySlashes:
        def __init__(self, get_response):
            self.get_response = get_response
        def __call__(self, request):
            if request.path_info.startswith('//'):
                request.path_info = '/' + request.path_info.lstrip('/')
            return self.get_response(request)
            
    MIDDLEWARE.insert(0, 'modulearn.settings.FixProxySlashes')