import os
import ssl
import sys
import logging
from pathlib import Path
from decouple import config
import os
import sentry_sdk

# CORE DJANGO SETTINGS

# Build paths inside the project like this: BASE_DIR / 'subdir'
BASE_DIR = Path(__file__).resolve().parent.parent

# Use 'development', 'staging', or 'production'
ENVIRONMENT = 'production'
DEBUG = True

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
    "anymail",
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
    'app.errors.EnhancedErrorHandlingMiddleware',
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
                'app.context_processors.notifications'
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


ERROR_DB_LOGGING = True
ERROR_EMAIL_ALERTS = False
VERSION = '1.0.0'


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

handler404 = 'app.views.error_404'
handler500 = 'app.views.error_500'
handler403 = 'app.views.error_403'
handler400 = 'app.views.error_400'


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

# Download link settings
DEFAULT_DOWNLOAD_EXPIRY_DAYS = 30
DEFAULT_MAX_DOWNLOADS = 5

# Base URL for building absolute URLs (important for download links)
BASE_URL = 'https://ams.acrp.org.za'  # Replace with your domain
DEFAULT_FROM_EMAIL = 'ams@acrp.org.za'
DEFAULT_REPLY_TO_EMAIL = 'ams@acrp.org.za'
# File and card settings
MAX_CARD_FILE_SIZE = 5 * 1024 * 1024  # 5MB
CARD_DEFAULT_FORMAT = 'pdf'
CARD_IMAGE_DPI = 300

# EMAIL CONFIGURATION - Environment-based email backend


# EMAIL CONFIGURATION - Force Mailjet API with debugging
import logging

# Email sender configuration
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='ACRP Portal <ams@acrp.org.za>')
SERVER_EMAIL = DEFAULT_FROM_EMAIL
EMAIL_SUBJECT_PREFIX = config('EMAIL_SUBJECT_PREFIX', default='[ACRP] ')

# Force Mailjet API backend
EMAIL_BACKEND = "anymail.backends.mailjet.EmailBackend"
ANYMAIL = {
    "MAILJET_API_KEY": config('MAILJET_API_KEY'),
    "MAILJET_SECRET_KEY": config('MAILJET_SECRET_KEY'),
    "IGNORE_RECIPIENT_STATUS": True,  # Don't fail on unverified recipients
}

# Password reset settings
PASSWORD_RESET_TIMEOUT = 86400  # 24 hours

# Email debugging - Add this logger 
EMAIL_LOGGER = logging.getLogger('django.core.mail')
EMAIL_LOGGER.setLevel(logging.DEBUG)




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


# ============================================================================
# LOGGING CONFIGURATION - Comprehensive and environment-based
# ============================================================================


# Ensure logs directory exists BEFORE defining LOGGING
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True, parents=True)  # Create directory and any parent directories

# Define the main log file path
LOG_FILE_PATH = LOGS_DIR / 'acrp.log'

