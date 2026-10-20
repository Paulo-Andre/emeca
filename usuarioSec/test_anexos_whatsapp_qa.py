"""Validação de anexos de campanha e armazenamento privado, sem WhatsApp real."""
from pathlib import Path
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from usuarioSec.anexos_boletim_whatsapp import (
    apagar_anexo, extrair_mensagem_anexo, ler_anexo,
    mensagem_com_anexo, salvar_anexo,
)
from usuarioSec.whatsapp_views import _validar_anexo_campanha


PDF_FAKE = b"%PDF-1.4\nAnexo para teste\n%%EOF\n"


class AnexosWhatsappQATests(SimpleTestCase):
    def test_pdf_reconhecido_por_extensao_e_assinatura(self):
        arquivo = SimpleUploadedFile("documento.pdf", PDF_FAKE, content_type="application/pdf")
        fmt = _validar_anexo_campanha(arquivo)
        self.assertEqual(fmt["mime"], "application/pdf")
        self.assertEqual(fmt["tipo"], "document")
        self.assertEqual(arquivo.tell(), 0)

    def test_arquivo_disfarcado_e_executavel_sao_bloqueados(self):
        for nome, dados in [
            ("falso.pdf", b"MZ" + b"x" * 20),
            ("virus.exe", b"MZ" + b"x" * 20),
            ("imagem.png", b"GIF89a" + b"x" * 20),
            ("arquivo.jpg", b"%PDF-1.4 fake"),
        ]:
            with self.subTest(nome=nome):
                with self.assertRaises(ValueError):
                    _validar_anexo_campanha(SimpleUploadedFile(nome, dados))

    def test_storage_privado_e_envelope_legado(self):
        with tempfile.TemporaryDirectory() as base:
            media = Path(base) / "media"
            with override_settings(MEDIA_ROOT=media):
                arquivo = SimpleUploadedFile("documento.pdf", PDF_FAKE)
                ref = salvar_anexo(arquivo, "documento.pdf")
                self.assertEqual(
                    extrair_mensagem_anexo(mensagem_com_anexo("Boletim de {aluno}", ref)),
                    ("Boletim de {aluno}", ref),
                )
                self.assertEqual(ler_anexo(ref)[0], PDF_FAKE)
                self.assertTrue((Path(base) / "whatsapp-anexos-privados" / ref).exists())
                self.assertFalse((media / ref).exists())
                self.assertEqual(extrair_mensagem_anexo("Mensagem antiga"), ("Mensagem antiga", ""))
                apagar_anexo(ref)
                self.assertFalse((Path(base) / "whatsapp-anexos-privados" / ref).exists())

    def test_nao_aceita_referencia_com_percurso_de_diretorios(self):
        with tempfile.TemporaryDirectory() as base:
            with override_settings(MEDIA_ROOT=Path(base) / "media"):
                with self.assertRaises(ValueError):
                    mensagem_com_anexo("Texto", "../segredo.pdf")
