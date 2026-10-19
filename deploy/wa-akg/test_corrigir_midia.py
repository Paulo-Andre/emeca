"""Testes de regressão do endpoint de mídia sem disparar documentos reais.

Rodar: python3 -m unittest discover -s deploy/wa-akg -p 'test_*.py'
"""
import importlib.util
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("emeca_patcher_media", BASE / "aplicar_correcoes.py")
patcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patcher)

MEDIA_ROUTE = Path("/srv/projetos/wa-akg/src/app/api/messages/[sessionId]/[jid]/media/route.ts")

# Três marcadores idênticos ao upstream: um teste em memória, sem rede e sem QR.
UPSTREAM_SAMPLE = """
export async function POST() {
    try {
        const sent = await ChatService.sendMediaMessage(
             sessionId,
             decodedJid,
             buffer,
             type,
             file.type,
             file.name,
             caption
        );
        return NextResponse.json({ status: true, message: "Operation successful", data: sent });

    } catch (e) {
        console.error("Media send error", e);
        return NextResponse.json({ status: false, message: "Failed to send media", error: "Failed to send media" }, { status: 500 });
    }
}
"""


class TestCorrecaoMedia(unittest.TestCase):
    def assertSeguro(self, patched):
        self.assertIn('data: { messageId }', patched)
        self.assertIn('typeof sent?.key?.id === "string"', patched)
        self.assertIn('"MEDIA_SEND_FAILED"', patched)
        self.assertIn('"MEDIA_SESSION_DISCONNECTED"', patched)
        self.assertIn('Media send error (sanitized)', patched)
        self.assertNotIn('data: sent', patched)
        self.assertNotIn('error: "Failed to send media"', patched)
        self.assertEqual(patched.count('ChatService.sendMediaMessage('), 1)
        self.assertNotIn('retry', patched.lower().replace("do not repeat", ""))

    def test_retorno_json_sanitizado_e_idempotente(self):
        patched = patcher.corrigir_resposta_envio_midia(UPSTREAM_SAMPLE)
        self.assertSeguro(patched)
        self.assertEqual(patched, patcher.corrigir_resposta_envio_midia(patched))

    def test_rejeita_codigo_desconhecido_sem_substituir(self):
        with self.assertRaises(RuntimeError):
            patcher.corrigir_resposta_envio_midia("rota de mídia modificada manualmente")

    def test_arquivo_no_servidor_apenas_leitura(self):
        if not MEDIA_ROUTE.exists():
            self.skipTest("WA-AKG não montado neste ambiente")
        original = MEDIA_ROUTE.read_text(encoding="utf-8")
        patched = patcher.corrigir_resposta_envio_midia(original)
        self.assertSeguro(patched)
        self.assertEqual(original, MEDIA_ROUTE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
