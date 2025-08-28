import os
import ssl
import sys
import logging
from pathlib import Path
from decouple import config
import os


# Debug environment loading
print(f"DEBUG value from env: {config('DEBUG', default='NOT_SET')}")
print(f"EMAIL_HOST from env: {config('EMAIL_HOST', default='NOT_SET')}")

# CORE DJANGO SETTINGS


# Build paths inside the project like this: BASE_DIR / 'subdir'
BASE_DIR = Path(__file__).resolve().parent.parent

# Use 'development', 'staging', or 'production'
ENVIRONMENT = 'production'
DEBUG = False

# Security settings
SECRET_KEY = config('SECRET_KEY')
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='*').split(',') if config('ALLOWED_HOSTS', default='*') != '*' else ['*']


# CSRF and CORS settings for trusted origins
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in config('CSRF_TRUSTED_ORIGINS', default='https://localhost,https://127.0.0.1').split(',') if origin.strip()]

# Security Headers - Applied only in production for maximum security
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_REDIRECT_EXEMPT = []
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    X_FRAME_OPTIONS = 'DENY'


# APPLICATION DEFINITION - Organized by category for maintainability


SECURE_SSL_REDIRECT = False
# Django Core Applications
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.sitemaps',
]

# Third Party Applications
THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework.authtoken',
    'django_extensions',
    'django_cleanup',
    'crispy_forms',
    'crispy_bootstrap4',
    'widget_tweaks',
    'tailwind',
    'theme',
]

# Development-only Applications (conditionally loaded)
DEVELOPMENT_APPS = [
    'debug_toolbar',
    'django_browser_reload',
] if DEBUG else []

# Project-specific Applications
PROJECT_APPS = [
    'accounts',
    'app',
    'enrollments',
    'cpd', 
    'affiliationcard',
]

# Combine all applications - Order matters for some apps
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + DEVELOPMENT_APPS + PROJECT_APPS


# MIDDLEWARE CONFIGURATION - Optimized order for performance and security


MIDDLEWARE = [
    # Security middleware (first for early security checks)
    'django.middleware.security.SecurityMiddleware',
    
    # Static files middleware (early for performance optimization)
    'whitenoise.middleware.WhiteNoiseMiddleware',
    
    # Session middleware (required for authentication)
    'django.contrib.sessions.middleware.SessionMiddleware',
    
    # Common middleware (handles redirects, ETags, etc.)
    'django.middleware.common.CommonMiddleware',
    
    # CSRF protection middleware
    'django.middleware.csrf.CsrfViewMiddleware',
    
    # Authentication middleware (after sessions and CSRF)
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    
    # Messages framework middleware
    'django.contrib.messages.middleware.MessageMiddleware',
    
    # Clickjacking protection middleware
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Add development middleware only in DEBUG mode
if DEBUG:
    MIDDLEWARE.extend([
        'debug_toolbar.middleware.DebugToolbarMiddleware',
        'django_browser_reload.middleware.BrowserReloadMiddleware',
    ])


# URL AND ROUTING CONFIGURATION

ROOT_URLCONF = 'acrp.urls'
WSGI_APPLICATION = 'acrp.wsgi.application'


# TEMPLATE CONFIGURATION - Optimized for performance


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
            ],
            # Use cached template loader in production for better performance
            'loaders': [
                ('django.template.loaders.cached.Loader', [
                    'django.template.loaders.filesystem.Loader',
                    'django.template.loaders.app_directories.Loader',
                ]),
            ] if not DEBUG else [
                'django.template.loaders.filesystem.Loader',
                'django.template.loaders.app_directories.Loader',
            ],
        },
    },
]



# DATABASE CONFIGURATION - Environment-based with PostgreSQL optimization


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASS'),
        'HOST': config('DB_HOST'), 
        'PORT': config('DB_PORT', cast=int),
        'OPTIONS': {
            # SSL mode for secure connections (required for production databases)
            'sslmode': config('DB_SSLMODE', default='require'),
            # Connection timeout to prevent hanging connections
            'connect_timeout': 10,
        },
        # Connection pooling for better performance
        'CONN_MAX_AGE': 600 if not DEBUG else 0,
        # Health checks to ensure connection validity
        'CONN_HEALTH_CHECKS': True,
    }
}



# CACHE CONFIGURATION - Environment-based caching strategy


if DEBUG:
    # Development: Local memory cache for quick testing
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'acrp-dev-cache',
            'TIMEOUT': 300,  # 5 minutes
            'OPTIONS': {
                'MAX_ENTRIES': 1000,
            }
        }
    }
else:
    
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
            'LOCATION': 'acrp_cache_table',
            'TIMEOUT': 300,  # 5 minutes
            'OPTIONS': {
                'MAX_ENTRIES': 5000,
                'CULL_FREQUENCY': 3,  # Remove 1/3 of entries when MAX_ENTRIES is reached
            }
        }
    }


# SESSION CONFIGURATION - Optimized for performance and security

SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access
SESSION_COOKIE_NAME = 'acrp_sessionid'
SESSION_SAVE_EVERY_REQUEST = False  # Save only when modified
SESSION_EXPIRE_AT_BROWSER_CLOSE = False


