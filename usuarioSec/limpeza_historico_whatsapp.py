"""Limpeza local de dados WhatsApp depois de exclusão confirmada no WA-AKG.

Nunca elimina dados escolares (alunos, boletins, documentos ou usuários).
A sessão é identificada por ID imutável; a nova sessão recebe outro ID.
"""
from django.db import transaction

from .models import (
    ContatoAgendaWhatsApp,
    ConversaExcluidaWhatsApp,
    EnvioBoletimWhatsApp,
    EstadoConversaWhatsApp,
    EtiquetaConversaWhatsApp,
    GrupoOcultoWhatsApp,
    IdentidadeContatoWhatsApp,
    LeituraChatWhatsApp,
    MensagemOcultaWhatsApp,
)
from .sessao_whatsapp import criar_sessao_isolada, sessao_atual_id


@transaction.atomic
def limpar_emeca_e_criar_sessao_nova(sessao_antiga):
    """Apaga registros EMECA daquela conta e troca o ponteiro atomicamente."""
    if not sessao_antiga or sessao_atual_id() != sessao_antiga:
        raise ValueError("A sessão ativa mudou. Exclusão cancelada.")

    modelos = (
        EnvioBoletimWhatsApp,  # elimina também itens de envio via FK
        LeituraChatWhatsApp,
        IdentidadeContatoWhatsApp,
        ContatoAgendaWhatsApp,
        EstadoConversaWhatsApp,
        EtiquetaConversaWhatsApp,
        MensagemOcultaWhatsApp,
        ConversaExcluidaWhatsApp,
        GrupoOcultoWhatsApp,
    )
    totals = {}
    for modelo in modelos:
        queryset = modelo.objects.filter(sessao=sessao_antiga)
        totals[modelo.__name__] = queryset.count()
        queryset.delete()

    nova = criar_sessao_isolada()
    if nova["anterior"] != sessao_antiga:
        raise ValueError("Sessão ativa inesperada durante rotação.")
    return {"sessao": nova["atual"], "removidos": totals}
