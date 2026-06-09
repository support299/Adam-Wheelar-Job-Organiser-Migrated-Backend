from .base import *  # noqa: F401, F403

DEBUG = True

INSTALLED_APPS += ['django_extensions']  # noqa: F405

# Relax CORS in development — allow all origins
CORS_ALLOW_ALL_ORIGINS = True

# Show SQL queries in the console
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'WARNING',
        },
        'apps': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
