from .base import *  # noqa

DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']

# Override static files storage for development (no manifest required)
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
