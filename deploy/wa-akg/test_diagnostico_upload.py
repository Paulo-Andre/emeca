"""Testes sem rede para registro seguro dos erros de upload Baileys."""
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parent / "aplicar_correcoes.py"
SPEC = importlib.util.spec_from_file_location("emeca_patch_upload", SOURCE)
patcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patcher)

INSTANCE = Path("/srv/projetos/wa-akg/src/modules/whatsapp/instance.ts")
ORIGINAL = """
    async initializeSocket() {
        this.socket = makeWASocket({
            version,
            logger: pino({ level: process.env.BAILEYS_LOG_LEVEL || "error" }) as any,
            printQRInTerminal: false
        });
    }
"""


class DiagnosticoUploadTests(unittest.TestCase):
    def test_instrumentacao_nao_registra_dados_confidenciais(self):
        changed = patcher.corrigir_diagnostico_upload_instancia(ORIGINAL)
        self.assertIn("WA-MEDIA-UPLOAD-DIAG", changed)
        self.assertIn("const baileysLogger =", changed)
        self.assertIn("logger: baileysLogger", changed)
        self.assertIn("UNKNOWN_UPLOAD_ERROR", changed)
        self.assertIn("ETIMEDOUT", changed)
        self.assertNotIn("console.error(trace", changed)
        self.assertNotIn("console.error(details", changed)
        self.assertEqual(changed.count("this.socket = makeWASocket({"), 1)
        self.assertEqual(changed, patcher.corrigir_diagnostico_upload_instancia(changed))

    def test_instrumentacao_recusa_codigo_desconhecido(self):
        with self.assertRaises(RuntimeError):
            patcher.corrigir_diagnostico_upload_instancia("outro makeWASocket")

    def test_versao_local_se_existir_permanece_inalterada(self):
        if not INSTANCE.exists():
            self.skipTest("WA-AKG não montado neste ambiente")
        before = INSTANCE.read_text(encoding="utf-8")
        after = patcher.corrigir_diagnostico_upload_instancia(before)
        self.assertIn("WA-MEDIA-UPLOAD-DIAG", after)
        self.assertEqual(before, INSTANCE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
