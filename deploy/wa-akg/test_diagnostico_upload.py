"""Regressão sintética: nenhum contato com WhatsApp, nenhuma mídia real."""
import importlib.util
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "emeca_patch_upload", BASE / "aplicar_correcoes.py"
)
patcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patcher)

INSTANCE = Path("/srv/projetos/wa-akg/src/modules/whatsapp/instance.ts")
ORIGINAL = """
import pino from "pino";
const MAX_RECONNECT_ATTEMPTS = 3;
    async initializeSocket() {
        this.socket = makeWASocket({
            version,
            logger: pino({ level: process.env.BAILEYS_LOG_LEVEL || "error" }) as any,
            printQRInTerminal: false
        });
    }
"""

OLD_AGENT = """
        // EMECA: observar apenas o código HTTP do upload, nunca a URL
        // autenticada ou o corpo da resposta. Nenhum reenvio é realizado.
        const mediaFetchAgent = new HttpsAgent({ keepAlive: true });
        const nativeAddRequest = (mediaFetchAgent as any).addRequest.bind(mediaFetchAgent);
        (mediaFetchAgent as any).addRequest = (request: any, options: any) => {
            if (request.method === "POST") {
                request.once("response", (response: any) => {
                    const httpStatus = typeof response.statusCode === "number" &&
                        response.statusCode >= 100 && response.statusCode <= 599
                        ? response.statusCode : null;
                    console.error("WA-MEDIA-HTTP-DIAG", { httpStatus });
                });
            }
            return nativeAddRequest(request, options);
        };
"""


class DiagnosticoUploadTests(unittest.TestCase):
    def _base(self):
        primeiro = patcher.corrigir_diagnostico_upload_instancia(ORIGINAL)
        return patcher.detalhar_resposta_upload_instancia(primeiro)

    def _assert_passivo(self, content):
        self.assertIn("WA-MEDIA-UPLOAD-DIAG", content)
        self.assertIn("resultKind", content)
        self.assertIn('diagnosticChannel("http.client.response.finish")', content)
        self.assertIn("WA-MEDIA-HTTP-DIAG", content)
        self.assertIn("EMECA_MEDIA_HTTP_PASSIVE_V1", content)
        self.assertEqual(content.count("WA-MEDIA-HTTP-DIAG"), 1)
        self.assertEqual(content.count("EMECA_MEDIA_HTTP_PASSIVE_V1"), 1)
        self.assertEqual(content.count("this.socket = makeWASocket({"), 1)
        self.assertNotIn("fetchAgent: mediaFetchAgent", content)
        self.assertNotIn("new HttpsAgent", content)
        self.assertNotIn("nativeAddRequest", content)
        self.assertNotIn("Agent as HttpsAgent", content)
        self.assertNotIn("console.error(trace", content)
        self.assertNotIn("console.error(details", content)

    def test_telemetria_passiva_na_versao_original(self):
        base = self._base()
        patched = patcher.observar_status_http_midia(base)
        self._assert_passivo(patched)
        self.assertEqual(
            patched, patcher.observar_status_http_midia(patched)
        )
        self.assertEqual(
            patched, patcher.corrigir_diagnostico_upload_instancia(patched)
        )
        self.assertEqual(
            patched, patcher.detalhar_resposta_upload_instancia(patched)
        )

    def test_migra_observador_antigo_sem_duplica_lo(self):
        base = self._base()
        old = base.replace(
            'import pino from "pino";',
            'import pino from "pino";\n'
            'import { Agent as HttpsAgent } from "node:https";',
        ).replace(
            '        this.socket = makeWASocket({',
            OLD_AGENT + '        this.socket = makeWASocket({',
        ).replace(
            '            logger: baileysLogger,',
            '            logger: baileysLogger,\n'
            '            fetchAgent: mediaFetchAgent,',
        )
        self.assertIn("WA-MEDIA-HTTP-DIAG", old)
        self.assertIn("fetchAgent: mediaFetchAgent", old)
        patched = patcher.observar_status_http_midia(old)
        self._assert_passivo(patched)
        self.assertEqual(patched, patcher.observar_status_http_midia(patched))

    def test_erro_se_observador_antigo_foi_modificado(self):
        base = self._base()
        broken = base.replace(
            '        this.socket = makeWASocket({',
            OLD_AGENT.replace("nativeAddRequest(request, options)", "unknownCall()")
            + '        this.socket = makeWASocket({',
        )
        broken = broken.replace(
            'import pino from "pino";',
            'import pino from "pino";\n'
            'import { Agent as HttpsAgent } from "node:https";',
        )
        broken = broken.replace(
            '            logger: baileysLogger,',
            '            logger: baileysLogger,\n'
            '            fetchAgent: mediaFetchAgent,',
        )
        with self.assertRaises(RuntimeError):
            patcher.observar_status_http_midia(broken)

    def test_arquivo_no_servidor_nao_e_modificado(self):
        if not INSTANCE.exists():
            self.skipTest("WA-AKG não montado neste ambiente")
        original = INSTANCE.read_text(encoding="utf-8")
        resultado = patcher.observar_status_http_midia(
            patcher.detalhar_resposta_upload_instancia(
                patcher.corrigir_diagnostico_upload_instancia(original)
            )
        )
        self._assert_passivo(resultado)
        self.assertEqual(original, INSTANCE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
