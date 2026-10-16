from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DJANGO_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "").strip()
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-change-me"
    else:
        raise RuntimeError("Defina DJANGO_SECRET_KEY antes de iniciar o sistema.")

DOCUMENT_SIGNING_KEY = os.getenv("DOCUMENT_SIGNING_KEY", "").strip()
if not DOCUMENT_SIGNING_KEY:
    if DEBUG:
        DOCUMENT_SIGNING_KEY = "dev-only-document-signing-key"
    else:
        raise RuntimeError("Defina DOCUMENT_SIGNING_KEY antes de iniciar o sistema.")

ALLOWED_HOSTS = [x.strip() for x in os.getenv(
    "DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost"
).split(",") if x.strip()]

CORS_ALLOWED_ORIGINS = [x.strip() for x in os.getenv(
    "DJANGO_CORS_ALLOWED_ORIGINS", ""
).split(",") if x.strip()]
CORS_ALLOW_ALL_ORIGINS = False

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework", "corsheaders", "cadastro", "secretaria", "usuarioSec",
    "historico", "site_publico",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "usuarioSec.middleware.SecurityRateLimitMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "historico.middleware.SecurityAuditMiddleware",
    "usuarioSec.middleware.LoginRequiredMiddleware",
    "usuarioSec.middleware.ModuleAccessMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "App.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "site_publico.context_processors.site_publico",
        "usuarioSec.context_processors.acessos_emeca",
    ]},
}]
WSGI_APPLICATION = "App.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(os.getenv("DJANGO_DB_PATH", str(BASE_DIR / "db.sqlite3"))),
        "OPTIONS": {"timeout": 60},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "App" / "static", BASE_DIR / "frontend_publico" / "dist"]

MEDIA_URL = "/media/"
MEDIA_ROOT = DATA_DIR / "media"
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/entrada/"
LOGOUT_REDIRECT_URL = "/login/"

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = int(os.getenv("DJANGO_SESSION_AGE", "3600"))
SESSION_SAVE_EVERY_REQUEST = True

SECURE_COOKIES = os.getenv("DJANGO_SECURE_COOKIES", "0") == "1"
SESSION_COOKIE_SECURE = SECURE_COOKIES
CSRF_COOKIE_SECURE = SECURE_COOKIES
SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "0") == "1"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
TRUST_PROXY_HEADERS = os.getenv("DJANGO_TRUST_PROXY_HEADERS", "0") == "1"
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = os.getenv("DJANGO_HSTS_PRELOAD", "0") == "1"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

EMECA_RBAC_STRICT = os.getenv("DJANGO_RBAC_STRICT", "1") == "1"

RATE_LIMIT_ENABLED = os.getenv("DJANGO_RATE_LIMIT_ENABLED", "1") == "1"
LOGIN_RATE_LIMIT_ACCOUNT = max(3, int(os.getenv("DJANGO_LOGIN_RATE_ACCOUNT", "8")))
LOGIN_RATE_LIMIT_IP = max(10, int(os.getenv("DJANGO_LOGIN_RATE_IP", "30")))
LOGIN_RATE_LIMIT_WINDOW = max(60, int(os.getenv("DJANGO_LOGIN_RATE_WINDOW", "900")))
BOLETIM_RATE_LIMIT_IP = max(3, int(os.getenv("DJANGO_BOLETIM_RATE_IP", "10")))
BOLETIM_RATE_LIMIT_WINDOW = max(60, int(os.getenv("DJANGO_BOLETIM_RATE_WINDOW", "900")))
MATRICULA_RATE_LIMIT_IP = max(5, int(os.getenv("DJANGO_MATRICULA_RATE_IP", "30")))
MATRICULA_RATE_LIMIT_WINDOW = max(60, int(os.getenv("DJANGO_MATRICULA_RATE_WINDOW", "3600")))
CONTATO_RATE_LIMIT_IP = max(5, int(os.getenv("DJANGO_CONTATO_RATE_IP", "20")))
CONTATO_RATE_LIMIT_WINDOW = max(60, int(os.getenv("DJANGO_CONTATO_RATE_WINDOW", "900")))

CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.getenv(
    "DJANGO_CSRF_TRUSTED_ORIGINS", ""
).split(",") if x.strip()]

DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 5000

# Integração WhatsApp (WA-AKG)
WA_AKG_BASE_URL = os.getenv("WA_AKG_BASE_URL", "").strip().rstrip("/")
WA_AKG_API_KEY = os.getenv("WA_AKG_API_KEY", "").strip()
WA_AKG_SESSION_ID = os.getenv("WA_AKG_SESSION_ID", "emeca-secretaria").strip()
WA_AKG_TIMEOUT_SECONDS = max(2, int(os.getenv("WA_AKG_TIMEOUT_SECONDS", "8")))
WA_AKG_BROADCAST_DELAY_MS = max(500, min(60000, int(os.getenv("WA_AKG_BROADCAST_DELAY_MS", "10000"))))


REQUIRE_SECURE_PRODUCTION = os.getenv("DJANGO_REQUIRE_SECURE_PRODUCTION", "0") == "1"
if REQUIRE_SECURE_PRODUCTION and not DEBUG:
    faltando = []
    if not SECURE_COOKIES:
        faltando.append("DJANGO_SECURE_COOKIES=1")
    if not SECURE_SSL_REDIRECT:
        faltando.append("DJANGO_SECURE_SSL_REDIRECT=1")
    if SECURE_HSTS_SECONDS < 86400:
        faltando.append("DJANGO_HSTS_SECONDS>=86400")
    if not CSRF_TRUSTED_ORIGINS:
        faltando.append("DJANGO_CSRF_TRUSTED_ORIGINS")
    if faltando:
        raise RuntimeError(
            "Hardening de produção incompleto: " + ", ".join(faltando)
        )
