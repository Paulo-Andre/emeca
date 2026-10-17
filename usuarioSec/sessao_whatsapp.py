"""Isolamento não destrutivo entre contas WhatsApp no EMECA.

Uma nova conta usa um ID de sessão WA-AKG único. Desvincular/login na mesma
sessão antiga reutilizava a mesma FK e misturava todas as mensagens.
"""
import secrets

from django.conf import settings
from django.db import transaction

from .models import SessaoWhatsAppAtiva


def sessao_atual_id():
    """Compatível com a instalação legada até a primeira troca de conta."""
    return (
        SessaoWhatsAppAtiva.objects.filter(chave="secretaria")
        .values_list("sessao_id", flat=True)
        .first()
        or settings.WA_AKG_SESSION_ID
    )


def criar_sessao_isolada():
    """Troca atomicamente o apontador, preservando todos os dados anteriores.

    O ID novo é criptograficamente aleatório e nunca reutiliza uma sessão já
    existente. Deve ser chamado após interromper o socket da conta anterior.
    """
    with transaction.atomic():
        registro, _ = SessaoWhatsAppAtiva.objects.select_for_update().get_or_create(
            chave="secretaria",
            defaults={"sessao_id": settings.WA_AKG_SESSION_ID},
        )
        anterior = registro.sessao_id
        nova = "emeca-" + secrets.token_hex(16)
        while nova == anterior or SessaoWhatsAppAtiva.objects.filter(
            sessao_id=nova
        ).exists():
            nova = "emeca-" + secrets.token_hex(16)
        registro.sessao_id = nova
        registro.save(update_fields=["sessao_id", "atualizado_em"])
        return {"anterior": anterior, "atual": nova}
