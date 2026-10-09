import os
from pathlib import Path

import pymysql
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv


pymysql.install_as_MySQLdb()

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-local-development-key"
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false"
        )
# The Windows launcher supplies current LAN addresses without rewriting .env.
ALLOWED_HOSTS = list(dict.fromkeys(
    host.strip()
    for value in (os.getenv("DJANGO_ALLOWED_HOSTS", ""), os.getenv("DJANGO_LAN_HOSTS", ""))
    for host in value.replace("，", ",").split(",")
    if host.strip()
))

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "personnel.apps.PersonnelConfig",
    "sampling.apps.SamplingConfig",
    "audit.apps.AuditConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("MYSQL_DATABASE", "selectrom"),
        "USER": os.getenv("MYSQL_USER", "selectrom"),
        "PASSWORD": os.getenv("MYSQL_PASSWORD", ""),
        "HOST": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "PORT": os.getenv("MYSQL_PORT", "3306"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
SAMPLING_PHOTOS_ROOT = BASE_DIR / "SamplingPhotos"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"
TIANDITU_API_KEY = os.getenv("TIANDITU_API_KEY", "")
TIANDITU_DIRECT_EGRESS = os.getenv("TIANDITU_DIRECT_EGRESS", "false").lower() == "true"
TIANDITU_DIRECT_SOURCE_IP = os.getenv("TIANDITU_DIRECT_SOURCE_IP", "")
TIANDITU_DIRECT_INTERFACE_INDEX = os.getenv("TIANDITU_DIRECT_INTERFACE_INDEX", "")
TIANDITU_DIRECT_DNS_SERVERS = [
    server.strip()
    for server in os.getenv("TIANDITU_DIRECT_DNS_SERVERS", "").split(",")
    if server.strip()
]
