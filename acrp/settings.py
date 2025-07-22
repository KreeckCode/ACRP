
import os
import sys
import logging
from pathlib import Path
from decouple import config, Csv
import dj_database_url

# ============================================================================
# CORE SETTINGS - Foundation configuration
# ============================================================================

# Build paths inside the project like this: BASE_DIR / 'subdir'
BASE_DIR = Path(__file__).resolve().parent.parent

# Environment detection
ENVIRONMENT = config('ENVIRONMENT', default='development')
DEBUG = config('DEBUG', default=True, cast=bool)

# Security
SECRET_KEY = config('SECRET_KEY')
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

# CSRF and CORS settings
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS', 
    default='https://kreeck.com,https://www.kreeck.com',
    cast=Csv()
)

# Security Headers (Production)
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_REDIRECT_EXEMPT = []
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
    SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = 'DENY'

# ============================================================================
# APPLICATION DEFINITION - Organized by category
# ============================================================================

# Django Core Apps
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

# Third Party Apps
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

# Development Apps (only in debug mode)
DEVELOPMENT_APPS = [
    'debug_toolbar',
    'django_browser_reload',
] if DEBUG else []

# Project Apps
PROJECT_APPS = [
    'accounts',
    'app',
    'enrollments',
    'cpd', 
    'affiliationcard',
]

# Combine all apps
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + DEVELOPMENT_APPS + PROJECT_APPS

# ============================================================================
# MIDDLEWARE CONFIGURATION - Optimized order for performance
# ============================================================================

MIDDLEWARE = [
    # Security middleware (first)
    'django.middleware.security.SecurityMiddleware',
    
    # Static files (early for performance)
    'whitenoise.middleware.WhiteNoiseMiddleware',
    
    # Session and cache
    'django.contrib.sessions.middleware.SessionMiddleware',
    
    # Common middleware
    'django.middleware.common.CommonMiddleware',
    
    # CSRF protection
    'django.middleware.csrf.CsrfViewMiddleware',
    
    # Authentication
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    
    # Messages
    'django.contrib.messages.middleware.MessageMiddleware',
    
    # Clickjacking protection
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
    # Development middleware (only in debug)
] + (['debug_toolbar.middleware.DebugToolbarMiddleware'] if DEBUG else []) + [
    'django_browser_reload.middleware.BrowserReloadMiddleware',
] if DEBUG else []

# ============================================================================
# URL AND ROUTING CONFIGURATION
# ============================================================================

ROOT_URLCONF = 'acrp.urls'
WSGI_APPLICATION = 'acrp.wsgi.application'

# ============================================================================
# TEMPLATE CONFIGURATION - Optimized for performance
# ============================================================================

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
            # Template caching for production
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

# ============================================================================
# DATABASE CONFIGURATION - Environment-based with optimization
# ============================================================================

# Default database configuration
DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME'),
            'USER': config('DB_USER'),
            'PASSWORD': config('DB_PASS'),
            'HOST': config('DB_HOST'), 
            'PORT': config('DB_PORT'),  
        }
    }

# Database optimization settings
DATABASE_OPTIONS = {
    'postgresql': {
        'OPTIONS': {
            'sslmode': config('DB_SSLMODE', default='prefer'),
            'connect_timeout': 10,
            'options': '-c default_transaction_isolation=read_committed'
        },
        'CONN_MAX_AGE': 600,
        'CONN_HEALTH_CHECKS': True,
        'ATOMIC_REQUESTS': True,  # Wrap each request in a transaction
    },
    'mysql': {
        'OPTIONS': {
            'charset': 'utf8mb4',
            'use_unicode': True,
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        'CONN_MAX_AGE': 600,
        'CONN_HEALTH_CHECKS': True,
        'ATOMIC_REQUESTS': True,
    }
}

# Apply database-specific optimizations
db_engine = DATABASES['default']['ENGINE']
if 'postgresql' in db_engine and not DEBUG:
    DATABASES['default'].update(DATABASE_OPTIONS['postgresql'])
elif 'mysql' in db_engine and not DEBUG:
    DATABASES['default'].update(DATABASE_OPTIONS['mysql'])

# ============================================================================
# CACHE CONFIGURATION - Simple deployment without Redis
# ============================================================================

if DEBUG:
    # Development: Local memory cache
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'acrp-cache',
            'TIMEOUT': 300,
            'OPTIONS': {
                'MAX_ENTRIES': 1000,
            }
        }
    }
else:
    # Production: Database cache (simple deployment)
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
            'LOCATION': 'acrp_cache_table',
            'TIMEOUT': 300,
            'OPTIONS': {
                'MAX_ENTRIES': 5000,
                'CULL_FREQUENCY': 3,
            }
        }
    }

