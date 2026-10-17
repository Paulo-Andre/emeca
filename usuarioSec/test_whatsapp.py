from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
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
    TelefoneDeclaracao,
    declaracao,
)
from .whatsapp_views import (
    _enriquecer_chats,
    _normalizar_jid,
    _resolver_boletins_destinatarios,
    _resolver_destinatarios,
)


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
        self.aluna_a = AlunoBoletim.objects.create(nome="ALUNA A")
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
        aluno_b = AlunoBoletim.objects.create(nome="ALUNO B")
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
        envio = EnvioBoletimWhatsApp.objects.create(
            tipo_periodo="TRIMESTRE",
            numero_periodo=1,
            ano=2026,
            modo="todos",
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
        self.client.force_login(self.usuario)

    @patch("usuarioSec.whatsapp_views.listar_chats")
    @patch("usuarioSec.whatsapp_views.obter_sessao")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_tela_mensagens_lista_conversas(
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
        self.assertContains(response, "Mensagens do WhatsApp")
        self.assertContains(response, "RESPONSAVEL SINTETICO")
        self.assertContains(response, "Envios")

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
