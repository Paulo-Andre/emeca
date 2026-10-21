"""Testes da substituição pontual do transporte rc.9, sem rede ou WhatsApp."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
PATCH = HERE / "patch-baileys-rc9-https.cjs"
SOURCE = """
// EMECA_BAILEYS_RC9_UPLOAD_V1
export const getWAUploadToServer = () => {
    return async (filePath) => {
        const response = await fetch(url, {
            headers: {'Content-Length': emecaEncryptedFileSize},
            body: stream,
            signal: undefined
        });
        console.error("WA-MEDIA-HTTP-DIAG", { httpStatus: response.status });
        let parsed = undefined;
        return parsed;
    };
};
const getMediaRetryKey = () => null;
"""


class TestTransporteRc9(unittest.TestCase):
    def setUp(self):
        if not shutil.which("node"):
            self.skipTest("Node não instalado no host do teste; preflight Docker cobre a imagem real")

    def make_fixture(self, root, version="7.0.0-rc.9", content=SOURCE):
        target = root / "lib/Utils/messages-media.js"
        target.parent.mkdir(parents=True)
        target.write_text(content)
        (root / "package.json").write_text(json.dumps({"version": version}))
        return target

    def patch(self, root):
        return subprocess.run(["node", str(PATCH), str(root)], capture_output=True, text=True)

    def test_versao_exata_sem_duplica_lo(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = self.make_fixture(root)
            first = self.patch(root)
            self.assertEqual(first.returncode, 0, first.stderr)
            after = target.read_text()
            self.assertIn("EMECA_RC9_HTTPS_UPLOAD_V2", after)
            self.assertIn("emecaHttpsUploadWithNode(url, filePath, {", after)
            self.assertNotIn("const response = await fetch(url, {", after)
            self.assertIn("MEDIA_SIZE_MISMATCH", after)
            self.assertIn("text: async () => responseBody", after)
            second = self.patch(root)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(target.read_text(), after)
            syntax = subprocess.run(["node", "--check", str(target)], capture_output=True, text=True)
            self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_outro_baileys_rejeitado_sem_escrita(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = self.make_fixture(root, version="7.0.0-rc14")
            before = target.read_bytes()
            self.assertNotEqual(self.patch(root).returncode, 0)
            self.assertEqual(before, target.read_bytes())

    def test_patch_v1_ausente_rejeitado_sem_escrita(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = self.make_fixture(root, content=SOURCE.replace("EMECA_BAILEYS_RC9_UPLOAD_V1", "SEM_V1"))
            before = target.read_bytes()
            self.assertNotEqual(self.patch(root).returncode, 0)
            self.assertEqual(before, target.read_bytes())


if __name__ == "__main__":
    unittest.main()