# Session configuration for performance (database-backed)
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_NAME = 'acrp_sessionid'
SESSION_SAVE_EVERY_REQUEST = False
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# ============================================================================
# AUTHENTICATION AND AUTHORIZATION
# ============================================================================

AUTH_USER_MODEL = 'accounts.User'

# Authentication backends
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

# Password validation
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

# Login/Logout settings
LOGIN_REDIRECT_URL = '/'
LOGIN_URL = '/auth/login/'
LOGOUT_REDIRECT_URL = '/'

# Password reset settings
PASSWORD_RESET_TIMEOUT = 86400  # 24 hours

# ============================================================================
# STATIC FILES AND MEDIA - Optimized for production
# ============================================================================

# Static files configuration
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []

# Static files finders (optimized order)
STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]

# Static files storage (optimized for production)
if DEBUG:
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
else:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# WhiteNoise configuration for production
WHITENOISE_USE_FINDERS = DEBUG
WHITENOISE_AUTOREFRESH = DEBUG
WHITENOISE_MAX_AGE = 31536000  # 1 year cache for production

# Media files configuration
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# File upload settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
FILE_UPLOAD_PERMISSIONS = 0o644

# ============================================================================
# EMAIL CONFIGURATION - Environment-based
# ============================================================================

if DEBUG:
    # Development email backend
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    # Production email configuration
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = config('EMAIL_HOST')
    EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
    EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
    EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
    EMAIL_HOST_USER = config('EMAIL_HOST_USER')
    EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
    
# Email settings
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@acrp.com')
SERVER_EMAIL = config('SERVER_EMAIL', default=DEFAULT_FROM_EMAIL)
EMAIL_SUBJECT_PREFIX = '[ACRP] '
EMAIL_TIMEOUT = 30

# ============================================================================
# INTERNATIONALIZATION AND LOCALIZATION
# ============================================================================

LANGUAGE_CODE = 'en-us'
TIME_ZONE = config('TIME_ZONE', default='UTC')
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Date and time formats
DATETIME_FORMAT = 'Y-m-d H:i:s'
DATE_FORMAT = 'Y-m-d'
TIME_FORMAT = 'H:i:s'

# ============================================================================
# DJANGO REST FRAMEWORK CONFIGURATION
# ============================================================================

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ] + (['rest_framework.renderers.BrowsableAPIRenderer'] if DEBUG else []),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
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

# ============================================================================
# THIRD-PARTY PACKAGE CONFIGURATION
# ============================================================================

# Crispy Forms
CRISPY_TEMPLATE_PACK = 'bootstrap4'
CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap4'

# Tailwind CSS
TAILWIND_APP_NAME = 'theme'
NPM_BIN_PATH = config('NPM_BIN_PATH', default='npm')

# Django Extensions
GRAPH_MODELS = {
    'all_applications': True,
    'group_models': True,
}

# ============================================================================
# PERFORMANCE OPTIMIZATION SETTINGS
# ============================================================================

# Database query optimization
if not DEBUG:
    # Prevent N+1 queries in production
    DATABASES['default']['OPTIONS'] = {
        **DATABASES['default'].get('OPTIONS', {}),
        'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
    }


# ============================================================================
# LOGGING CONFIGURATION - Comprehensive and structured
# ============================================================================

if DEBUG:
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
                '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
                'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
            } if not DEBUG else {
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
                'handlers': ['console'] if DEBUG else [],
                'level': 'DEBUG' if DEBUG else 'WARNING',
                'propagate': False,
            },
            'acrp': {
                'handlers': ['console', 'file', 'mail_admins'],
                'level': 'DEBUG' if DEBUG else 'INFO',
                'propagate': False,
            },
            'cpd_tracking': {
                'handlers': ['console', 'file'],
                'level': 'DEBUG' if DEBUG else 'INFO',
                'propagate': False,
            },
        },
    }
else:
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
            },
        },
        'root': {
            'handlers': ['console'],
            'level': 'WARNING',
        },
    }
    
# Ensure logs directory exists
(BASE_DIR / 'logs').mkdir(exist_ok=True)

# ============================================================================
# DEBUG TOOLBAR CONFIGURATION - Development only
# ============================================================================

if DEBUG:
    DEBUG_TOOLBAR_CONFIG = {
        'INTERCEPT_REDIRECTS': False,
        'SHOW_TOOLBAR_CALLBACK': lambda request: True,
        'HIDE_DJANGO_SQL': False,
        'SHOW_TEMPLATE_CONTEXT': True,
        'SQL_WARNING_THRESHOLD': 500,  # milliseconds
    }
    
    INTERNAL_IPS = [
        '127.0.0.1',
        'localhost',
    ]

