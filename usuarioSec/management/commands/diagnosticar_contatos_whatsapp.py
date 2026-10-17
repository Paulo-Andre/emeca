"""Diagnóstico sem divulgar números, nomes ou mensagens do WhatsApp."""
from django.core.management.base import BaseCommand

from usuarioSec.whatsapp_gateway import (
    WhatsAppGatewayError,
    listar_chats,
    listar_contatos,
)
from usuarioSec.whatsapp_views import (
    _contatos_persistidos_wa,
    _identidades_wa,
    _jid_eh_telefone,
    _jids_do_registro,
    _mapa_aliases_wa,
    _nome_disponivel_no_wa,
)


class Command(BaseCommand):
    help = (
        "Mostra contagens (sem dados pessoais) de contatos sem nome/telefone "
        "e identifica se o WA-AKG está retornando associações LID."
    )

    def handle(self, *args, **options):
        try:
            resposta = listar_chats()
            resposta_contatos = listar_contatos()
        except WhatsAppGatewayError as exc:
            self.stderr.write(self.style.ERROR(
                "Falha ao consultar o WA-AKG: " + str(exc.status_code or "gateway")
            ))
            return

        chats = resposta.get("data", []) if isinstance(resposta, dict) else []
        contatos = (
            resposta_contatos.get("data", [])
            if isinstance(resposta_contatos, dict) else []
        )
        chats = [item for item in chats if isinstance(item, dict)]
        contatos = [item for item in contatos if isinstance(item, dict)]
        identidades = _identidades_wa()
        grupos = _mapa_aliases_wa(
            contatos + _contatos_persistidos_wa(identidades), chats
        )
        mapa_contatos = {}
        for item in contatos:
            for jid in _jids_do_registro(item):
                mapa_contatos.setdefault(jid, []).append(item)

        com_telefone = com_nome = sem_identidade = lids = 0
        for chat in chats:
            jid = str(chat.get("jid") or "")
            if not jid:
                continue
            if jid.endswith("@lid"):
                lids += 1
            aliases = grupos.get(jid, (jid,))
            telefone = any(_jid_eh_telefone(item) for item in aliases)
            nome = _nome_disponivel_no_wa(chat)
            if not nome:
                nome = next(
                    (
                        _nome_disponivel_no_wa(contato)
                        for alias in aliases
                        for contato in mapa_contatos.get(alias, [])
                        if _nome_disponivel_no_wa(contato)
                    ),
                    "",
                )
            if not nome:
                nome = next(
                    (
                        item["nome_exibicao"]
                        for item in identidades
                        if item["jid"] in aliases and item["nome_exibicao"]
                    ),
                    "",
                )
            com_telefone += bool(telefone)
            com_nome += bool(nome)
            sem_identidade += not (telefone or nome)

        self.stdout.write("Diagnóstico da integração EMECA / WA-AKG")
        self.stdout.write(f"Conversas recebidas na lista: {len(chats)}")
        self.stdout.write(f"Cadastros retornados pelo WA-AKG: {len(contatos)}")
        self.stdout.write(f"Conversas recebidas como LID: {lids}")
        self.stdout.write(f"Conversas com telefone confirmado: {com_telefone}")
        self.stdout.write(f"Conversas com algum nome disponível: {com_nome}")
        self.stdout.write(f"Conversas sem nome e sem telefone: {sem_identidade}")
        self.stdout.write(f"Identificações persistidas no EMECA: {len(identidades)}")
        self.stdout.write(
            "Obs.: a API de chats do WA-AKG limita a lista padrão às "
            "50 conversas mais recentes. Este relatório não modifica dados."
        )
