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
