"""Protege o envio de imagem/PDF por lote no WA-AKG sem rede ou mensagens reais."""
import importlib.util
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("emeca_broadcast_patch", BASE / "aplicar_correcoes.py")
patcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patcher)


ORIGINAL = """const broadcastBodySchema = z.object({
    recipients: z.array(z.string()),
    message: z.string().min(1),
    delay: z.number().optional()
});
export async function POST(request) {
    try {
        const body = await request.json();
        const parseResult = broadcastBodySchema.safeParse(body);
        const { recipients, message, delay } = parseResult.data;
        const log = await prisma.broadcastLog.create({
            data: {
                sessionId,
                message,
                total: recipients.length,
                delay: delay || 2000,
            }
        });
        const messageContent: AnyMessageContent = { text: message };
        for (let i = 0; i < recipients.length; i++) {
            await instance.socket!.sendMessage(recipients[i], messageContent);
        }
    } catch (e) {}
}
"""


class BroadcastMediaTests(unittest.TestCase):
    def test_aceita_multipart_e_preserva_envio_individual(self):
        patched = patcher.corrigir_broadcast_anexo(ORIGINAL)
        self.assertIn('request.formData()', patched)
        self.assertIn('mediaFile.type === "application/pdf"', patched)
        self.assertIn('document: mediaBuffer', patched)
        self.assertIn('image: mediaBuffer', patched)
        self.assertIn('message: z.string().max(4000)', patched)
        self.assertIn('await instance.socket!.sendMessage(recipients[i], messageContent)', patched)
        self.assertEqual(patched, patcher.corrigir_broadcast_anexo(patched))

    def test_patch_recusa_servidor_desconhecido(self):
        with self.assertRaises(RuntimeError):
            patcher.corrigir_broadcast_anexo("broadcast manual diferente")

    def test_codigo_instalado_apenas_leitura(self):
        route = Path("/srv/projetos/wa-akg/src/app/api/messages/[sessionId]/broadcast/route.ts")
        if not route.is_file():
            self.skipTest("WA-AKG não está montado neste ambiente")
        source = route.read_text(encoding="utf-8")
        patched = patcher.corrigir_broadcast_anexo(source)
        self.assertIn("mediaBuffer", patched)
        self.assertEqual(patched, patcher.corrigir_broadcast_anexo(patched))
        self.assertEqual(source, route.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
