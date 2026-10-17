from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
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
        estado = LeituraChatWhatsApp.objects.create(
            usuario=self.usuario, jid=self.telefone, nao_lidas=3
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
        self.assertContains(response, "whatsapp_perfil_api")


class WhatsAppDesconexaoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="administrador_desconexao_wa",
            password="SenhaDeTeste-local",
            is_staff=True,
            is_superuser=True,
        )
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

    @patch("usuarioSec.whatsapp_views.desvincular_sessao", return_value={"status": True})
    @patch("usuarioSec.whatsapp_views.obter_sessao",
           return_value={"data": {"status": "CONNECTED"}})
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_desvinculacao_confirmada(self, _config, _sessao, desvincular):
        result = self.client.post(self.url, {
            "acao": "desvincular", "confirmacao": "DESVINCULAR",
            "origem": "mensagens",
        })
        self.assertRedirects(
            result, reverse("whatsapp_mensagens"), fetch_redirect_response=False
        )
        desvincular.assert_called_once_with()

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
            "acao": "desvincular", "confirmacao": "DESVINCULAR"
        })
        self.assertEqual(result.status_code, 302)
        desvincular.assert_not_called()

    @patch("usuarioSec.whatsapp_views.pausar_sessao")
    @patch("usuarioSec.whatsapp_views.desvincular_sessao")
    def test_usuario_comum_nao_pode_desconectar(self, desvincular, pausar):
        comum = get_user_model().objects.create_user(username="colaborador_sem_permissao")
        self.client.force_login(comum)
        resposta = self.client.post(self.url, {
            "acao": "desvincular", "confirmacao": "DESVINCULAR"
        })
        self.assertEqual(resposta.status_code, 403)
        desvincular.assert_not_called()
        pausar.assert_not_called()

    def test_desconexao_usa_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

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

    @patch("usuarioSec.whatsapp_views.criar_etiqueta",
           return_value={"status": True, "data": {"label": {"id": "teste", "name": "Matrícula"}}})
    def test_criar_etiqueta_na_tela_de_mensagens(self, criar):
        response = self.client.post(reverse("whatsapp_etiquetas_criar_api"), {
            "nome": "Matrícula", "cor": "3",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["etiqueta"]["name"], "Matrícula")
        criar.assert_called_once_with("Matrícula", 3)

    @patch("usuarioSec.whatsapp_views.criar_etiqueta")
    def test_nao_cria_etiqueta_com_nome_vazio(self, criar):
        response = self.client.post(reverse("whatsapp_etiquetas_criar_api"), {
            "nome": "  ", "cor": "0",
        })
        self.assertEqual(response.status_code, 400)
        criar.assert_not_called()

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
