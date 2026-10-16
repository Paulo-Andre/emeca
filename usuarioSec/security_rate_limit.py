import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from .models import SecurityRateLimit


def _hash(valor):
    segredo = settings.SECRET_KEY.encode("utf-8")
    bruto = str(valor or "").encode("utf-8")
    return hmac.new(segredo, bruto, hashlib.sha256).hexdigest()


def ip_cliente(request):
    if getattr(settings, "TRUST_PROXY_HEADERS", False):
        cf_ip = (request.META.get("HTTP_CF_CONNECTING_IP") or "").strip()
        if cf_ip:
            return cf_ip
        forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
        if forwarded:
            return forwarded.split(",")[0].strip()
    return (request.META.get("REMOTE_ADDR") or "desconhecido").strip()


def chave_limite(bucket, identidade):
    return _hash(f"{bucket}:{identidade}")


def consumir_limite(bucket, identidade, limite, janela_segundos):
    if not getattr(settings, "RATE_LIMIT_ENABLED", True):
        return True, 0

    agora = timezone.now()
    chave = chave_limite(bucket, identidade)
    janela = timedelta(seconds=janela_segundos)

    for tentativa in range(2):
        try:
            with transaction.atomic():
                try:
                    registro = (
                        SecurityRateLimit.objects
                        .select_for_update()
                        .get(chave=chave)
                    )
                except SecurityRateLimit.DoesNotExist:
                    try:
                        SecurityRateLimit.objects.create(
                            chave=chave,
                            janela_inicio=agora,
                            contador=1,
                        )
                        return True, 0
                    except IntegrityError:
                        if tentativa == 0:
                            continue
                        raise

                if registro.bloqueado_ate and registro.bloqueado_ate > agora:
                    restante = max(
                        1,
                        int((registro.bloqueado_ate - agora).total_seconds()),
                    )
                    return False, restante

                if agora - registro.janela_inicio >= janela:
                    registro.janela_inicio = agora
                    registro.contador = 1
                    registro.bloqueado_ate = None
                    registro.save(
                        update_fields=[
                            "janela_inicio",
                            "contador",
                            "bloqueado_ate",
                            "atualizado_em",
                        ]
                    )
                    return True, 0

                registro.contador += 1
                if registro.contador > limite:
                    registro.bloqueado_ate = registro.janela_inicio + janela
                    restante = max(
                        1,
                        int((registro.bloqueado_ate - agora).total_seconds()),
                    )
                    registro.save(
                        update_fields=[
                            "contador",
                            "bloqueado_ate",
                            "atualizado_em",
                        ]
                    )
                    return False, restante

                registro.save(update_fields=["contador", "atualizado_em"])
                return True, 0
        except IntegrityError:
            if tentativa == 0:
                continue
            return False, janela_segundos
        except DatabaseError:
            # Falha fechada: em contenção/falha do banco, não libera uma
            # sequência de tentativas potencialmente abusiva.
            return False, janela_segundos

    return False, janela_segundos


def limpar_limite(bucket, identidade):
    chave = chave_limite(bucket, identidade)
    SecurityRateLimit.objects.filter(chave=chave).delete()


def limpar_limites_antigos(dias=2):
    limite = timezone.now() - timedelta(days=dias)
    return SecurityRateLimit.objects.filter(atualizado_em__lt=limite).delete()
