from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from .access_control import GRUPO_WHATSAPP
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.cache import cache
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from site_publico.models import AlunoBoletim, BoletimAluno, PeriodoBoletim

from .management.commands.processar_envios_whatsapp import (
    claim_proximo_lote,
    recuperar_lotes_obsoletos,
)
from .models import (
    EnvioBoletimWhatsApp,
    ItemEnvioBoletimWhatsApp,
    IdentidadeContatoWhatsApp,
    LeituraChatWhatsApp,
    TelefoneDeclaracao,
    declaracao,
)
from .whatsapp_views import (
    _enriquecer_chats,
    _sincronizar_nao_lidas,
    _aliases_contato_wa,
    _normalizar_jid,
    _resolver_boletins_destinatarios,
    _resolver_destinatarios,
)


def autorizar_operador_whatsapp_teste(usuario):
    """Concede o perfil exigido pelo RBAC somente ao usuário deste teste.

    Não altera permissões de produção nem interfere nos testes negativos
    de operadores sem permissão.
    """
    grupo, _ = Group.objects.get_or_create(name=GRUPO_WHATSAPP)
    usuario.groups.add(grupo)
    return usuario


class WhatsAppDestinatariosTests(TestCase):
    def setUp(self):
        self.aluna_a = declaracao.objects.create(
            nomeDoAluno="ALUNA A",
            turmaDoAluno="1º A",
        )
        self.aluno_b = declaracao.objects.create(
            nomeDoAluno="ALUNO B",
            turmaDoAluno="2º B",
        )

        self.mae_a = TelefoneDeclaracao.objects.create(
            declaracao=self.aluna_a,
            tipo="MAE",
            telefone="(38) 99999-1111",
        )
        TelefoneDeclaracao.objects.create(
            declaracao=self.aluna_a,
            tipo="PAI",
            telefone="38 98888-2222",
        )
        TelefoneDeclaracao.objects.create(
            declaracao=self.aluno_b,
            tipo="MAE",
            telefone="+55 (38) 99999-1111",
        )
        TelefoneDeclaracao.objects.create(
            declaracao=self.aluno_b,
            tipo="RESPONSAVEL",
            telefone="9999-0000",
        )

    def test_normaliza_numero_brasileiro_para_jid(self):
        self.assertEqual(
            _normalizar_jid("(38) 99999-1111"),
            "5538999991111@s.whatsapp.net",
        )
        self.assertEqual(
            _normalizar_jid("+55 38 98888-2222"),
            "5538988882222@s.whatsapp.net",
        )
        self.assertEqual(
            _normalizar_jid("(55) 99999-1111"),
            "5555999991111@s.whatsapp.net",
        )
        self.assertIsNone(_normalizar_jid("9999-0000"))

    def test_envio_para_todos_remove_duplicados(self):
        destinatarios, invalidos, _ = _resolver_destinatarios("todos")
        self.assertEqual(len(destinatarios), 2)
        self.assertEqual(invalidos, 1)

    def test_envio_por_turma_filtra_alunos(self):
        destinatarios, invalidos, _ = _resolver_destinatarios(
            "turma",
            turma="1º A",
        )
        self.assertEqual(len(destinatarios), 2)
        self.assertEqual(invalidos, 0)

    def test_envio_individual_escolhe_um_contato(self):
        destinatarios, invalidos, _ = _resolver_destinatarios(
            "individual",
            contato_id=self.mae_a.id,
        )
        self.assertEqual(
            destinatarios,
            ["5538999991111@s.whatsapp.net"],
        )
        self.assertEqual(invalidos, 0)

    def test_sem_tipos_selecionados_nao_envia_para_todos(self):
        destinatarios, invalidos, _ = _resolver_destinatarios(
            "todos",
            tipos=[],
        )
        self.assertEqual(destinatarios, [])
        self.assertEqual(invalidos, 0)


class WhatsAppBoletimTests(TestCase):
    def setUp(self):
        self.declaracao_a = declaracao.objects.create(
            nomeDoAluno="ALUNA A",
            turmaDoAluno="1º A",
        )
        self.mae_a = TelefoneDeclaracao.objects.create(
            declaracao=self.declaracao_a,
            tipo="MAE",
            telefone="(38) 99999-1111",
        )
        TelefoneDeclaracao.objects.create(
            declaracao=self.declaracao_a,
            tipo="PAI",
            telefone="(38) 98888-2222",
        )
        self.periodo_a = PeriodoBoletim.objects.create(
            tipo="TRIMESTRE",
            numero=2,
            ano=2026,
            turma="1º A",
            regente="Professora Ana",
            publicado=True,
        )
        self.aluna_a = AlunoBoletim.objects.create(nome="ALUNA A", declaracao=self.declaracao_a)
        self.boletim_a = BoletimAluno.objects.create(
            periodo=self.periodo_a,
            aluno=self.aluna_a,
            faltas_totais=3,
        )

    def test_resolve_boletim_publicado_por_turma(self):
        dados = _resolver_boletins_destinatarios(
            "turma",
            "TRIMESTRE",
            2,
            2026,
            turma="1º A",
        )

        self.assertEqual(dados["alunos"], 1)
        self.assertEqual(len(dados["itens"]), 2)
        self.assertTrue(
            all(item["boletim"].pk == self.boletim_a.pk for item in dados["itens"])
        )

    def test_mesmo_telefone_recebe_boletins_de_irmaos_separadamente(self):
        declaracao_b = declaracao.objects.create(
            nomeDoAluno="ALUNO B",
            turmaDoAluno="2º B",
        )
        TelefoneDeclaracao.objects.create(
            declaracao=declaracao_b,
            tipo="MAE",
            telefone="+55 (38) 99999-1111",
        )
        periodo_b = PeriodoBoletim.objects.create(
            tipo="TRIMESTRE",
            numero=2,
            ano=2026,
            turma="2º B",
            publicado=True,
        )
        aluno_b = AlunoBoletim.objects.create(nome="ALUNO B", declaracao=declaracao_b)
        boletim_b = BoletimAluno.objects.create(
            periodo=periodo_b,
            aluno=aluno_b,
        )

        dados = _resolver_boletins_destinatarios(
            "todos",
            "TRIMESTRE",
            2,
            2026,
        )
        itens_numero_compartilhado = [
            item
            for item in dados["itens"]
            if item["jid"] == "5538999991111@s.whatsapp.net"
        ]

        self.assertEqual(len(itens_numero_compartilhado), 2)
        self.assertEqual(
            {item["boletim"].pk for item in itens_numero_compartilhado},
            {self.boletim_a.pk, boletim_b.pk},
        )

    def test_homonimo_nao_recebe_notas_de_outra_declaracao(self):
        outro = declaracao.objects.create(
            nomeDoAluno="ALUNA A", turmaDoAluno="1º A",
        )
        telefone = TelefoneDeclaracao.objects.create(
            declaracao=outro, tipo="RESPONSAVEL",
            telefone="(38) 97777-3333",
        )
        dados = _resolver_boletins_destinatarios(
            "individual", "TRIMESTRE", 2, 2026, contato_id=telefone.pk,
        )
        self.assertEqual(dados["itens"], [])
        self.assertEqual(dados["sem_boletim"], 1)

    def test_boletim_nao_publicado_nao_entra_no_envio(self):
        self.periodo_a.publicado = False
        self.periodo_a.save(update_fields=["publicado", "atualizado_em"])

        dados = _resolver_boletins_destinatarios(
            "individual",
            "TRIMESTRE",
            2,
            2026,
            contato_id=self.mae_a.pk,
        )

        self.assertEqual(dados["itens"], [])
        self.assertEqual(dados["sem_boletim"], 1)

    def test_post_coloca_pdf_personalizado_na_fila(self):
        usuario = get_user_model().objects.create_user(
            username="secretaria_whatsapp",
            password="senha-segura-123",
        )
        autorizar_operador_whatsapp_teste(usuario)
        self.client.force_login(usuario)

        with (
            patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True),
            patch(
                "usuarioSec.whatsapp_views.obter_sessao",
                return_value={"data": {"status": "CONNECTED"}},
            ),
        ):
            response = self.client.post(
                reverse("whatsapp_enviar"),
                {
                    "conteudo": "boletim",
                    "modo": "individual",
                    "contato_id": str(self.mae_a.pk),
                    "boletim_tipo": "TRIMESTRE",
                    "boletim_numero": "2",
                    "boletim_ano": "2026",
                    "mensagem_boletim": "Olá! Segue o boletim de {aluno}.",
                },
            )

        self.assertEqual(response.status_code, 302)
        envio = EnvioBoletimWhatsApp.objects.get()
        self.assertEqual(envio.total, 1)
        self.assertEqual(envio.status, "PENDENTE")
        item = ItemEnvioBoletimWhatsApp.objects.get(envio=envio)
        self.assertEqual(item.boletim_id, self.boletim_a.pk)
        self.assertEqual(item.jid, "5538999991111@s.whatsapp.net")


