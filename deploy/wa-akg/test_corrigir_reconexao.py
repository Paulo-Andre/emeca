"""Verifica o patch de reconexão sem acessar API, banco ou WhatsApp.

Executar: python3 -m unittest discover -s deploy/wa-akg -p 'test_*.py'
"""
import importlib.util
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("patcher_reconexao", BASE / "aplicar_correcoes.py")
patcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patcher)


class ReconexaoWAACKGTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = Path("/srv/projetos/wa-akg/src/modules/whatsapp/instance.ts")

    def test_versao_desconhecida_recusada(self):
        with self.assertRaises(RuntimeError):
            patcher.corrigir_reconexao_instancia("custom altered socket implementation")

    def test_guarda_e_idempotencia_no_codigo_instalado(self):
        if not self.path.is_file():
            self.skipTest("WA-AKG não está disponível neste ambiente")
        original = self.path.read_text(encoding="utf-8")
        corrigido = patcher.corrigir_reconexao_instancia(original)
        novamente = patcher.corrigir_reconexao_instancia(corrigido)
        self.assertEqual(corrigido, novamente)
        self.assertIn("generation !== this.socketGeneration", corrigido)
        self.assertIn("this.reconnectTimer = setTimeout", corrigido)
        self.assertIn("const previousSocket = this.socket", corrigido)
        self.assertIn("if (this.closeHandled) return", corrigido)
        self.assertIn('String(code ?? "unknown")', corrigido)
        self.assertIn("++this.socketGeneration", corrigido)
        self.assertNotIn("if (!this.isStopped) this.init();", corrigido)
        # Somente transforma texto em memória, sem escrever no WA-AKG real.
        self.assertEqual(self.path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
