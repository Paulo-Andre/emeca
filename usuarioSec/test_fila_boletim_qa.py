"""QA de privacidade da fila de boletins via WhatsApp.

Todos os contatos e alunos são fictícios. Não usa gateway externo.
"""
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from site_publico.models import AlunoBoletim, BoletimAluno, PeriodoBoletim
from usuarioSec.management.commands.processar_envios_whatsapp import (
    confirmar_aceite_documento,
    validar_destinatario_do_boletim,
    recuperar_lotes_obsoletos,
    processar_item,
)
from usuarioSec.models import (
    EnvioBoletimWhatsApp,
    ItemEnvioBoletimWhatsApp,
    TelefoneDeclaracao,
    declaracao,
)
from usuarioSec.whatsapp_gateway import WhatsAppGatewayError


class FilaBoletimPrivacidadeTests(TestCase):
    def setUp(self):
        self.crianca = declaracao.objects.create(
            nomeDoAluno="ALUNO QA FICTICIO",
            turmaDoAluno="1º QA",
        )
        self.telefone = TelefoneDeclaracao.objects.create(
            declaracao=self.crianca,
            tipo="MAE",
            telefone="(38) 99999-1111",
        )
        self.periodo = PeriodoBoletim.objects.create(
            tipo="TRIMESTRE",
            numero=2, ano=2026,
            turma="1º QA",
            publicado=True,
        )
        self.perfil = AlunoBoletim.objects.create(
            nome="ALUNO QA FICTICIO",
            declaracao=self.crianca,
        )
        self.boletim = BoletimAluno.objects.create(
            periodo=self.periodo,
            aluno=self.perfil,
            faltas_totais=3,
        )
        self.lote = EnvioBoletimWhatsApp.objects.create(
            tipo_periodo="TRIMESTRE",
            numero_periodo=2,
            ano=2026,
            modo="individual",
            sessao="emeca-qa-sintetico",
            status="PENDENTE",
            total=1,
        )
        self.item = ItemEnvioBoletimWhatsApp.objects.create(
            envio=self.lote,
            boletim=self.boletim,
            jid="5538999991111@s.whatsapp.net",
            tipo_contato="MAE",
            status="PENDENTE",
        )

    def test_destinatario_do_cadastro_atual_e_permitido(self):
        self.assertIsNone(validar_destinatario_do_boletim(self.item))

    def test_troca_de_telefone_bloqueia_pdf_em_lote_antigo(self):
        self.telefone.telefone = "(38) 98888-2222"
        self.telefone.save(update_fields=["telefone"])
        with self.assertRaisesRegex(WhatsAppGatewayError, "não pertence mais"):
            validar_destinatario_do_boletim(self.item)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "PENDENTE")

    def test_desvincular_declaracao_bloqueia_pdf(self):
        self.perfil.declaracao = None
        self.perfil.save(update_fields=["declaracao"])
        with self.assertRaisesRegex(WhatsAppGatewayError, "sem vínculo"):
            validar_destinatario_do_boletim(self.item)

    def test_retirar_publicacao_bloqueia_pdf(self):
        self.periodo.publicado = False
        self.periodo.save(update_fields=["publicado", "atualizado_em"])
        with self.assertRaisesRegex(WhatsAppGatewayError, "deixou de estar publicado"):
            validar_destinatario_do_boletim(self.item)

    def test_aluno_com_nome_igual_nao_autoriza_telefone_de_outro(self):
        outro = declaracao.objects.create(
            nomeDoAluno=self.crianca.nomeDoAluno,
            turmaDoAluno=self.crianca.turmaDoAluno,
        )
        TelefoneDeclaracao.objects.create(
            declaracao=outro,
            tipo="MAE",
            telefone="(38) 97777-3333",
        )
        self.item.jid = "5538977773333@s.whatsapp.net"
        self.item.save(update_fields=["jid"])
        with self.assertRaisesRegex(WhatsAppGatewayError, "não pertence mais"):
            validar_destinatario_do_boletim(self.item)

    def test_status_falso_na_resposta_do_gateway_nunca_e_sucesso(self):
        for resposta in (
            None, {}, {"status": False}, {"success": False},
            {"status": "SENT"}, {"message": "ok"},
        ):
            with self.subTest(resposta=resposta):
                with self.assertRaises(WhatsAppGatewayError):
                    confirmar_aceite_documento(resposta)

    def test_resposta_positiva_indica_aceite_nao_entrega_comprovada(self):
        for resposta in ({"status": True}, {"success": True}):
            with self.subTest(resposta=resposta):
                self.assertEqual(
                    confirmar_aceite_documento(resposta), resposta,
                )

    def test_recuperacao_obsoleta_nao_retransmite_item_iniciado(self):
        from datetime import timedelta
        self.lote.status = "PROCESSANDO"
        self.lote.iniciado_em = timezone.now() - timedelta(hours=7)
        self.lote.save(update_fields=["status", "iniciado_em"])
        self.item.status = "PROCESSANDO"
        self.item.save(update_fields=["status"])
        recuperar_lotes_obsoletos()
        self.lote.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.lote.status, "PENDENTE")
        self.assertEqual(self.item.status, "ERRO")
        self.assertIn("interrompido", self.item.erro)


    def _processar_sem_rede(self, *, resposta=None, falha=None, sessao=None):
        """Ações sob mocks: nunca conecta ao número real da escola."""
        modulo = "usuarioSec.management.commands.processar_envios_whatsapp"
        with (
            patch(f"{modulo}.sessao_atual_id", return_value=sessao or self.lote.sessao),
            patch(f"{modulo}.gerar_pdf_boletim", return_value=BytesIO(b"%PDF-1.4 ficticio")) as render,
            patch(f"{modulo}.enviar_documento", return_value=resposta, side_effect=falha) as enviar,
        ):
            resultado = processar_item(
                self.lote, self.item, None, "Escola de QA",
            )
        self.item.refresh_from_db()
        return resultado, render, enviar

    def test_processamento_positivo_marca_aceite_api(self):
        resultado, render, enviar = self._processar_sem_rede(
            resposta={"status": True, "data": {"id": "fake"}}
        )
        self.assertEqual(resultado, "ENVIADO")
        self.assertEqual(self.item.status, "ENVIADO")
        self.assertIsNotNone(self.item.enviado_em)
        self.assertEqual(render.call_count, 1)
        self.assertEqual(enviar.call_count, 1)
        self.assertEqual(enviar.call_args.kwargs["sessao_id"], self.lote.sessao)

    def test_processamento_resposta_negativa_nao_conta_como_envio(self):
        resultado, render, enviar = self._processar_sem_rede(
            resposta={"success": False, "message": "não aceito"}
        )
        self.assertEqual(resultado, "ERRO")
        self.assertIsNone(self.item.enviado_em)
        self.assertEqual(enviar.call_count, 1)

    def test_telefone_alterado_antes_do_disparo_nunca_gera_pdf_ou_envia(self):
        self.telefone.telefone = "(38) 98888-2222"
        self.telefone.save(update_fields=["telefone"])
        resultado, render, enviar = self._processar_sem_rede(
            resposta={"status": True}
        )
        self.assertEqual(resultado, "ERRO")
        render.assert_not_called()
        enviar.assert_not_called()

    def test_alteracao_de_publicacao_apos_cache_bloqueia_envio(self):
        # A relação carregada pelo ORM no início do lote pode estar velha.
        _ = self.item.boletim.periodo.publicado
        self.periodo.publicado = False
        self.periodo.save(update_fields=["publicado", "atualizado_em"])
        resultado, render, enviar = self._processar_sem_rede(
            resposta={"status": True}
        )
        self.assertEqual(resultado, "ERRO")
        render.assert_not_called()
        enviar.assert_not_called()

    def test_troca_de_conta_interrompe_antes_de_gerar_documento(self):
        resultado, render, enviar = self._processar_sem_rede(
            sessao="outra-conta", resposta={"status": True}
        )
        self.assertEqual(resultado, "ERRO")
        render.assert_not_called()
        enviar.assert_not_called()

    def test_timeout_nao_reativa_envio_automatico(self):
        resultado, render, enviar = self._processar_sem_rede(
            falha=WhatsAppGatewayError("Tempo limite; entrega desconhecida")
        )
        self.assertEqual(resultado, "ERRO")
        self.assertEqual(self.item.enviado_em, None)
        self.assertEqual(self.item.status, "ERRO")
        self.assertEqual(enviar.call_count, 1)