# AUTHENTICATION AND AUTHORIZATION


# Custom user model
AUTH_USER_MODEL = 'accounts.User'

# Authentication backends
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

# Password validation for security
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Login/Logout URL configuration
LOGIN_REDIRECT_URL = '/'
LOGIN_URL = '/auth/login/'
LOGOUT_REDIRECT_URL = '/'

# Password reset settings
PASSWORD_RESET_TIMEOUT = 86400  # 24 hours


# Static files configuration
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []

# Static files finders 
STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]

# Static files storage with compression for production
if DEBUG:
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
else:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# WhiteNoise configuration for static file serving
WHITENOISE_USE_FINDERS = DEBUG
WHITENOISE_AUTOREFRESH = DEBUG
WHITENOISE_MAX_AGE = 31536000  # 1 year cache for static files

# Media files configuration
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# File upload security settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
FILE_UPLOAD_PERMISSIONS = 0o644


# EMAIL CONFIGURATION - Environment-based email backend


if DEBUG:
    # Development: Console backend for testing
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = config('EMAIL_HOST')
    EMAIL_PORT = config('EMAIL_PORT', default=465, cast=int)
    EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
    EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
    EMAIL_HOST_USER = config('EMAIL_HOST_USER')
    EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
    
    # SSL context for certificate issues
    import ssl
    EMAIL_SSL_CONTEXT = ssl.create_default_context()
    EMAIL_SSL_CONTEXT.check_hostname = False
    EMAIL_SSL_CONTEXT.verify_mode = ssl.CERT_NONE

# Email settings (apply to both development and production)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='ams@acrp.org.za')
SERVER_EMAIL = config('SERVER_EMAIL', default=DEFAULT_FROM_EMAIL)
EMAIL_SUBJECT_PREFIX = '[ACRP] '
EMAIL_TIMEOUT = 30

# INTERNATIONALIZATION AND LOCALIZATION


LANGUAGE_CODE = 'en-us'
TIME_ZONE = config('TIME_ZONE', default='UTC')
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Date and time formats
DATETIME_FORMAT = 'Y-m-d H:i:s'
DATE_FORMAT = 'Y-m-d'
TIME_FORMAT = 'H:i:s'


# DJANGO REST FRAMEWORK CONFIGURATION

REST_FRAMEWORK = {
    # Authentication classes for API endpoints
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    # Default permissions for API security
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    # Response renderers (browsable API only in debug mode)
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ] + (['rest_framework.renderers.BrowsableAPIRenderer'] if DEBUG else []),
    # Pagination for large datasets
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    # Filtering and searching
    'DEFAULT_FILTER_BACKENDS': [
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    # Rate limiting for API protection
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour'
    },
    'EXCEPTION_HANDLER': 'rest_framework.views.exception_handler',
}


# THIRD-PARTY PACKAGE CONFIGURATION


# Crispy Forms for better form rendering
CRISPY_TEMPLATE_PACK = 'bootstrap4'
CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap4'

# Tailwind CSS configuration
TAILWIND_APP_NAME = 'theme'
NPM_BIN_PATH = config('NPM_BIN_PATH', default='npm')

# Django Extensions for development tools
GRAPH_MODELS = {
    'all_applications': True,
    'group_models': True,
}


# LOGGING CONFIGURATION - Comprehensive logging for debugging and monitoring