# Create the log file if it doesn't exist (with proper permissions)
if not LOG_FILE_PATH.exists():
    LOG_FILE_PATH.touch(mode=0o644)  # rw-r--r--
    print(f"Created log file: {LOG_FILE_PATH}")

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    
    # ------------------------------------------------------------------------
    # FORMATTERS - Define how log messages are formatted
    # ------------------------------------------------------------------------
    'formatters': {
        'verbose': {
            # Detailed format for file logging with all context
            'format': '[{levelname}] {asctime} | {name} | {module}.{funcName}:{lineno} | {process:d} {thread:d} | {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            # Simple format for console output (easier to read during development)
            'format': '[{levelname}] {asctime} | {name} | {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'json': {
            # JSON format for production log aggregation systems
            'format': '{levelname} {asctime} {name} {module} {funcName} {lineno} {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    
    # ------------------------------------------------------------------------
    # FILTERS - Control which log records are processed
    # ------------------------------------------------------------------------
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    
    # ------------------------------------------------------------------------
    # HANDLERS - Define where log messages go
    # ------------------------------------------------------------------------
    'handlers': {
        # Console handler - Always outputs to console (stdout)
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        
        # File handler - ALWAYS writes to logs/acrp.log
        'file': {
            'level': 'INFO',  # Capture INFO and above to file
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_FILE_PATH),  # Convert Path to string
            'maxBytes': 15728640,  # 15MB per file
            'backupCount': 10,  # Keep 10 backup files (150MB total)
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        
        # Error file handler - Separate file for errors only
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'acrp_errors.log'),
            'maxBytes': 10485760,  # 10MB per file
            'backupCount': 20,  # Keep more error logs (200MB total)
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        
        # Security log handler - Track security events
        'security_file': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'security.log'),
            'maxBytes': 10485760,  # 10MB
            'backupCount': 20,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        
    },
    
    # ------------------------------------------------------------------------
    # LOGGERS - Configure logging for different parts of the application
    # ------------------------------------------------------------------------
    'loggers': {
        # Root logger - Catches everything not caught by specific loggers
        '': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        
        # Django framework logger
        'django': {
            'handlers': ['console', 'file', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
        
        # Django request logger - Logs all HTTP requests
        'django.request': {
            'handlers': ['console', 'file', 'error_file'],
            'level': 'WARNING',  # Only log warnings and errors for requests
            'propagate': False,
        },
        
        # Django database logger - SQL queries
        'django.db.backends': {
            'handlers': ['console'] if config('SQL_DEBUG', default=False, cast=bool) else ['file'],
            'level': 'DEBUG' if config('SQL_DEBUG', default=False, cast=bool) else 'WARNING',
            'propagate': False,
        },
        
        # Django security logger - Security-related events
        'django.security': {
            'handlers': ['console', 'security_file'],
            'level': 'WARNING',
            'propagate': False,
        },
        
        # ACRP application logger - Your main application logs
        'acrp': {
            'handlers': ['console', 'file', 'error_file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        
        # CPD tracking logger - Specific to CPD functionality
        'cpd_tracking': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        
        # Affiliation card logger
        'affiliationcard': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        
        # Enrollment logger
        'enrollments': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        
        # Accounts/Authentication logger
        'accounts': {
            'handlers': ['console', 'file', 'security_file'],
            'level': 'INFO',
            'propagate': False,
        },

        'app.errors': {
            'handlers': ['console', 'file', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# ============================================================================
# LOGGING UTILITY FUNCTIONS
# ============================================================================

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.
    
    Usage in your code:
        from django.conf import settings
        logger = settings.get_logger(__name__)
        logger.info("Something happened")
    
    Args:
        name: Logger name (typically __name__ of the module)
    
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def log_application_startup():
    """
    Log application startup information.
    Call this at the end of settings.py
    """
    logger = logging.getLogger('acrp')
    
    logger.info("="*70)
    logger.info(f"ACRP Application Starting")
    logger.info(f"Environment: {ENVIRONMENT}")
    logger.info(f"Debug Mode: {DEBUG}")
    logger.info(f"Database: {DATABASES['default']['ENGINE']}")
    logger.info(f"Cache Backend: {CACHES['default']['BACKEND']}")
    logger.info(f"Log File: {LOG_FILE_PATH}")
    logger.info(f"Static Files: {STATICFILES_STORAGE}")
    logger.info("="*70)


def verify_log_permissions():
    """
    Verify that log files are writable.
    Raises exception if logs cannot be written.
    """
    import tempfile
    
    try:
        # Test write permissions on log file
        with open(LOG_FILE_PATH, 'a') as f:
            f.write(f"\n# Log verification at {logging.Formatter().formatTime(logging.LogRecord('test', 0, '', 0, '', (), None))}\n")
        
        logger = logging.getLogger('acrp')
        logger.info("✓ Log file permissions verified")
        return True
        
    except PermissionError as e:
        print(f"ERROR: Cannot write to log file {LOG_FILE_PATH}")
        print(f"Permission Error: {e}")
        print(f"Please check file permissions: chmod 644 {LOG_FILE_PATH}")
        raise
    except Exception as e:
        print(f"ERROR: Unexpected error with log file: {e}")
        raise


# ============================================================================
# ADDITIONAL LOG FILES SETUP
# ============================================================================

# Create additional log files if they don't exist
ADDITIONAL_LOG_FILES = [
    LOGS_DIR / 'acrp_errors.log',
    LOGS_DIR / 'security.log',
]

for log_file in ADDITIONAL_LOG_FILES:
    if not log_file.exists():
        log_file.touch(mode=0o644)
        print(f"Created log file: {log_file}")


# ============================================================================
# LOG FILE CLEANUP UTILITIES
# ============================================================================

def cleanup_old_logs(days: int = 30):
    """
    Clean up log files older than specified days.
    
    Usage:
        python manage.py shell
        >>> from django.conf import settings
        >>> settings.cleanup_old_logs(30)
    
    Args:
        days: Delete log files older than this many days
    """
    import time
    from datetime import datetime, timedelta
    
    cutoff_time = time.time() - (days * 86400)
    deleted_count = 0
    deleted_size = 0
    
    logger = logging.getLogger('acrp')
    
    for log_file in LOGS_DIR.glob('*.log*'):
        if log_file.stat().st_mtime < cutoff_time:
            file_size = log_file.stat().st_size
            log_file.unlink()
            deleted_count += 1
            deleted_size += file_size
            logger.info(f"Deleted old log file: {log_file.name} ({file_size / 1024:.2f} KB)")
    
    if deleted_count > 0:
        logger.info(f"Cleanup complete: {deleted_count} files deleted, {deleted_size / 1024 / 1024:.2f} MB freed")
    else:
        logger.info(f"No log files older than {days} days found")
    
    return deleted_count


def get_log_file_sizes():
    """
    Get sizes of all log files for monitoring.
    
    Returns:
        Dictionary with log file names and sizes in MB
    """
    log_sizes = {}
    total_size = 0
    
    for log_file in LOGS_DIR.glob('*.log*'):
        size_mb = log_file.stat().st_size / 1024 / 1024
        log_sizes[log_file.name] = round(size_mb, 2)
        total_size += size_mb
    
    log_sizes['_total_mb'] = round(total_size, 2)
    return log_sizes


# ============================================================================
# PRODUCTION LOG MONITORING SETUP
# ============================================================================

if not DEBUG:
    # In production, also log to syslog for centralized logging
    try:
        LOGGING['handlers']['syslog'] = {
            'level': 'INFO',
            'class': 'logging.handlers.SysLogHandler',
            'address': '/dev/log',  # Unix socket for syslog
            'formatter': 'verbose',
        }
        
        # Add syslog to acrp logger
        LOGGING['loggers']['acrp']['handlers'].append('syslog')
        
    except Exception as e:
        print(f"Warning: Could not configure syslog handler: {e}")


# ============================================================================
# VERIFICATION & STARTUP
# ============================================================================

# Verify log file permissions at startup
try:
    verify_log_permissions()
except Exception as e:
    print(f"CRITICAL: Log file verification failed!")
    print(f"Error: {e}")
    # In development, we continue; in production, we should probably exit
    if not DEBUG:
        import sys
        sys.exit(1)

# Log application startup information
log_application_startup()

# Print confirmation to console
print(f"\n{'='*70}")
print(f"✓ Logging configured successfully")
print(f"✓ Main log file: {LOG_FILE_PATH}")
print(f"✓ Error log file: {LOGS_DIR / 'acrp_errors.log'}")
print(f"✓ Security log file: {LOGS_DIR / 'security.log'}")
print(f"✓ Current log sizes: {get_log_file_sizes()}")
print(f"{'='*70}\n")
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



# Application monitoring with Sentry (optional)
MONITORING_ENABLED = config('MONITORING_ENABLED', default=True, cast=bool)

if MONITORING_ENABLED and config('SENTRY_DSN', default=None):
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        
        # Configure Sentry logging integration
        sentry_logging = LoggingIntegration(
            level=logging.INFO,        # Capture info and above as breadcrumbs
            event_level=logging.ERROR  # Send errors as events to Sentry
        )
        
        # Initialize Sentry SDK
        sentry_sdk.init(
            # FIXED: Remove extra 'dsn=' prefix, quotes, and trailing comma
            dsn='https://c4bea8401743f05e60cd6d8bff36c8ad@o4510151471202304.ingest.us.sentry.io/4510151474085888',
            integrations=[
                DjangoIntegration(),
                sentry_logging       
            ],
            traces_sample_rate=0.1, 
            send_default_pii=True,
            environment=ENVIRONMENT,
        )
        
        logger = logging.getLogger(__name__)
        logger.info(f"✓ Sentry monitoring initialized for environment: {ENVIRONMENT}")
        
    except ImportError:
        # Sentry SDK not installed - skip monitoring
        logger = logging.getLogger(__name__)
        logger.warning("Sentry SDK not installed. Error monitoring disabled.")
    except Exception as e:
        # Handle any other Sentry initialization errors gracefully
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to initialize Sentry: {e}")

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
    
    


# SETTINGS VALIDATION - Ensure critical settings are properly configured


# Validate essential environment variables
assert SECRET_KEY, "SECRET_KEY must be set in environment variables"
assert ALLOWED_HOSTS, "ALLOWED_HOSTS must be configured"



# Set default primary key field type for Django 3.2+
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# FINAL SETUP AND LOGGING


# Log startup information
logger = logging.getLogger(__name__)
logger.info(f"ACRP Platform starting in {ENVIRONMENT} mode (DEBUG={DEBUG})")

# Reminder for cache table creation in production
if not DEBUG and 'migrate' not in sys.argv and 'runserver' not in sys.argv:
    logger.info("Remember to create cache table: python manage.py createcachetable acrp_cache_table")