# ============================================================================
# CUSTOM APPLICATION SETTINGS
# ============================================================================

# CPD Tracking specific settings
CPD_SETTINGS = {
    'DEFAULT_POINTS_PER_HOUR': 1.0,
    'MAX_FILE_UPLOAD_SIZE': 10 * 1024 * 1024,  # 10MB
    'EVIDENCE_ALLOWED_EXTENSIONS': ['.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png'],
    'AUTO_APPROVAL_THRESHOLD': 5.0,  # Hours
    'COMPLIANCE_CALCULATION_CACHE_TIMEOUT': 3600,  # 1 hour
    'NOTIFICATION_REMINDER_DAYS': [30, 14, 7, 1],  # Days before deadline
}

# Enrollment system settings
ENROLLMENT_SETTINGS = {
    'APPLICATION_TIMEOUT_DAYS': 90,
    'MAX_APPLICATIONS_PER_USER': 5,
    'REQUIRE_EVIDENCE_UPLOADS': True,
    'AUTO_GENERATE_CERTIFICATES': True,
}

# General application settings
APP_SETTINGS = {
    'SITE_NAME': 'ACRP Africa',
    'SITE_DESCRIPTION': 'Association of Christian Religious Practitioners',
    'CONTACT_EMAIL': config('CONTACT_EMAIL', default='info@acrp.org.za'),
    'SUPPORT_EMAIL': config('SUPPORT_EMAIL', default='acrp@acrpafrica.co.za'),
    'MAX_LOGIN_ATTEMPTS': 10,
    'LOGIN_LOCKOUT_DURATION': 500,  # 5 minutes
}

# ============================================================================
# MONITORING AND ANALYTICS - Simple deployment
# ============================================================================

# Application monitoring (optional - add services like Sentry only if needed)
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

# Performance monitoring
PERFORMANCE_MONITORING = {
    'SLOW_QUERY_THRESHOLD': 1000,  # milliseconds
    'MEMORY_USAGE_THRESHOLD': 500,  # MB
    'ENABLE_PROFILING': DEBUG,
}

# ============================================================================
# BACKGROUND TASKS CONFIGURATION - Simple deployment
# ============================================================================

# For simple deployments, we'll use Django's built-in management commands
# and scheduled cron jobs instead of Celery for background tasks
BACKGROUND_TASKS = {
    'EMAIL_BATCH_SIZE': 50,
    'NOTIFICATION_BATCH_SIZE': 100,
    'CLEANUP_OLDER_THAN_DAYS': 90,
    'MAINTENANCE_WINDOW_HOUR': 2,  # 2 AM
}

# ============================================================================
# ENVIRONMENT-SPECIFIC OVERRIDES
# ============================================================================

# Development overrides
if DEBUG:
    # Allow all hosts in development
    ALLOWED_HOSTS = ['*']
    
    # Disable email in development
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    
    # Enable SQL debugging
    LOGGING['loggers']['django.db.backends']['level'] = 'DEBUG'

# Production overrides
if ENVIRONMENT == 'production':
    # Force HTTPS
    SECURE_SSL_REDIRECT = True
    
    # Enable all security features
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    
    # Optimize for production
    CONN_MAX_AGE = 600
    
# Testing overrides
if 'test' in sys.argv or 'pytest' in sys.modules:
    # Use in-memory database for tests
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
    
    # Disable migrations for faster tests
    class DisableMigrations:
        def __contains__(self, item):
            return True
        def __getitem__(self, item):
            return None
    
    MIGRATION_MODULES = DisableMigrations()
    
    # Use dummy cache for tests
    CACHES['default']['BACKEND'] = 'django.core.cache.backends.dummy.DummyCache'
    
    # Disable logging during tests
    LOGGING['root']['level'] = 'CRITICAL'

# ============================================================================
# FINAL SETTINGS VALIDATION
# ============================================================================

# Validate critical settings
assert SECRET_KEY, "SECRET_KEY must be set in environment variables"
assert ALLOWED_HOSTS, "ALLOWED_HOSTS must be configured"

if not DEBUG:
    assert config('EMAIL_HOST', default=None), "EMAIL_HOST must be set in production"
    assert 'postgresql' in DATABASES['default']['ENGINE'] or 'mysql' in DATABASES['default']['ENGINE'], \
           "Production should use PostgreSQL or MySQL"

# Set default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Final environment info (for logging)
logger = logging.getLogger(__name__)
logger.info(f"ACRP Platform starting in {ENVIRONMENT} mode (DEBUG={DEBUG})")

# Cache table setup reminder for production
if not DEBUG and 'migrate' not in sys.argv:
    logger.info("Remember to create cache table: python manage.py createcachetable acrp_cache_table")