from django.conf import settings

from .access_control import GRUPOS_EMECA, usuario_tem_modulo


def acessos_emeca(request):
    user = getattr(request, "user", None)
    strict = getattr(settings, "EMECA_RBAC_STRICT", True)
    return {
        "acessos_emeca": {
            chave: usuario_tem_modulo(user, chave, strict=strict)
            for chave in GRUPOS_EMECA
        }
    }