class WhatsAppWorkerConcorrenciaTests(TestCase):
    def _envio(self, status="PENDENTE", iniciado_em=None):
        from .sessao_whatsapp import sessao_atual_id
        envio = EnvioBoletimWhatsApp.objects.create(
            tipo_periodo="TRIMESTRE",
            numero_periodo=1,
            ano=2026,
            modo="todos",
            sessao=sessao_atual_id(),
            status=status,
        )
        if iniciado_em is not None:
            EnvioBoletimWhatsApp.objects.filter(pk=envio.pk).update(
                iniciado_em=iniciado_em
            )
            envio.refresh_from_db()
        return envio

    def test_claim_condicional_nao_entrega_mesmo_lote_duas_vezes(self):
        primeiro = self._envio()
        segundo = self._envio()

        claim_a = claim_proximo_lote()
        claim_b = claim_proximo_lote()

        self.assertEqual(claim_a.pk, primeiro.pk)
        self.assertEqual(claim_b.pk, segundo.pk)
        primeiro.refresh_from_db()
        segundo.refresh_from_db()
        self.assertEqual(primeiro.status, "PROCESSANDO")
        self.assertEqual(segundo.status, "PROCESSANDO")

    def test_recuperacao_nao_toca_lote_processando_recentemente(self):
        recente = self._envio(
            status="PROCESSANDO",
            iniciado_em=timezone.now() - timedelta(minutes=5),
        )

        recuperar_lotes_obsoletos()

        recente.refresh_from_db()
        self.assertEqual(recente.status, "PROCESSANDO")



class WhatsAppInboxTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="atendimento_whatsapp",
            password="Senha-Sintetica-2026!",
        )
        autorizar_operador_whatsapp_teste(self.usuario)
        self.client.force_login(self.usuario)

    @patch("usuarioSec.whatsapp_views.listar_chats")
    @patch("usuarioSec.whatsapp_views.obter_sessao")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_tela_mensagens_carrega_sem_bloquear_por_conversas(
        self,
        _configurado,
        obter_sessao_mock,
        listar_chats_mock,
    ):
        obter_sessao_mock.return_value = {"data": {"status": "CONNECTED"}}
        listar_chats_mock.return_value = {
            "status": True,
            "data": [
                {
                    "jid": "5538999990000@s.whatsapp.net",
                    "name": "RESPONSAVEL SINTETICO",
                    "lastMessage": {
                        "content": "Olá",
                        "timestamp": "2026-10-17T01:00:00.000Z",
                        "type": "TEXT",
                    },
                }
            ],
        }

        response = self.client.get(reverse("whatsapp_mensagens"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Conversas")
        self.assertNotContains(response, "RESPONSAVEL SINTETICO")
        listar_chats_mock.assert_not_called()
        self.assertContains(response, "refreshChats(true);")
        self.assertContains(response, 'id="wa-chats-iniciais"')
        self.assertContains(response, 'id="newChatButton"')
        self.assertContains(response, 'id="refreshChats"')
        self.assertNotContains(response, 'class="header whatsapp-inbox-header"')
        self.assertNotContains(response, 'class="wa-header-actions"')

    @patch("usuarioSec.whatsapp_views._sincronizar_nao_lidas",
           side_effect=lambda _usuario, chats: chats)
    @patch("usuarioSec.whatsapp_views._filtrar_conversas_excluidas_wa",
           side_effect=lambda _usuario, chats: chats)
    @patch("usuarioSec.whatsapp_views._enriquecer_chats",
           side_effect=lambda chats: chats)
    @patch("usuarioSec.whatsapp_views.listar_chats_pagina")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_api_conversas_paginadas_com_cursor(
        self, _gateway, pagina, _enriquecer, _filtrar, _nao_lidas,
    ):
        pagina.return_value = {
            "status": True,
            "data": [{"jid": "5538999990000@s.whatsapp.net"}],
            "meta": {"nextBefore": "2026-10-18T10:00:00.000Z"},
        }
        response = self.client.get(
            reverse("whatsapp_chats_api"),
            {"limit": "30", "before": "2026-10-19T10:00:00Z"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(len(response.json()["chats"]), 1)
        self.assertEqual(response.json()["nextBefore"], "2026-10-18T10:00:00.000Z")
        pagina.assert_called_once_with(limit=30, before="2026-10-19T10:00:00Z")

    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_api_conversas_recusa_cursor_invalido(self, _gateway):
        response = self.client.get(
            reverse("whatsapp_chats_api"), {"before": "cursor-invalido"},
        )
        self.assertEqual(response.status_code, 400)

    @patch("usuarioSec.whatsapp_views._sincronizar_nao_lidas",
           side_effect=lambda _usuario, chats: chats)
    @patch("usuarioSec.whatsapp_views._filtrar_conversas_excluidas_wa",
           side_effect=lambda _usuario, chats: chats)
    @patch("usuarioSec.whatsapp_views._enriquecer_chats",
           side_effect=lambda chats: chats)
    @patch("usuarioSec.whatsapp_views._combinar_chats_e_grupos_wa",
           side_effect=lambda chats: chats)
    @patch("usuarioSec.whatsapp_views.listar_chats_pagina")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_api_conversas_limita_tamanho_sem_carregar_todo_historico(
        self, _gateway, pagina, _combinar, _enriquecer, _filtrar, _nao_lidas,
    ):
        pagina.return_value = {"status": True, "data": [], "meta": {}}
        response = self.client.get(reverse("whatsapp_chats_api"), {"limit": "2000"})
        self.assertEqual(response.status_code, 200)
        pagina.assert_called_once_with(limit=50, before="")
        self.assertIsNone(response.json()["nextBefore"])

    @patch("usuarioSec.whatsapp_views.listar_contatos")
    def test_enriquece_lid_com_numero_real_nome_e_foto(self, listar_contatos_mock):
        listar_contatos_mock.return_value = {
            "data": [
                {
                    "jid": "184774392074394@lid",
                    "lid": "184774392074394@lid",
                    "remoteJidAlt": "5538999990000@s.whatsapp.net",
                    "name": "RESPONSAVEL TESTE",
                    "notify": "Responsável",
                    "profilePic": "https://example.invalid/foto.jpg",
                }
            ]
        }

        chats = _enriquecer_chats([
            {
                "jid": "184774392074394@lid",
                "lastMessage": {"content": "Olá"},
            }
        ])

        self.assertEqual(chats[0]["phoneJid"], "5538999990000@s.whatsapp.net")
        self.assertEqual(chats[0]["name"], "RESPONSAVEL TESTE")
        self.assertEqual(chats[0]["profilePic"], "https://example.invalid/foto.jpg")
        self.assertEqual(chats[0]["photoJid"], "5538999990000@s.whatsapp.net")

    @patch("usuarioSec.whatsapp_views.listar_contatos", return_value={"data": []})
    def test_chat_sem_nome_exibe_jid_com_numero_real(self, _listar_contatos_mock):
        chat = _enriquecer_chats([{
            "jid": "5538999990000@s.whatsapp.net",
            "name": None,
            "notify": "",
        }])[0]

        self.assertEqual(chat["name"], "")
        self.assertEqual(chat["phoneJid"], "5538999990000@s.whatsapp.net")

    @patch("usuarioSec.whatsapp_views.listar_contatos", return_value={"data": []})
    def test_nome_generico_nao_substitui_numero_de_contato(self, _listar_contatos_mock):
        chat = _enriquecer_chats([{
            "jid": "5538999990000@s.whatsapp.net",
            "name": "Contato WhatsApp",
            "notify": "WhatsApp",
        }])[0]

        self.assertEqual(chat["name"], "")
        self.assertEqual(chat["phoneJid"], "5538999990000@s.whatsapp.net")

    @patch("usuarioSec.whatsapp_views.listar_contatos", return_value={"data": []})
    def test_lid_sem_numero_nao_e_apresentado_como_telefone(self, _listar_contatos_mock):
        chat = _enriquecer_chats([{
            "jid": "184774392074394@lid",
            "name": None,
        }])[0]

        self.assertEqual(chat["phoneJid"], "")
        self.assertEqual(chat["name"], "")

    @patch("usuarioSec.whatsapp_views.listar_contatos")
    def test_lid_sem_telefone_exibe_apelido_quando_disponivel(self, listar_contatos_mock):
        listar_contatos_mock.return_value = {"data": [{
            "jid": "184774392074394@lid",
            "notify": "Responsável pela turma",
        }]}
        chat = _enriquecer_chats([{"jid": "184774392074394@lid"}])[0]
        self.assertEqual(chat["phoneJid"], "")
        self.assertEqual(chat["name"], "Responsável pela turma")

    @patch("usuarioSec.whatsapp_views.listar_contatos")
    def test_lid_recupera_telefone_quando_disponivel_em_data(self, listar_contatos_mock):
        listar_contatos_mock.return_value = {"data": [{
            "jid": "184774392074394@lid",
            "lid": "184774392074394@lid",
            "data": {"id": "5538999990000@s.whatsapp.net"},
        }]}
        chat = _enriquecer_chats([{"jid": "184774392074394@lid"}])[0]
        self.assertEqual(chat["phoneJid"], "5538999990000@s.whatsapp.net")

    @patch("usuarioSec.whatsapp_views.listar_contatos")
    def test_pushname_igual_ao_nome_nao_substitui_numero_nao_salvo(self, listar_contatos_mock):
        listar_contatos_mock.return_value = {"data": [{
            "jid": "5538999990000@s.whatsapp.net",
            "name": "Nome de perfil",
            "notify": "Nome de perfil",
        }]}
        chat = _enriquecer_chats([{"jid": "5538999990000@s.whatsapp.net"}])[0]
        self.assertEqual(chat["phoneJid"], "5538999990000@s.whatsapp.net")
        self.assertEqual(chat["name"], "")

    @patch("usuarioSec.whatsapp_views.listar_contatos")
    def test_nome_salvo_diferente_do_apelido_e_preservado(self, listar_contatos_mock):
        listar_contatos_mock.return_value = {"data": [{
            "jid": "5538999990000@s.whatsapp.net",
            "name": "Responsável cadastrado",
            "notify": "Apelido WhatsApp",
        }]}
        chat = _enriquecer_chats([{"jid": "5538999990000@s.whatsapp.net"}])[0]
        self.assertEqual(chat["name"], "Responsável cadastrado")

    @patch("usuarioSec.whatsapp_views.obter_foto_perfil")
    def test_api_foto_retorna_url_de_perfil(self, obter_foto_mock):
        obter_foto_mock.return_value = {
            "success": True,
            "profilePicUrl": "https://example.invalid/foto-real.jpg",
        }

        response = self.client.post(
            reverse("whatsapp_foto_api"),
            {"jid": "5538999990000@s.whatsapp.net"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(
            response.json()["url"],
            "https://example.invalid/foto-real.jpg",
        )

    @patch("usuarioSec.whatsapp_views.marcar_chat_como_lido")
    @patch("usuarioSec.whatsapp_views.obter_mensagens_chat")
    def test_api_carrega_mensagens_e_marca_como_lidas(
        self,
        obter_mensagens_mock,
        marcar_lido_mock,
    ):
        jid = "5538999990000@s.whatsapp.net"
        obter_mensagens_mock.return_value = {
            "status": True,
            "data": [
                {
                    "keyId": "msg-sintetica-1",
                    "fromMe": False,
                    "content": "Preciso de uma informação.",
                    "type": "TEXT",
                    "timestamp": "2026-10-17T01:00:00.000Z",
                }
            ],
        }

        response = self.client.get(reverse("whatsapp_chat_api"), {"jid": jid})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(
            response.json()["mensagens"][0]["content"],
            "Preciso de uma informação.",
        )
        marcar_lido_mock.assert_called_once_with(jid)

    @patch("usuarioSec.whatsapp_views.enviar_mensagem_chat")
    def test_api_responde_conversa(self, enviar_mock):
        enviar_mock.return_value = {
            "status": True,
            "data": {"key": {"id": "msg-sintetica-2"}},
        }

        response = self.client.post(
            reverse("whatsapp_responder_api"),
            {
                "jid": "5538999990000@s.whatsapp.net",
                "mensagem": "Resposta da secretaria.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        enviar_mock.assert_called_once_with(
            "5538999990000@s.whatsapp.net",
            "Resposta da secretaria.",
        )

    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False)
    def test_tela_envios_exibe_botao_conectar_mesmo_sem_configuracao(self, _configurado):
        response = self.client.get(reverse("whatsapp"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Conectar WhatsApp")


class WhatsAppAtendimentoCompletoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="whatsapp_atendimento_completo",
            password="Senha-Sintetica-2026!",
        )
        autorizar_operador_whatsapp_teste(self.usuario)
        self.client.force_login(self.usuario)

    @patch("usuarioSec.whatsapp_views.listar_contatos")
    def test_busca_contatos_do_whatsapp_por_nome(self, listar_mock):
        listar_mock.return_value = {
            "data": [
                {
                    "jid": "5538999991111@s.whatsapp.net",
                    "name": "Responsável Teste",
                    "notify": "Responsável Teste",
                }
            ]
        }

        response = self.client.get(
            reverse("whatsapp_buscar_contatos_wa"),
            {"q": "Responsável"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["nome"], "Responsável Teste")
        self.assertEqual(
            response.json()["results"][0]["jid"],
            "5538999991111@s.whatsapp.net",
        )

    @patch("usuarioSec.whatsapp_views.enviar_mensagem_chat")
    @patch("usuarioSec.whatsapp_views.verificar_numeros")
    def test_nova_conversa_valida_numero_e_envia_direto(
        self,
        verificar_mock,
        enviar_mock,
    ):
        verificar_mock.return_value = {
            "data": {
                "results": [
                    {
                        "number": "5538999991111",
                        "exists": True,
                        "jid": "5538999991111@s.whatsapp.net",
                    }
                ]
            }
        }
        enviar_mock.return_value = {"status": True}

        response = self.client.post(
            reverse("whatsapp_nova_conversa_api"),
            {
                "numero": "(38) 99999-1111",
                "mensagem": "Mensagem de teste.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        enviar_mock.assert_called_once_with(
            "5538999991111@s.whatsapp.net",
            "Mensagem de teste.",
        )

    @patch("usuarioSec.whatsapp_views.gerenciar_chat")
    def test_gerenciamento_de_conversa(self, gerenciar_mock):
        gerenciar_mock.return_value = {"success": True}

        response = self.client.post(
            reverse("whatsapp_gerenciar_chat_api"),
            {
                "jid": "5538999991111@s.whatsapp.net",
                "acao": "archive",
                "ativo": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        gerenciar_mock.assert_called_once_with(
            "5538999991111@s.whatsapp.net",
            "archive",
            True,
        )



class WhatsAppAliasMidiaTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="whatsapp_alias_midia",
            password="Senha-Sintetica-2026!",
        )
        autorizar_operador_whatsapp_teste(self.usuario)
        self.client.force_login(self.usuario)

    @patch("usuarioSec.whatsapp_views.listar_contatos")
    @patch("usuarioSec.whatsapp_views.obter_mensagens_chat")
    @patch("usuarioSec.whatsapp_views.marcar_chat_como_lido")
    def test_chat_busca_mensagens_em_todos_os_aliases(
        self,
        marcar_lido_mock,
        obter_mensagens_mock,
        listar_contatos_mock,
    ):
        listar_contatos_mock.return_value = {
            "data": [{
                "jid": "123456789012345@lid",
                "lid": "123456789012345@lid",
                "remoteJidAlt": "5538999990000@s.whatsapp.net",
                "name": "Responsável Alias",
            }]
        }

        def mensagens_por_alias(jid):
            if jid.endswith("@lid"):
                return {"data": []}
            return {
                "data": [{
                    "keyId": "msg-real-1",
                    "fromMe": False,
                    "pushName": "Responsável Alias",
                    "content": "Mensagem encontrada pelo número real.",
                    "timestamp": "2026-10-17T03:00:00.000Z",
                }]
            }

        obter_mensagens_mock.side_effect = mensagens_por_alias

        response = self.client.get(
            reverse("whatsapp_chat_api"),
            {"jid": "123456789012345@lid"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(
            response.json()["mensagens"][0]["content"],
            "Mensagem encontrada pelo número real.",
        )
        self.assertEqual(response.json()["nome"], "Responsável Alias")

    @patch("usuarioSec.whatsapp_views.enviar_midia")
    def test_envio_de_imagem_pela_conversa(self, enviar_midia_mock):
        enviar_midia_mock.return_value = {"status": True}
        arquivo = SimpleUploadedFile(
            "foto.jpg",
            b"imagem-sintetica",
            content_type="image/jpeg",
        )

        response = self.client.post(
            reverse("whatsapp_enviar_midia_api"),
            {
                "jid": "5538999990000@s.whatsapp.net",
                "legenda": "Foto da atividade",
                "arquivo": arquivo,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["tipo"], "image")
        enviar_midia_mock.assert_called_once()



class WhatsAppRecursosAvancadosTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="whatsapp_recursos_avancados",
            password="Senha-Sintetica-2026!",
        )
        autorizar_operador_whatsapp_teste(self.usuario)
        self.client.force_login(self.usuario)

    @patch("usuarioSec.whatsapp_views.obter_config_sistema")
    @patch("usuarioSec.whatsapp_views.listar_grupos")
    @patch("usuarioSec.whatsapp_views.listar_agendamentos")
    @patch("usuarioSec.whatsapp_views.listar_respostas_automaticas")
    @patch("usuarioSec.whatsapp_views.listar_etiquetas")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_painel_gerenciamento_carrega_recursos(
        self,
        _configurado,
        etiquetas_mock,
        auto_mock,
        agendamentos_mock,
        grupos_mock,
        config_mock,
    ):
        etiquetas_mock.return_value = {
            "data": {"labels": [{"id": "l1", "name": "Urgente", "colorHex": "#ff0000"}]}
        }
        auto_mock.return_value = {
            "data": [{"id": "r1", "keyword": "horario", "response": "Atendimento às 7h."}]
        }
        agendamentos_mock.side_effect = [
            {"data": [{"id": "s1", "jid": "5538999990000@s.whatsapp.net", "content": "Lembrete"}]},
            {"data": []},
        ]
        grupos_mock.return_value = {
            "data": [{"id": "g1", "subject": "Responsáveis 5º Ano", "size": 20}]
        }
        config_mock.return_value = {"data": {"timezone": "America/Sao_Paulo"}}

        response = self.client.get(reverse("whatsapp_gerenciamento"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gerenciamento do WhatsApp")
        self.assertContains(response, "Urgente")
        self.assertContains(response, "Responsáveis 5º Ano")
        self.assertContains(response, "Respostas automáticas")
        self.assertContains(response, "Mensagens agendadas")

    @patch("usuarioSec.whatsapp_views.responder_mensagem_citada")
    def test_resposta_citada(self, responder_mock):
        responder_mock.return_value = {"status": True}

        response = self.client.post(
            reverse("whatsapp_acao_mensagem_api"),
            {
                "jid": "5538999990000@s.whatsapp.net",
                "message_id": "msg-1",
                "acao": "reply",
                "texto": "Resposta citada.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        responder_mock.assert_called_once_with(
            "5538999990000@s.whatsapp.net",
            "msg-1",
            "Resposta citada.",
        )

    @patch("usuarioSec.whatsapp_views.reagir_mensagem")
    def test_reacao_em_mensagem(self, reagir_mock):
        reagir_mock.return_value = {"success": True}

        response = self.client.post(
            reverse("whatsapp_acao_mensagem_api"),
            {
                "jid": "5538999990000@s.whatsapp.net",
                "message_id": "msg-2",
                "acao": "react",
                "emoji": "👍",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        reagir_mock.assert_called_once_with(
            "5538999990000@s.whatsapp.net",
            "msg-2",
            "👍",
        )

    @patch("usuarioSec.whatsapp_views.baixar_midia_mensagem")
    def test_proxy_midia_recebida_exige_login_e_entrega_imagem(self, baixar_mock):
        baixar_mock.return_value = (
            b"imagem-sintetica",
            "image/jpeg",
            'attachment; filename="foto.jpg"',
        )

        response = self.client.get(
            reverse("whatsapp_midia_recebida", args=["db-message-id"])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertEqual(response["Content-Disposition"], "inline")
        self.assertEqual(response.content, b"imagem-sintetica")

    @patch("usuarioSec.whatsapp_views.salvar_config_sistema")
    def test_configuracao_fuso_horario(self, salvar_mock):
        salvar_mock.return_value = {"status": True}

        response = self.client.post(
            reverse("whatsapp_gerenciamento"),
            {
                "acao": "configurar_sistema",
                "timezone": "America/Sao_Paulo",
            },
        )

        self.assertEqual(response.status_code, 302)
        salvar_mock.assert_called_once_with(
            "EMECA WhatsApp",
            "",
            "/favicon.ico",
            "America/Sao_Paulo",
            False,
        )

    def test_tela_mensagens_exibe_anexo_e_acoes_avancadas(self):
        with patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False):
            response = self.client.get(reverse("whatsapp_mensagens"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="attachButton"')
        self.assertContains(response, 'id="labelsButton"')
        self.assertContains(response, 'id="messageSearchButton"')
        self.assertContains(response, "Gerenciamento", count=1)


class WhatsAppIdentidadeNotificacoesTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="teste_notificacoes_whatsapp",
            password="Senha-Sintetica-2026!",
        )
        autorizar_operador_whatsapp_teste(self.usuario)
        self.client.force_login(self.usuario)
        self.lid = "184774392074394@lid"
        self.telefone = "5538999990000@s.whatsapp.net"

    @patch("usuarioSec.whatsapp_views.listar_contatos")
    def test_lid_e_telefone_aparecem_uma_vez_e_preservam_aliases(self, listar):
        listar.return_value = {"data": [{
            "jid": self.lid, "lid": self.lid,
            "remoteJidAlt": self.telefone, "name": "Pessoa da comunidade"
        }]}
        chats = _enriquecer_chats([
            {"jid": self.lid, "lastMessage": {
                "content": "Primeira mensagem", "timestamp": "2026-10-17T12:00:00Z"
            }},
            {"jid": self.telefone, "lastMessage": {
                "content": "Mensagem mais recente", "timestamp": "2026-10-17T12:01:00Z"
            }},
        ])
        self.assertEqual(len(chats), 1)
        self.assertEqual(chats[0]["jid"], self.telefone)
        self.assertEqual(chats[0]["lastMessage"]["content"], "Mensagem mais recente")
        self.assertIn(self.lid, chats[0]["aliases"])
        self.assertIn(self.telefone, chats[0]["aliases"])

    @patch("usuarioSec.whatsapp_views.listar_contatos")
    def test_igualdade_de_foto_ou_nome_nao_funde_contatos(self, listar):
        listar.return_value = {"data": [
            {"jid": self.lid, "name": "Mesmo nome", "profilePic": "https://example.invalid/a.jpg"},
            {"jid": self.telefone, "name": "Mesmo nome", "profilePic": "https://example.invalid/a.jpg"},
        ]}
        chats = _enriquecer_chats([
            {"jid": self.lid, "lastMessage": {"timestamp": "2026-10-17T12:00:00Z"}},
            {"jid": self.telefone, "lastMessage": {"timestamp": "2026-10-17T12:01:00Z"}},
        ])
        self.assertEqual(len(chats), 2)

    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    @patch("usuarioSec.whatsapp_views._mensagens_para_contar")
    @patch("usuarioSec.whatsapp_views.listar_contatos", return_value={"data": []})
    def test_lid_recupera_telefone_e_nome_do_historico(self, _contatos, mensagens, _gateway):
        cache.clear()
        mensagens.return_value = ([{
            "keyId": "mensagem-real-1",
            "timestamp": "2026-10-17T12:00:00Z",
            "fromMe": False,
            "type": "TEXT",
            "content": "Olá",
            "senderJid": self.telefone,
            "pushName": "Pessoa identificada",
        }], True)
        chats = _enriquecer_chats([
            {"jid": self.lid, "lastMessage": {"timestamp": "2026-10-17T12:00:00Z"}},
            {"jid": self.telefone, "lastMessage": {"timestamp": "2026-10-17T12:01:00Z"}},
        ])
        self.assertEqual(len(chats), 1)
        self.assertEqual(chats[0]["phoneJid"], self.telefone)
        self.assertIn(self.lid, _aliases_contato_wa(self.telefone, []))
        mensagens.assert_called_once_with([self.lid])
        cache.clear()

    def test_aliases_apos_ligacao_transitiva(self):
        contatos = [
            {"jid": self.lid, "lid": self.lid, "remoteJidAlt": "5538999991111@s.whatsapp.net"},
            {"jid": "5538999991111@s.whatsapp.net", "remoteJidAlt": self.telefone},
        ]
        aliases = _aliases_contato_wa(self.lid, contatos)
        self.assertIn(self.telefone, aliases)

    @patch("usuarioSec.whatsapp_views.obter_mensagens_chat")
    def test_somente_recebidas_novas_entram_no_contador(self, carregar):
        inicio = [{"jid": self.telefone, "aliases": [self.telefone], "lastMessage": {
            "timestamp": "2026-10-17T12:00:00Z", "type": "TEXT", "content": "oi"
        }}]
        _sincronizar_nao_lidas(self.usuario, inicio)
        self.assertEqual(inicio[0]["naoLidas"], 0)
        carregar.return_value = {"data": [
            {"keyId": "antes", "timestamp": "2026-10-17T12:00:00Z", "fromMe": False, "type": "TEXT", "content": "oi"},
            {"keyId": "nova-1", "timestamp": "2026-10-17T12:01:00Z", "fromMe": False, "type": "TEXT", "content": "olá"},
            {"keyId": "nova-2", "timestamp": "2026-10-17T12:02:00Z", "fromMe": True, "type": "TEXT", "content": "resposta"},
            {"keyId": "sistema", "timestamp": "2026-10-17T12:02:30Z", "fromMe": False, "type": "TEXT", "content": ""},
        ]}
        atualizado = [{"jid": self.telefone, "aliases": [self.telefone], "lastMessage": {
            "timestamp": "2026-10-17T12:03:00Z", "type": "TEXT", "content": "mensagem técnica"
        }}]
        _sincronizar_nao_lidas(self.usuario, atualizado)
        self.assertEqual(atualizado[0]["naoLidas"], 1)
        _sincronizar_nao_lidas(self.usuario, atualizado)
        self.assertEqual(atualizado[0]["naoLidas"], 1)

    @patch("usuarioSec.whatsapp_views.listar_contatos", return_value={"data": []})
    @patch("usuarioSec.whatsapp_views.obter_mensagens_chat")
    @patch("usuarioSec.whatsapp_views.marcar_chat_como_lido")
    def test_abrir_chat_limpa_alerta_local(self, marcar, carregar, _contatos):
        from .sessao_whatsapp import sessao_atual_id
        estado = LeituraChatWhatsApp.objects.create(
            usuario=self.usuario, sessao=sessao_atual_id(),
            jid=self.telefone, nao_lidas=3,
        )
        carregar.return_value = {"data": [{
            "keyId": "msg-1", "timestamp": "2026-10-17T12:30:00Z",
            "fromMe": False, "content": "Tudo bem?", "type": "TEXT"
        }]}
        response = self.client.get(reverse("whatsapp_chat_api"), {"jid": self.telefone})
        self.assertEqual(response.status_code, 200)
        estado.refresh_from_db()
        self.assertEqual(estado.nao_lidas, 0)
        self.assertIsNotNone(estado.ultima_verificacao_em)
        marcar.assert_called_once_with(self.telefone)


class WhatsAppIdentificacaoManualTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="operador_identificacao",
            password="Senha-Sintetica-2026!",
        )
        autorizar_operador_whatsapp_teste(self.usuario)
        self.client.force_login(self.usuario)
        self.lid = "184774392074394@lid"
        self.telefone = "5538999990000@s.whatsapp.net"

    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False)
    @patch("usuarioSec.whatsapp_views.listar_contatos", return_value={"data": []})
    def test_identidade_manual_persiste_e_une_lid_com_telefone(self, _contatos, _gateway):
        raw = [
            {"jid": self.lid, "lastMessage": {"timestamp": "2026-10-17T09:00:00Z"}},
            {"jid": self.telefone, "lastMessage": {"timestamp": "2026-10-17T10:00:00Z"}},
        ]
        self.assertEqual(len(_enriquecer_chats(raw)), 2)
        with patch("usuarioSec.whatsapp_views.listar_chats", return_value={"data": raw}):
            response = self.client.post(
                reverse("whatsapp_identificar_contato_api"),
                {"jid": self.lid, "telefone_jid": self.telefone, "nome": "Responsável confirmado"},
            )
        self.assertEqual(response.status_code, 200, response.content)
        entidade = IdentidadeContatoWhatsApp.objects.get(jid=self.lid)
        self.assertEqual(entidade.origem, "MANUAL")
        self.assertEqual(entidade.telefone_jid, self.telefone)
        junto = _enriquecer_chats(raw)
        self.assertEqual(len(junto), 1)
        self.assertEqual(junto[0]["name"], "Responsável confirmado")
        self.assertIn(self.lid, junto[0]["aliases"])
        self.assertIn(self.telefone, _aliases_contato_wa(self.lid, []))

    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False)
    @patch("usuarioSec.whatsapp_views.listar_contatos", return_value={"data": []})
    def test_desfazer_vinculo_restaura_conversas_independentes(self, _contatos, _gateway):
        IdentidadeContatoWhatsApp.objects.create(
            sessao=settings.WA_AKG_SESSION_ID, jid=self.lid,
            telefone_jid=self.telefone, nome_exibicao="Responsável confirmado",
        )
        raw = [{"jid": self.lid}, {"jid": self.telefone}]
        self.assertEqual(len(_enriquecer_chats(raw)), 1)
        with patch("usuarioSec.whatsapp_views.listar_chats", return_value={"data": raw}):
            response = self.client.post(
                reverse("whatsapp_identificar_contato_api"),
                {"jid": self.lid, "telefone_jid": "", "nome": ""},
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(IdentidadeContatoWhatsApp.objects.filter(jid=self.lid).exists())
        self.assertEqual(len(_enriquecer_chats(raw)), 2)

    @patch("usuarioSec.whatsapp_views.listar_chats")
    def test_nao_permita_unir_numero_nao_listado(self, listar):
        listar.return_value = {"data": [{"jid": self.lid}]}
        resposta = self.client.post(
            reverse("whatsapp_identificar_contato_api"),
            {"jid": self.lid, "telefone_jid": self.telefone, "nome": "Pessoa"},
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(IdentidadeContatoWhatsApp.objects.exists())

    @patch("usuarioSec.whatsapp_views.listar_chats")
    def test_nao_confunde_digitos_do_lid_com_telefone(self, listar):
        listar.return_value = {"data": [{"jid": self.lid}]}
        resposta = self.client.post(
            reverse("whatsapp_identificar_contato_api"),
            {"jid": self.lid, "telefone_jid": self.lid, "nome": ""},
        )
        self.assertEqual(resposta.status_code, 400)

    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False)
    @patch("usuarioSec.whatsapp_views.listar_contatos", return_value={"data": []})
    def test_apelido_manual_aparece_sem_precisar_vincular_numero(self, _contatos, _gateway):
        IdentidadeContatoWhatsApp.objects.create(
            sessao=settings.WA_AKG_SESSION_ID,
            jid=self.lid, nome_exibicao="Mãe da turma", origem="MANUAL",
        )
        data = _enriquecer_chats([{"jid": self.lid}])
        self.assertEqual(data[0]["name"], "Mãe da turma")
        self.assertEqual(data[0]["phoneJid"], "")


    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False)
    @patch("usuarioSec.whatsapp_views.listar_contatos", return_value={"data": []})
    def test_metadados_persistem_sem_cache_de_worker(self, _contatos, _gateway):
        IdentidadeContatoWhatsApp.objects.create(
            sessao=settings.WA_AKG_SESSION_ID,
            jid=self.lid,
            telefone_jid=self.telefone,
            nome_exibicao="Nome de perfil WhatsApp",
            origem="METADATA",
        )
        cache.clear()
        chats = _enriquecer_chats([
            {"jid": self.lid, "lastMessage": {"timestamp": "2026-10-17T09:00:00Z"}},
            {"jid": self.telefone, "lastMessage": {"timestamp": "2026-10-17T10:00:00Z"}},
        ])
        self.assertEqual(len(chats), 1)
        self.assertEqual(chats[0]["jid"], self.telefone)
        self.assertIn(self.lid, _aliases_contato_wa(self.telefone, []))
        self.assertEqual(chats[0]["phoneJid"], self.telefone)


class WhatsAppMetadadosAlternativosTests(TestCase):
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False)
    @patch("usuarioSec.whatsapp_views.listar_contatos")
    def test_nome_recuperado_de_metadados_internos_wa_akg(self, listar, _gateway):
        listar.return_value = {"data": [{
            "jid": "184774392074394@lid",
            "name": None,
            "notify": None,
            "data": {"pushName": "Maria do WhatsApp"},
        }]}
        chats = _enriquecer_chats([{"jid": "184774392074394@lid"}])
        self.assertEqual(len(chats), 1)
        self.assertEqual(chats[0]["name"], "Maria do WhatsApp")
        self.assertFalse(chats[0]["phoneJid"])

    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False)
    @patch("usuarioSec.whatsapp_views.listar_contatos")
    def test_telefone_recuperado_de_pn_jid_explicito_wa_akg(self, listar, _gateway):
        listar.return_value = {"data": [{
            "jid": "184774392074394@lid",
            "data": {"pnJid": "5538999990000@s.whatsapp.net"},
        }]}
        chats = _enriquecer_chats([{"jid": "184774392074394@lid"}])
        self.assertEqual(chats[0]["phoneJid"], "5538999990000@s.whatsapp.net")

    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False)
    @patch("usuarioSec.whatsapp_views.listar_contatos")
    def test_metadado_sem_nome_nao_inventa_numero(self, listar, _gateway):
        listar.return_value = {"data": [{
            "jid": "184774392074394@lid",
            "data": {},
        }]}
        chats = _enriquecer_chats([{"jid": "184774392074394@lid"}])
        self.assertEqual(chats[0]["name"], "")
        self.assertEqual(chats[0]["phoneJid"], "")


class WhatsAppGatewayPaginacaoTests(TestCase):
    @patch("usuarioSec.whatsapp_gateway.settings.WA_AKG_SESSION_ID", "sessao-educacao")
    @patch("usuarioSec.whatsapp_gateway._request")
    def test_gateway_percorre_paginas_sem_perder_conversas(self, requisicao):
        from .whatsapp_gateway import listar_chats
        requisicao.side_effect = [
            {
                "status": True,
                "data": [{"jid": "5511999990001@s.whatsapp.net",
                          "lastMessage": {"timestamp": "2026-10-17T12:00:00Z"}}],
                "meta": {"nextBefore": "2026-10-17T12:00:00Z"},
            },
            {
                "status": True,
                "data": [{"jid": "5511999990002@s.whatsapp.net",
                          "lastMessage": {"timestamp": "2026-10-17T11:00:00Z"}}],
                "meta": {"nextBefore": "2026-10-17T11:00:00Z"},
            },
            {"status": True, "data": [], "meta": {"nextBefore": None}},
        ]
        data = listar_chats()
        self.assertEqual(len(data["data"]), 2)
        self.assertEqual(requisicao.call_count, 3)
        self.assertIn("limit=500", requisicao.call_args_list[0].args[1])
        self.assertIn("before=", requisicao.call_args_list[1].args[1])

    @patch("usuarioSec.whatsapp_gateway.settings.WA_AKG_SESSION_ID", "sessao-educacao")
    @patch("usuarioSec.whatsapp_gateway._request")
    def test_gateway_compatibilidade_com_api_antiga(self, requisicao):
        from .whatsapp_gateway import listar_chats
        requisicao.return_value = {
            "status": True,
            "data": [{"jid": "5511999990001@s.whatsapp.net"}],
        }
        resposta = listar_chats()
        self.assertEqual(len(resposta["data"]), 1)
        requisicao.assert_called_once()

    @patch("usuarioSec.whatsapp_gateway.settings.WA_AKG_SESSION_ID", "sessao-educacao")
    @patch("usuarioSec.whatsapp_gateway._request")
    def test_gateway_impede_loop_de_cursor_repetido(self, requisicao):
        from .whatsapp_gateway import listar_chats
        requisicao.return_value = {
            "status": True,
            "data": [{"jid": "5511999990001@s.whatsapp.net"}],
            "meta": {"nextBefore": "2026-10-17T12:00:00Z"},
        }
        resposta = listar_chats()
        self.assertEqual(len(resposta["data"]), 1)
        self.assertLessEqual(requisicao.call_count, 3)


class WhatsAppVisualizacaoPerfilTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="operador_perfil", password="senha-local-exemplo"
        )
        autorizar_operador_whatsapp_teste(self.usuario)
        self.client.force_login(self.usuario)

    @patch("usuarioSec.whatsapp_views.obter_perfil_contato")
    @patch("usuarioSec.whatsapp_views.listar_contatos")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_perfil_exibe_nome_numero_sobre_e_foto_disponivel(
        self, _config, contatos_mock, perfil_mock
    ):
        contatos_mock.return_value = {"data": [{
            "jid": "5538999991234@s.whatsapp.net",
            "name": "Maria Teste",
            "notify": "Maria",
            "profilePic": "https://example.invalid/foto.jpg",
        }]}
        perfil_mock.return_value = {
            "status": True, "data": {"about": "Atendimento disponível"}
        }
        response = self.client.get(reverse("whatsapp_perfil_api"), {
            "jid": "5538999991234@s.whatsapp.net"
        })
        self.assertEqual(response.status_code, 200)
        perfil = response.json()["perfil"]
        self.assertEqual(perfil["nome"], "Maria Teste")
        self.assertEqual(perfil["telefoneJid"], "5538999991234@s.whatsapp.net")
        self.assertEqual(perfil["sobre"], "Atendimento disponível")
        self.assertTrue(perfil["fotoDisponivel"])

    @patch("usuarioSec.whatsapp_views.obter_perfil_contato")
    @patch("usuarioSec.whatsapp_views.listar_contatos", return_value={"data": []})
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_lid_nao_aparece_como_numero_real(self, _gateway, _contatos, perfil_mock):
        perfil_mock.return_value = {"status": True, "data": {"about": None}}
        response = self.client.get(reverse("whatsapp_perfil_api"), {
            "jid": "184774392074394@lid"
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["perfil"]["telefoneJid"], "")
        self.assertEqual(response.json()["perfil"]["nome"], "Contato sem identificação")

    def test_perfil_exige_login(self):
        self.client.logout()
        response = self.client.get(reverse("whatsapp_perfil_api"), {
            "jid": "5538999991234@s.whatsapp.net"
        })
        self.assertEqual(response.status_code, 302)

    def test_perfil_rejeita_identificadores_invalidos(self):
        response = self.client.get(reverse("whatsapp_perfil_api"), {
            "jid": "https://example.invalid"
        })
        self.assertEqual(response.status_code, 400)

    def test_dialogs_foto_e_perfil_aparecem_na_tela(self):
        with patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False):
            response = self.client.get(reverse("whatsapp_mensagens"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="contactPhotoDialog"')
        self.assertContains(response, 'id="contactProfileDialog"')
        self.assertContains(response, 'id="viewContactProfile"')
        self.assertContains(response, reverse("whatsapp_perfil_api"))


class WhatsAppDesconexaoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="administrador_desconexao_wa",
            password="SenhaDeTeste-local",
            is_staff=True,
            is_superuser=True,
        )
        autorizar_operador_whatsapp_teste(self.usuario)
        self.client.force_login(self.usuario)
        self.url = reverse("whatsapp_desconectar")

    @patch("usuarioSec.whatsapp_views.pausar_sessao", return_value={"status": True})
    @patch("usuarioSec.whatsapp_views.obter_sessao",
           return_value={"data": {"status": "CONNECTED"}})
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_pausar_sem_apagar_sessao(self, _config, _sessao, pausar):
        result = self.client.post(self.url, {"acao": "pausar"})
        self.assertRedirects(result, reverse("whatsapp"), fetch_redirect_response=False)
        pausar.assert_called_once_with()

    @patch("usuarioSec.whatsapp_views.excluir_historico_sessao",
           return_value={"status": True, "data": {"messages": 12, "mediaErrors": 0}})
    @patch("usuarioSec.whatsapp_views.desvincular_sessao", return_value={"status": True})
    @patch("usuarioSec.whatsapp_views.obter_sessao",
           return_value={"data": {"status": "CONNECTED"}})
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_desvinculacao_confirmada(self, _config, _sessao, desvincular, limpar):
        from .sessao_whatsapp import sessao_atual_id
        sessao_anterior = sessao_atual_id()
        result = self.client.post(self.url, {
            "acao": "desvincular", "confirmacao": "DESVINCULAR",
            "confirmar_exclusao": "APAGAR_HISTORICO",
            "origem": "mensagens",
        })
        self.assertRedirects(
            result, reverse("whatsapp_mensagens"), fetch_redirect_response=False
        )
        desvincular.assert_called_once_with()
        limpar.assert_called_once_with(sessao_anterior)
        self.assertNotEqual(sessao_atual_id(), sessao_anterior)

    @patch("usuarioSec.whatsapp_views.desvincular_sessao")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_nao_desvincula_sem_confirmacao(self, _config, desvincular):
        result = self.client.post(self.url, {"acao": "desvincular"})
        self.assertEqual(result.status_code, 302)
        desvincular.assert_not_called()

    @patch("usuarioSec.whatsapp_views.desvincular_sessao")
    @patch("usuarioSec.whatsapp_views.obter_sessao",
           return_value={"data": {"status": "STOPPED"}})
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_nao_confunde_status_offline_com_logout_real(
        self, _config, _sessao, desvincular
    ):
        result = self.client.post(self.url, {
            "acao": "desvincular", "confirmacao": "DESVINCULAR",
            "confirmar_exclusao": "APAGAR_HISTORICO",
        })
        self.assertEqual(result.status_code, 302)
        desvincular.assert_not_called()

    @patch("usuarioSec.whatsapp_views.pausar_sessao")
    @patch("usuarioSec.whatsapp_views.desvincular_sessao")
    def test_usuario_comum_nao_pode_desconectar(self, desvincular, pausar):
        comum = get_user_model().objects.create_user(username="colaborador_sem_permissao")
        # Pode entrar no módulo WhatsApp, mas NÃO é administrador.
        # Testa a autorização da própria operação destrutiva.
        autorizar_operador_whatsapp_teste(comum)
        self.client.force_login(comum)
        resposta = self.client.post(self.url, {
            "acao": "desvincular", "confirmacao": "DESVINCULAR"
        })
        self.assertEqual(resposta.status_code, 403)
        desvincular.assert_not_called()
        pausar.assert_not_called()

    def test_desconexao_usa_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    @patch("usuarioSec.whatsapp_views.limpeza_historico_pendente")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_falha_migracao_retorna_orientacao_sem_http_500(
        self, _config, pendente
    ):
        from django.db import OperationalError
        pendente.side_effect = OperationalError("no such column: limpeza_pendente")
        resposta = self.client.post(self.url, {"acao": "pausar"})
        self.assertRedirects(resposta, reverse("whatsapp"), fetch_redirect_response=False)
        avisos = [str(item) for item in list(resposta.wsgi_request._messages)]
        self.assertTrue(any("migrações" in aviso.lower() for aviso in avisos))

    @patch("usuarioSec.whatsapp_views.limpeza_historico_pendente")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_erro_inesperado_antes_do_logout_nao_devolve_http_500(
        self, _config, pendente
    ):
        pendente.side_effect = RuntimeError("falha simulada")
        resposta = self.client.post(self.url, {"acao": "pausar"})
        self.assertRedirects(resposta, reverse("whatsapp"), fetch_redirect_response=False)
        avisos = [str(item) for item in list(resposta.wsgi_request._messages)]
        self.assertTrue(any("não foi possível" in aviso.lower() for aviso in avisos))

    @patch("usuarioSec.whatsapp_views.pausar_sessao", return_value={"status": True})
    @patch("usuarioSec.whatsapp_views.obter_sessao",
           return_value={"data": {"status": "CONNECTED"}})
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_administrador_emeca_sem_is_staff_pode_gerenciar(
        self, _config, _sessao, pausar
    ):
        from django.contrib.auth.models import Group
        from .access_control import GRUPO_ADMIN
        admin_grupo = get_user_model().objects.create_user(
            username="grupo_administracao_sem_staff"
        )
        grupo, _ = Group.objects.get_or_create(name=GRUPO_ADMIN)
        admin_grupo.groups.add(grupo)
        self.client.force_login(admin_grupo)
        resposta = self.client.get(reverse("whatsapp"))
        self.assertContains(resposta, "Desvincular número")
        post = self.client.post(self.url, {"acao": "pausar"})
        self.assertEqual(post.status_code, 302)
        pausar.assert_called_once_with()

    @patch("usuarioSec.whatsapp_views.obter_sessao",
           return_value={"data": {"status": "CONNECTED"}})
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_botoes_visiveis_em_tela_de_conexao(self, _config, _sessao):
        resposta = self.client.get(reverse("whatsapp"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Desvincular número")
        self.assertContains(resposta, "Pausar")
        self.assertContains(resposta, "whatsapp/desconectar")


class WhatsAppAcoesCabecalhoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="operador_acoes", password="senha_ficticia"
        )
        autorizar_operador_whatsapp_teste(self.usuario)
        self.client.force_login(self.usuario)
        self.jid = "5538999991234@s.whatsapp.net"

    @patch("usuarioSec.whatsapp_views.gerenciar_chat", return_value={"success": True})
    def test_fixar_e_desafixar_persistem_estado(self, gerenciar):
        from .models import EstadoConversaWhatsApp
        for enabled in ("1", "0"):
            response = self.client.post(reverse("whatsapp_gerenciar_chat_api"), {
                "jid": self.jid, "acao": "pin", "ativo": enabled,
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["ativo"], enabled == "1")
            estado = EstadoConversaWhatsApp.objects.get(jid=self.jid)
            self.assertEqual(estado.fixado, enabled == "1")
        self.assertEqual(gerenciar.call_count, 2)
        self.assertEqual(EstadoConversaWhatsApp.objects.count(), 1)

    @patch("usuarioSec.whatsapp_views.gerenciar_chat", return_value={"success": True})
    def test_arquivar_e_silenciar_separadamente(self, _gerenciar):
        from .models import EstadoConversaWhatsApp
        self.client.post(reverse("whatsapp_gerenciar_chat_api"), {
            "jid": self.jid, "acao": "archive", "ativo": "1",
        })
        self.client.post(reverse("whatsapp_gerenciar_chat_api"), {
            "jid": self.jid, "acao": "mute", "ativo": "1",
        })
        estado = EstadoConversaWhatsApp.objects.get(jid=self.jid)
        self.assertTrue(estado.arquivado)
        self.assertTrue(estado.silenciado)
        self.assertFalse(estado.fixado)

    @patch("usuarioSec.whatsapp_views.gerenciar_chat")
    def test_falha_wa_nao_grava_estado_falso(self, gerenciar):
        from .models import EstadoConversaWhatsApp
        from .whatsapp_gateway import WhatsAppGatewayError
        gerenciar.side_effect = WhatsAppGatewayError("WA-AKG não confirmou pin", 502)
        result = self.client.post(reverse("whatsapp_gerenciar_chat_api"), {
            "jid": self.jid, "acao": "pin", "ativo": "1",
        })
        self.assertEqual(result.status_code, 502)
        self.assertFalse(result.json()["ok"])
        self.assertFalse(EstadoConversaWhatsApp.objects.exists())

    @patch("usuarioSec.whatsapp_gateway._request")
    def test_gateway_rejeita_status_false_mas_aceita_success_true(self, call):
        from .whatsapp_gateway import (
            WhatsAppGatewayError, gerenciar_chat, bloquear_contato
        )
        call.return_value = {"success": True}
        self.assertEqual(gerenciar_chat(self.jid, "pin", True)["success"], True)
        call.return_value = {"status": False, "message": "Falha no servidor"}
        with self.assertRaises(WhatsAppGatewayError):
            bloquear_contato(self.jid, True)

    @patch("usuarioSec.whatsapp_views.bloquear_contato", return_value={"status": True})
    def test_bloqueio_alterna_sem_apagar_mensagens(self, bloqueio):
        from .models import EstadoConversaWhatsApp
        for choice in ("1", "0"):
            response = self.client.post(reverse("whatsapp_bloqueio_api"), {
                "jid": self.jid, "bloquear": choice,
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["bloqueado"], choice == "1")
        self.assertFalse(EstadoConversaWhatsApp.objects.get(jid=self.jid).bloqueado)
        self.assertEqual(bloqueio.call_count, 2)

    @patch("usuarioSec.whatsapp_views.atualizar_etiquetas_chat",
           return_value={"success": True, "labels": [
               {"id": "teste", "name": "Matrícula", "colorHex": "#00FF00"}
           ]})
    @patch("usuarioSec.whatsapp_views.criar_etiqueta",
           return_value={"status": True, "data": {"label": {
               "id": "teste", "name": "Matrícula", "colorHex": "#00FF00"
           }}})
    def test_criar_etiqueta_na_tela_de_mensagens(self, criar, associar):
        from .models import EtiquetaConversaWhatsApp
        response = self.client.post(reverse("whatsapp_etiquetas_criar_api"), {
            "jid": self.jid, "nome": "Matrícula", "cor": "3",
        })
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["etiqueta"]["name"], "Matrícula")
        self.assertEqual(len(response.json()["etiquetas_conversa"]), 1)
        self.assertTrue(EtiquetaConversaWhatsApp.objects.filter(
            jid=self.jid, etiqueta_id="teste"
        ).exists())
        criar.assert_called_once_with("Matrícula", 3)
        associar.assert_called_once_with(self.jid, ["teste"], "add")

    @patch("usuarioSec.whatsapp_views.criar_etiqueta")
    def test_nao_cria_etiqueta_com_nome_vazio(self, criar):
        response = self.client.post(reverse("whatsapp_etiquetas_criar_api"), {
            "nome": "  ", "cor": "0",
        })
        self.assertEqual(response.status_code, 400)
        criar.assert_not_called()

    @patch("usuarioSec.whatsapp_views._mapa_nomes_telefones_escola_wa")
    @patch("usuarioSec.whatsapp_views.listar_contatos", return_value={"data": []})
    def test_muitos_chats_uma_consulta_de_nomes_da_escola(
        self, _contatos, carregar_nomes
    ):
        telefones = [f"5538999{i:06d}@s.whatsapp.net" for i in range(120)]
        carregar_nomes.return_value = {
            jid.split("@")[0]: "Responsável " + str(i)
            for i, jid in enumerate(telefones)
        }
        resultado = _enriquecer_chats([{"jid": jid} for jid in telefones])
        self.assertEqual(len(resultado), 120)
        self.assertEqual(resultado[0]["name"], "Responsável 0")
        carregar_nomes.assert_called_once_with()

    @patch("usuarioSec.whatsapp_views.listar_contatos", return_value={"data": []})
    def test_conversa_fixada_fica_acima_de_conversa_recente(self, _contatos):
        from .models import EstadoConversaWhatsApp
        from .sessao_whatsapp import sessao_atual_id
        primeiro = "5538999991234@s.whatsapp.net"
        novo = "5538999995678@s.whatsapp.net"
        EstadoConversaWhatsApp.objects.create(
            sessao=sessao_atual_id(), jid=primeiro, fixado=True
        )
        chats = _enriquecer_chats([
            {"jid": novo, "lastMessage": {"timestamp": "2026-10-17T15:50:00Z"}},
            {"jid": primeiro, "lastMessage": {"timestamp": "2026-10-17T10:00:00Z"}},
        ])
        self.assertEqual(chats[0]["jid"], primeiro)
        self.assertTrue(chats[0]["fixado"])

    @patch("usuarioSec.whatsapp_views.listar_contatos", return_value={"data": []})
    def test_etiquetas_sao_visiveis_apos_reabrir_lista(self, _contatos):
        from .models import EtiquetaConversaWhatsApp
        from .sessao_whatsapp import sessao_atual_id
        EtiquetaConversaWhatsApp.objects.create(
            sessao=sessao_atual_id(), jid=self.jid,
            etiqueta_id="matriculas", nome="Matrículas", cor="#22c55e",
        )
        chats = _enriquecer_chats([{"jid": self.jid}])
        self.assertEqual(chats[0]["etiquetas"][0]["name"], "Matrículas")

    @patch("usuarioSec.whatsapp_views.atualizar_etiquetas_chat",
           return_value={"success": True, "labels": [
               {"id": "urgente", "name": "Urgente", "colorHex": "#FF0000"}
           ]})
    def test_salvar_etiqueta_apresenta_estado_persistido(self, atualizar):
        from .models import EtiquetaConversaWhatsApp
        response = self.client.post(reverse("whatsapp_etiquetas_atualizar_api"), {
            "jid": self.jid, "action": "add", "label_ids": ["urgente"],
        })
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["etiquetas_conversa"][0]["nome"], "Urgente")
        self.assertTrue(EtiquetaConversaWhatsApp.objects.filter(
            jid=self.jid, etiqueta_id="urgente"
        ).exists())
        atualizar.assert_called_once_with(self.jid, ["urgente"], "add")

    @patch("usuarioSec.whatsapp_views.atualizar_etiquetas_chat")
    def test_erro_atribuicao_nao_cria_etiqueta_local(self, atualizar):
        from .models import EtiquetaConversaWhatsApp
        from .whatsapp_gateway import WhatsAppGatewayError
        atualizar.side_effect = WhatsAppGatewayError("Falha ao aplicar", 502)
        response = self.client.post(reverse("whatsapp_etiquetas_atualizar_api"), {
            "jid": self.jid, "action": "add", "label_ids": ["urgente"],
        })
        self.assertEqual(response.status_code, 502)
        self.assertFalse(EtiquetaConversaWhatsApp.objects.exists())

    @patch("usuarioSec.whatsapp_views.listar_etiquetas_chat",
           return_value={"status": True, "data": {"labels": [
               {"id": "urgente", "name": "Urgente", "colorHex": "#FF0000"}
           ]}})
    @patch("usuarioSec.whatsapp_views.listar_etiquetas",
           return_value={"status": True, "data": {"labels": [
               {"id": "urgente", "name": "Urgente", "colorHex": "#FF0000"}
           ]}})
    def test_consulta_etiquetas_reconcilia_lista_local(self, _geral, _chat):
        from .models import EtiquetaConversaWhatsApp
        response = self.client.get(
            reverse("whatsapp_etiquetas_api"), {"jid": self.jid}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(EtiquetaConversaWhatsApp.objects.filter(
            jid=self.jid, etiqueta_id="urgente"
        ).exists())

    @patch("usuarioSec.whatsapp_views.buscar_mensagens")
    def test_busca_de_conversa_retorna_resultados(self, buscar):
        buscar.return_value = {
            "status": True,
            "data": [{"keyId": "mensagem1", "content": "Matrícula",
                      "timestamp": "2026-10-17T12:00:00Z"}],
            "pagination": {"total": 1, "page": 1},
        }
        response = self.client.get(reverse("whatsapp_buscar_mensagens_api"), {
            "jid": self.jid, "q": "Matrícula"
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["mensagens"]), 1)

    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False)
    def test_interface_tem_botoes_e_busca_explicita(self, _gateway):
        response = self.client.get(reverse("whatsapp_mensagens"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="runMessageSearch"')
        self.assertContains(response, 'id="createChatLabel"')
        self.assertContains(response, 'id="blockContactButton"')
        self.assertContains(response, 'data-chat-action="pin"')
        self.assertContains(response, "const chatElements = new Map()")
        self.assertContains(response, "const canAppend = quiet")
        self.assertContains(response, 'className = "wa-chat-labels"')
        self.assertContains(response, "function setChatCardColor(node, chat)")
        self.assertContains(response, "--wa-chat-selected")
        self.assertContains(response, "tintChatColor(color, hasLabel ? 0.32 : 0.20)")

        self.assertNotContains(response, 'chatList.innerHTML = ""')



class WhatsAppExclusaoMensagemTests(TestCase):
    def setUp(self):
        self.operador = get_user_model().objects.create_user(
            username="operador_exclusao", password="SenhaFicticia-123"
        )
        self.outro = get_user_model().objects.create_user(
            username="operador_diferente", password="SenhaFicticia-123"
        )
        autorizar_operador_whatsapp_teste(self.operador)
        self.client.force_login(self.operador)
        self.jid = "5538999990000@s.whatsapp.net"
        self.message_id = "MENSAGEM_DE_TESTE_01"

    def test_ocultar_mensagem_nao_chama_wa_akg(self):
        from .models import MensagemOcultaWhatsApp
        with patch("usuarioSec.whatsapp_views.apagar_mensagem") as apagar:
            resposta = self.client.post(reverse("whatsapp_acao_mensagem_api"), {
                "jid": self.jid, "message_id": self.message_id,
                "acao": "hide_local", "from_me": "0",
            })
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertTrue(resposta.json()["ok"])
        apagar.assert_not_called()
        self.assertTrue(MensagemOcultaWhatsApp.objects.filter(
            usuario=self.operador, mensagem_id=self.message_id
        ).exists())
        self.assertFalse(MensagemOcultaWhatsApp.objects.filter(
            usuario=self.outro
        ).exists())

    @patch("usuarioSec.whatsapp_views.marcar_chat_como_lido")
    @patch("usuarioSec.whatsapp_views._contatos_wa", return_value=[])
    @patch("usuarioSec.whatsapp_views.obter_mensagens_chat")
    def test_oculta_em_consultas_futuras_somente_para_operador(
        self, buscar, _contatos, _lida
    ):
        buscar.return_value = {"data": [
            {"keyId": self.message_id, "content": "Teste", "fromMe": False},
            {"keyId": "OUTRA_MSG", "content": "Continua aqui", "fromMe": True}
        ]}
        self.client.post(reverse("whatsapp_acao_mensagem_api"), {
            "jid": self.jid, "message_id": self.message_id, "acao": "hide_local"
        })
        resposta = self.client.get(reverse("whatsapp_chat_api"), {
            "jid": self.jid
        })
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertEqual(
            [x["keyId"] for x in resposta.json()["mensagens"]],
            ["OUTRA_MSG"]
        )
        autorizar_operador_whatsapp_teste(self.outro)
        self.client.force_login(self.outro)
        resposta_outro = self.client.get(reverse("whatsapp_chat_api"), {
            "jid": self.jid
        })
        self.assertEqual(len(resposta_outro.json()["mensagens"]), 2)

    @patch("usuarioSec.whatsapp_views._aliases_contato_wa")
    @patch("usuarioSec.whatsapp_views.buscar_mensagens")
    def test_pesquisa_respeita_mensagem_oculta(self, buscar, aliases):
        aliases.return_value = [self.jid]
        buscar.return_value = {
            "status": True,
            "data": [
                {"keyId": self.message_id, "content": "Segredo"},
                {"keyId": "OUTRA", "content": "Visível"},
            ],
            "pagination": {"total": 2}
        }
        self.client.post(reverse("whatsapp_acao_mensagem_api"), {
            "jid": self.jid, "message_id": self.message_id,
            "acao": "hide_local"
        })
        resposta = self.client.get(reverse("whatsapp_buscar_mensagens_api"), {
            "jid": self.jid, "q": "texto"
        })
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertEqual(
            [msg["keyId"] for msg in resposta.json()["mensagens"]], ["OUTRA"]
        )

    @patch("usuarioSec.whatsapp_views._aliases_contato_wa")
    @patch("usuarioSec.whatsapp_views.obter_mensagens_chat")
    @patch("usuarioSec.whatsapp_views.apagar_mensagem")
    def test_apagar_para_todos_valida_remetente_no_servidor(
        self, apagar, historico, aliases
    ):
        from .models import MensagemOcultaWhatsApp
        aliases.return_value = [self.jid]
        historico.return_value = {"data": [{
            "keyId": self.message_id, "fromMe": False
        }]}
        resposta = self.client.post(reverse("whatsapp_acao_mensagem_api"), {
            "jid": self.jid, "message_id": self.message_id,
            "acao": "delete", "from_me": "1"
        })
        self.assertEqual(resposta.status_code, 400)
        apagar.assert_not_called()
        self.assertFalse(MensagemOcultaWhatsApp.objects.exists())

    @patch("usuarioSec.whatsapp_views._aliases_contato_wa")
    @patch("usuarioSec.whatsapp_views.obter_mensagens_chat")
    @patch("usuarioSec.whatsapp_views.apagar_mensagem",
           return_value={"status": True})
    def test_apagar_para_todos_so_oculta_apos_confirmacao_wa(
        self, apagar, historico, aliases
    ):
        from .models import MensagemOcultaWhatsApp
        aliases.return_value = [self.jid]
        historico.return_value = {"data": [{
            "keyId": self.message_id, "fromMe": True,
            "remoteJid": self.jid
        }]}
        resposta = self.client.post(reverse("whatsapp_acao_mensagem_api"), {
            "jid": self.jid, "message_id": self.message_id,
            "acao": "delete", "from_me": "1"
        })
        self.assertEqual(resposta.status_code, 200, resposta.content)
        apagar.assert_called_once_with(self.jid, self.message_id)
        self.assertTrue(MensagemOcultaWhatsApp.objects.filter(
            usuario=self.operador, mensagem_id=self.message_id
        ).exists())

    @patch("usuarioSec.whatsapp_views._aliases_contato_wa")
    @patch("usuarioSec.whatsapp_views.obter_mensagens_chat")
    @patch("usuarioSec.whatsapp_views.apagar_mensagem",
           return_value={"status": False, "error": "Mensagem antiga"})
    def test_falha_remota_nao_oculta_a_mensagem(
        self, _apagar, historico, aliases
    ):
        from .models import MensagemOcultaWhatsApp
        aliases.return_value = [self.jid]
        historico.return_value = {"data": [{
            "keyId": self.message_id, "fromMe": True
        }]}
        resposta = self.client.post(reverse("whatsapp_acao_mensagem_api"), {
            "jid": self.jid, "message_id": self.message_id,
            "acao": "delete", "from_me": "1"
        })
        self.assertEqual(resposta.status_code, 502)
        self.assertFalse(MensagemOcultaWhatsApp.objects.exists())

    def test_ocultacoes_nao_passam_para_outra_conta(self):
        from .models import MensagemOcultaWhatsApp
        from .sessao_whatsapp import criar_sessao_isolada, sessao_atual_id
        self.client.post(reverse("whatsapp_acao_mensagem_api"), {
            "jid": self.jid, "message_id": self.message_id,
            "acao": "hide_local"
        })
        antiga = sessao_atual_id()
        criar_sessao_isolada()
        self.assertNotEqual(sessao_atual_id(), antiga)
        self.client.post(reverse("whatsapp_acao_mensagem_api"), {
            "jid": self.jid, "message_id": self.message_id,
            "acao": "hide_local"
        })
        self.assertEqual(MensagemOcultaWhatsApp.objects.count(), 2)

    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False)
    def test_tela_tem_lixeira_visivel_e_duas_opcoes(self, _config):
        resposta = self.client.get(reverse("whatsapp_mensagens"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "wa-message-delete-trigger")
        self.assertContains(resposta, 'id="deleteMessageDialog"')
        self.assertContains(resposta, "Remover somente do EMECA")
        self.assertContains(resposta, "Apagar para todos")


class SidebarFlutuanteAutomaticoTests(TestCase):
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False)
    def test_sidebar_nao_exibe_botao_manual_e_css_novo_e_carregado(self, _gateway):
        usuario = get_user_model().objects.create_user(
            username="teste_menu_hover", password="SenhaExemploNaoReal123"
        )
        autorizar_operador_whatsapp_teste(usuario)
        self.client.force_login(usuario)
        resposta = self.client.get(reverse("whatsapp_mensagens"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'aria-label="Navegação da secretaria"')
        self.assertNotContains(resposta, 'class="sidebar-toggle"')
        self.assertNotContains(resposta, "js/sidebar.js")
        self.assertContains(resposta, "20261017-sidebar-hover-overlay-06")

    def test_css_menu_flutuante_preserva_largura_do_conteudo(self):
        from pathlib import Path
        from django.contrib.staticfiles.finders import find
        caminho = find("css/school-ui.css")
        self.assertIsNotNone(caminho)
        css = Path(caminho).read_text(encoding="utf-8")
        self.assertIn("position: fixed !important", css)
        self.assertIn("body:has(> .sidebar)", css)
        self.assertIn("padding-left: 76px", css)
        self.assertIn(".sidebar:is(:hover, :focus-within)", css)
        self.assertNotIn(".sidebar.is-collapsed", css)
