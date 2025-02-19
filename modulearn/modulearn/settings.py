"""
Django settings for modulearn project.

Generated by 'django-admin startproject' using Django 5.1.
"""

import os
from pathlib import Path
from datetime import timedelta

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-k7s0j45f+h4q_a%8llu@en)@mnbq&e535btz)ce@%6no0uw&i%'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# Helper function to handle ngrok URLs in development
def get_ngrok_urls():
    if DEBUG:  # Only allow ngrok in development
        from urllib.request import urlopen
        try:
            # Get ngrok tunnels info
            ngrok_tunnels = urlopen('http://127.0.0.1:4040/api/tunnels').read()
            import json
            tunnels = json.loads(ngrok_tunnels)['tunnels']
            return [tunnel['public_url'].replace('https://', '').replace('http://', '') 
                   for tunnel in tunnels]
        except:
            return []
    return []

ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    'saltire.lti.app',
    *get_ngrok_urls()  # Dynamically add ngrok URLs
]

# Application definition
INSTALLED_APPS = [
    # Default Django apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party apps
    # 'lti_tool',
    'crispy_forms',
    'crispy_bootstrap5',
    # Your apps
    'modulearn',
    'accounts',
    'courses',
    'dashboard',
    'main',
    'lti'
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
            ],
        },
    },
]

WSGI_APPLICATION = 'modulearn.wsgi.application'

# store db outside of the project
os.makedirs(BASE_DIR / '../modulearn-storage/db', exist_ok=True)

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / '../modulearn-storage/db/db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'accounts.User'
LOGIN_URL = 'accounts:login'

# Django REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'oauth2_provider.contrib.rest_framework.OAuth2Authentication',  # OAuth2 authentication
        'rest_framework.authentication.SessionAuthentication',          # Session authentication
        # Add other authentication classes if needed
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',  # Require authentication by default
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',       # Render responses in JSON
        'rest_framework.renderers.BrowsableAPIRenderer',
    ),
}

# OAuth2 Provider Settings (using django-oauth-toolkit)
OAUTH2_PROVIDER = {
    'ACCESS_TOKEN_EXPIRE_SECONDS': 3600,  # Access token lifespan
    'AUTHORIZATION_CODE_EXPIRE_SECONDS': 600,
    'ROTATE_REFRESH_TOKEN': True,
    'SCOPES': {
        'read': 'Read scope',
        'write': 'Write scope',
        'lti': 'LTI scope',
    },
}

# CORS Headers Configuration
CORS_ALLOWED_ORIGINS = [
    'https://canvas.instructure.com',
    'https://saltire.lti.app',
    *[f'https://{host}' for host in get_ngrok_urls()]  # Add ngrok URLs with https://
]

# Security Settings
SECURE_SSL_REDIRECT = not DEBUG          # Redirect HTTP to HTTPS in production
SESSION_COOKIE_SECURE = not DEBUG        # Secure cookies in production
CSRF_COOKIE_SECURE = not DEBUG           # Secure CSRF cookies in production
X_FRAME_OPTIONS = ''

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,  # Set to False to prevent duplicate logging
        },
        'courses': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,  # Set to False to prevent duplicate logging
        },
    },
}

# Email Configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'       # Replace with your email host
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@example.com'     # Replace with your email
EMAIL_HOST_PASSWORD = 'your-email-password'    # Replace with your email password

LOGIN_URL = 'accounts:login'

# LTI 1.3 Configuration
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

# Cache Configuration
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'django_cache_table',
    }
}

SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# Allow session cookies to be sent in cross-site requests
SESSION_COOKIE_SAMESITE = 'None'  # Required for iframe embedding
SESSION_COOKIE_SECURE = True      # Required when SameSite is None
CSRF_COOKIE_SAMESITE = 'None'    # Required for iframe embedding
CSRF_COOKIE_SECURE = True        # Required when SameSite is None

# Allow CSRF cookies in cross-site requests (if needed)
CSRF_COOKIE_SAMESITE = None
CSRF_COOKIE_SECURE = True

# Crispy Forms Configuration
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# Configuration for acting as an LTI tool consumer
LTI_CONSUMER_CONFIG = {
    'client_id': 'external-tool-client-id',
    'public_key_file': './modulearn/public.key',
    'private_key_file': './modulearn/private.key',
    # Add any other necessary configuration specific to the external tool
}

def get_primary_domain():
    """Returns the primary domain to use for the application"""
    if DEBUG:
        # Try to get ngrok URL first
        ngrok_urls = get_ngrok_urls()
        if ngrok_urls:
            domain = f"https://{ngrok_urls[0]}"
            print(f"Using ngrok domain: {domain}")  # Debug print
            return domain
        print("No ngrok URLs found, using localhost")  # Debug print
        return "http://localhost:8000"  # Fallback to localhost
    return "https://modulearn.com"  # Production domain PLACEHOLDER TODO

LTI_TOOL_CONFIG = {
    'title': 'ModuLearn',
    'description': 'A multi-protocol eLearning module bundling and delivery platform',
    'launch_url': f'{get_primary_domain()}/lti/launch/',
    'custom_fields': {
        'canvas_course_id': '$Canvas.course.id',
        'canvas_user_id': '$Canvas.user.id'
    },
    'extensions': [
        {
            'platform': 'canvas.instructure.com',
            'settings': {
                'text': 'ModuLearn',
                'icon_url': f'{get_primary_domain()}/static/img/logo_128.png',
                'selection_height': 800,
                'selection_width': 1200,
                'privacy_level': 'public'
            }
        }
    ]
}

# Add CSRF trusted origins for your ngrok domain
CSRF_TRUSTED_ORIGINS = [
    'https://*.ngrok-free.app',
]

# LTI 1.1 Configuration
LTI_11_CONSUMER_KEY = 'modulearn_key'
LTI_11_CONSUMER_SECRET = 'modulearn_secret'