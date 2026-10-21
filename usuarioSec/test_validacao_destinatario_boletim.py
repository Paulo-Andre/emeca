"""Testes sem rede e sem banco para proteção de documentos escolares."""
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from usuarioSec.management.commands.processar_envios_whatsapp import (
    _jid_eh_mesmo_numero_confirmado,
    confirmar_jid_whatsapp_do_boletim,
    processar_item,
)
from usuarioSec.whatsapp_gateway import WhatsAppGatewayError


WORKER = "usuarioSec.management.commands.processar_envios_whatsapp."
CADASTRADO = "5538999991111@s.whatsapp.net"  # Número sintético com 9º dígito
LEGADO = "553899991111@s.whatsapp.net"      # O mesmo número sem o 9


class ValidacaoJidBoletimTests(SimpleTestCase):
    def test_mesmo_numero_e_nono_digito_sao_validos(self):
        self.assertTrue(_jid_eh_mesmo_numero_confirmado(CADASTRADO, CADASTRADO))
        self.assertTrue(_jid_eh_mesmo_numero_confirmado(CADASTRADO, LEGADO))
        self.assertTrue(_jid_eh_mesmo_numero_confirmado(LEGADO, CADASTRADO))

    def test_outro_numero_e_lid_sao_bloqueados(self):
        self.assertFalse(_jid_eh_mesmo_numero_confirmado(
            CADASTRADO, "5538999982222@s.whatsapp.net"
        ))
        self.assertFalse(_jid_eh_mesmo_numero_confirmado(
            CADASTRADO, "12345678@lid"
        ))
        self.assertFalse(_jid_eh_mesmo_numero_confirmado(
            CADASTRADO, "553899991111@g.us"
        ))

    @patch(WORKER + "verificar_numeros")
    def test_confirma_e_usa_jid_retornado_pelo_whatsapp(self, check):
        check.return_value = {
            "status": True,
            "data": {"results": [{
                "number": CADASTRADO.split("@")[0],
                "exists": True,
                "jid": LEGADO,
            }]}
        }
        item = SimpleNamespace(jid=CADASTRADO)
        self.assertEqual(confirmar_jid_whatsapp_do_boletim(item), LEGADO)
        check.assert_called_once_with([CADASTRADO.split("@")[0]])

    @patch(WORKER + "verificar_numeros")
    def test_bloqueia_numero_inexistente_e_outro_jid(self, check):
        item = SimpleNamespace(jid=CADASTRADO)
        check.return_value = {
            "status": True,
            "data": {"results": [{
                "number": CADASTRADO.split("@")[0],
                "exists": False,
                "jid": None,
            }]}
        }
        with self.assertRaises(WhatsAppGatewayError):
            confirmar_jid_whatsapp_do_boletim(item)

        check.return_value["data"]["results"][0].update({
            "exists": True, "jid": "5538999982222@s.whatsapp.net",
        })
        with self.assertRaises(WhatsAppGatewayError):
            confirmar_jid_whatsapp_do_boletim(item)

        check.return_value["data"]["results"][0].update({
            "jid": "12345678@lid",
        })
        with self.assertRaises(WhatsAppGatewayError):
            confirmar_jid_whatsapp_do_boletim(item)

    @patch(WORKER + "verificar_numeros")
    def test_bloqueia_numero_de_entrada_trocado_na_resposta(self, check):
        check.return_value = {
            "status": True, "data": {"results": [{
                "number": "5538999982222",
                "exists": True, "jid": LEGADO,
            }]}
        }
        with self.assertRaises(WhatsAppGatewayError):
            confirmar_jid_whatsapp_do_boletim(SimpleNamespace(jid=CADASTRADO))

    @patch(WORKER + "enviar_documento")
    @patch(WORKER + "gerar_pdf_boletim")
    @patch(WORKER + "verificar_numeros")
    @patch(WORKER + "validar_destinatario_do_boletim")
    @patch(WORKER + "sessao_atual_id", return_value="sessao-teste")
    def test_processar_item_usa_jid_confirmado_no_pdf(
        self, _sessao, _validar, check, gerar, enviar
    ):
        check.return_value = {
            "status": True, "data": {"results": [{
                "number": CADASTRADO.split("@")[0], "exists": True,
                "jid": LEGADO,
            }]}
        }
        gerar.return_value = BytesIO(b"%PDF-1.4 teste sintetico")
        enviar.return_value = {"status": True}
        boletim = SimpleNamespace(
            aluno=SimpleNamespace(nome_oficial="ALUNO SINTETICO"),
            periodo=SimpleNamespace(nome_periodo="Primeiro trimestre", ano=2026)
        )
        item = SimpleNamespace(
            jid=CADASTRADO, status="PENDENTE", erro="",
            boletim=boletim, save=Mock(),
        )
        envio = SimpleNamespace(sessao="sessao-teste", mensagem="")
        status = processar_item(envio, item, None, "Escola Sintetica")
        self.assertEqual(status, "ENVIADO")
        self.assertEqual(enviar.call_args.args[0], LEGADO)
        self.assertEqual(enviar.call_args.kwargs["sessao_id"], "sessao-teste")
        self.assertEqual(item.jid, CADASTRADO)  # Auditoria original preservada

    @patch(WORKER + "enviar_documento")
    @patch(WORKER + "gerar_pdf_boletim")
    @patch(WORKER + "verificar_numeros")
    @patch(WORKER + "validar_destinatario_do_boletim")
    @patch(WORKER + "sessao_atual_id", return_value="sessao-teste")
    def test_jid_sem_correspondencia_nao_gera_nem_envia_pdf(
        self, _sessao, _validar, check, gerar, enviar
    ):
        check.return_value = {
            "status": True, "data": {"results": [{
                "number": CADASTRADO.split("@")[0], "exists": True,
                "jid": "5538999982222@s.whatsapp.net",
            }]}
        }
        item = SimpleNamespace(
            jid=CADASTRADO, status="PENDENTE", erro="",
            save=Mock(),
        )
        envio = SimpleNamespace(sessao="sessao-teste", mensagem="")
        status = processar_item(envio, item, None, "Escola Sintetica")
        self.assertEqual(status, "ERRO")
        self.assertIn("não correspondente", item.erro)
        gerar.assert_not_called()
        enviar.assert_not_called()
