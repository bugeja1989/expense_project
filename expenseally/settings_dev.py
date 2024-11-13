from .settings import *

# Override settings for development
DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# Use SQLite for development
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Email backend for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Disable SSL/HTTPS requirements
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Debug toolbar settings
INSTALLED_APPS += ['debug_toolbar']
MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
INTERNAL_IPS = ['127.0.0.1']

# Disable whitenoise for development
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# Cache settings for development
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Celery settings for development
CELERY_TASK_ALWAYS_EAGER = True  # Tasks are executed immediately
CELERY_TASK_EAGER_PROPAGATES = True  # Propagate exceptions in eager mode