# Console debug logging flag
CONSOLE_LOG_DEBUG = config('CONSOLE_LOG_DEBUG', default=False, cast=bool)

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
        'json': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple' if DEBUG else 'json',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'acrp.log',
            'maxBytes': 15728640,  # 15MB
            'backupCount': 10,
            'formatter': 'verbose',
        } if not DEBUG else {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console'],
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'] if not DEBUG else ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'] if CONSOLE_LOG_DEBUG else [],
            'level': 'DEBUG' if CONSOLE_LOG_DEBUG else 'WARNING',
            'propagate': False,
        },
        'acrp': {
            'handlers': ['console', 'file', 'mail_admins'] if not DEBUG else ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'cpd_tracking': {
            'handlers': ['console', 'file'] if not DEBUG else ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}

# Ensure logs directory exists for file logging
if not DEBUG:
    (BASE_DIR / 'logs').mkdir(exist_ok=True)


# DEBUG TOOLBAR CONFIGURATION - Development only


if DEBUG:
    DEBUG_TOOLBAR_CONFIG = {
        'INTERCEPT_REDIRECTS': False,
        'SHOW_TOOLBAR_CALLBACK': lambda request: True,
        'HIDE_DJANGO_SQL': False,
        'SHOW_TEMPLATE_CONTEXT': True,
        'SQL_WARNING_THRESHOLD': 500,  # milliseconds
    }
    
    # Internal IPs for debug toolbar access
    INTERNAL_IPS = [
        '127.0.0.1',
        'localhost',
    ]


# CUSTOM APPLICATION SETTINGS - Business logic configuration


# CPD (Continuing Professional Development) Tracking Settings
CPD_SETTINGS = {
    'DEFAULT_POINTS_PER_HOUR': 1.0,
    'MAX_FILE_UPLOAD_SIZE': 10 * 1024 * 1024,  # 10MB
    'EVIDENCE_ALLOWED_EXTENSIONS': ['.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png'],
    'AUTO_APPROVAL_THRESHOLD': 5.0,  # Hours
    'COMPLIANCE_CALCULATION_CACHE_TIMEOUT': 3600,  # 1 hour
    'NOTIFICATION_REMINDER_DAYS': [30, 14, 7, 1],  # Days before deadline
}

# Enrollment System Settings
ENROLLMENT_SETTINGS = {
    'APPLICATION_TIMEOUT_DAYS': 90,
    'MAX_APPLICATIONS_PER_USER': 5,
    'REQUIRE_EVIDENCE_UPLOADS': True,
    'AUTO_GENERATE_CERTIFICATES': True,
}

# General Application Settings
APP_SETTINGS = {
    'SITE_NAME': 'ACRP Africa',
    'SITE_DESCRIPTION': 'Association of Christian Religious Practitioners',
    'CONTACT_EMAIL': config('CONTACT_EMAIL', default='ams@acrp.org.za'),
    'SUPPORT_EMAIL': config('SUPPORT_EMAIL', default='ams@acrpafrica.co.za'),
    'MAX_LOGIN_ATTEMPTS': 10,
    'LOGIN_LOCKOUT_DURATION': 300,  # 5 minutes
}
ADMINS = [
    ('admin', 'ams@acrp.org.za'), 
]
MANAGERS = ADMINS



# MONITORING AND ANALYTICS - Optional production monitoring


# Application monitoring with Sentry (optional)
MONITORING_ENABLED = config('MONITORING_ENABLED', default=False, cast=bool)

if MONITORING_ENABLED and config('SENTRY_DSN', default=None):
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        
        sentry_logging = LoggingIntegration(
            level=logging.INFO,
            event_level=logging.ERROR
        )
        
        sentry_sdk.init(
            dsn=config('SENTRY_DSN'),
            integrations=[DjangoIntegration(), sentry_logging],
            traces_sample_rate=0.1,
            send_default_pii=True,
            environment=ENVIRONMENT,
        )
    except ImportError:
        # Sentry not installed, skip monitoring
        pass

# Performance monitoring thresholds
PERFORMANCE_MONITORING = {
    'SLOW_QUERY_THRESHOLD': 1000,  # milliseconds
    'MEMORY_USAGE_THRESHOLD': 500,  # MB
    'ENABLE_PROFILING': DEBUG,
}


# BACKGROUND TASKS CONFIGURATION - Simple deployment approach


# Using Django management commands with cron jobs instead of Celery
BACKGROUND_TASKS = {
    'EMAIL_BATCH_SIZE': 10,
    'NOTIFICATION_BATCH_SIZE': 100,
    'CLEANUP_OLDER_THAN_DAYS': 90,
    'MAINTENANCE_WINDOW_HOUR': 2,  # 2 AM
}


# ENVIRONMENT-SPECIFIC OVERRIDES


# Development environment overrides
if DEBUG:
    # Allow all hosts in development
    ALLOWED_HOSTS = ['*']

# Production environment overrides
if ENVIRONMENT == 'production':
    
    # Set proper allowed hosts (should be configured in environment)
    assert ALLOWED_HOSTS != ['*'], "ALLOWED_HOSTS must be properly configured for production"

# Testing environment overrides
if 'test' in sys.argv or 'pytest' in sys.modules:
    # Use SQLite in-memory database for faster tests
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
    
    # Disable migrations during testing for speed
    class DisableMigrations:
        def __contains__(self, item):
            return True
        def __getitem__(self, item):
            return None
    
    MIGRATION_MODULES = DisableMigrations()
    
    # Use dummy cache for tests
    CACHES['default']['BACKEND'] = 'django.core.cache.backends.dummy.DummyCache'
    
    # Disable logging during tests to reduce noise
    LOGGING['root']['level'] = 'CRITICAL'


# SETTINGS VALIDATION - Ensure critical settings are properly configured


# Validate essential environment variables
assert SECRET_KEY, "SECRET_KEY must be set in environment variables"
assert ALLOWED_HOSTS, "ALLOWED_HOSTS must be configured"

# Production-specific validations
if not DEBUG:
    assert config('EMAIL_HOST', default=None), "EMAIL_HOST must be set in production"
    #assert 'postgresql' in DATABASES['default']['ENGINE'], \
     #      "Production should use PostgreSQL for better performance and features"

# Set default primary key field type for Django 3.2+
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# FINAL SETUP AND LOGGING


# Log startup information
logger = logging.getLogger(__name__)
logger.info(f"ACRP Platform starting in {ENVIRONMENT} mode (DEBUG={DEBUG})")

# Reminder for cache table creation in production
if not DEBUG and 'migrate' not in sys.argv and 'runserver' not in sys.argv:
    logger.info("Remember to create cache table: python manage.py createcachetable acrp_cache_table")