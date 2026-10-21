"""Testes locais: diagnósticos de HTTP 400 não registram conteúdo nem tokens."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
PATCH=HERE/"patch-resposta-400.cjs"
SAMPLE=(
    "export const getWAUploadToServer = () => {\n"
    " // EMECA_RC9_HTTPS_UPLOAD_V2\n"
    " const emecaHttpsUploadWithNode = () => {\n"
    '            res.on("end", () => resolve({\n'
    '                status: res.statusCode,\n'
    '                json: async () => JSON.parse(Buffer.concat(chunks).toString("utf8"))\n'
    '            }));\n'
    " };\n"
    "};\n"
    "const getMediaRetryKey = () => {};\n"
)

SAMPLE_FETCH_V1=(
    "export const getWAUploadToServer = () => {\n"
    " // EMECA_BAILEYS_RC9_UPLOAD_V1\n"
    " const response = await fetch(url, {body: stream});\n"
    " let parsed = undefined;\n"
    " try { parsed = await response.json(); } catch { parsed = undefined; }\n"
    " return parsed;\n"
    "};\n"
    "const getMediaRetryKey = () => {};\n"
)

class TestRejeicao400(unittest.TestCase):
    def setUp(self):
        if not shutil.which("node"):
            self.skipTest("Node não encontrado; diagnóstico é validado dentro do contêiner no mini PC")

    def patch(self,root):
        return subprocess.run(["node",str(PATCH),str(root)],capture_output=True,text=True)

    def fixture(self,base,version="7.0.0-rc.9",code=SAMPLE):
        (base/"lib"/"Utils").mkdir(parents=True)
        target=base/"lib"/"Utils"/"messages-media.js"
        target.write_text(code)
        (base/"package.json").write_text(json.dumps({"version":version}))
        return target

    def test_sanitizacao_e_idempotencia(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            f=self.fixture(root)
            first=self.patch(root)
            self.assertEqual(first.returncode,0,first.stderr)
            result=f.read_text()
            self.assertIn("WA-MEDIA-REJECTION-DIAG-V1",result)
            self.assertIn("responseClass",result)
            self.assertIn("responseFormat",result)
            self.assertIn("responseBytes",result)
            self.assertNotIn("console.error(responseBody)",result)
            self.assertNotIn("console.error(mediaUrl)",result)
            syntax=subprocess.run(["node","--check",str(f)],capture_output=True,text=True)
            self.assertEqual(syntax.returncode,0,syntax.stderr)
            second=self.patch(root)
            self.assertEqual(second.returncode,0,second.stderr)
            self.assertEqual(f.read_text(),result)

    def test_transporte_fetch_v1_sanitizado(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            f=self.fixture(root,code=SAMPLE_FETCH_V1)
            first=self.patch(root)
            self.assertEqual(first.returncode,0,first.stderr)
            patched=f.read_text()
            self.assertIn("WA-MEDIA-REJECTION-DIAG-V1",patched)
            self.assertIn("await response.text()",patched)
            self.assertIn("parsed = JSON.parse(emecaRawResponse)",patched)
            self.assertNotIn("parsed = await response.json()",patched)
            self.assertNotIn("console.error(emecaRawResponse)",patched)
            second=self.patch(root)
            self.assertEqual(second.returncode,0,second.stderr)
            self.assertEqual(f.read_text(),patched)
            syntax=subprocess.run(["node","--check",str(f)],capture_output=True,text=True)
            self.assertEqual(syntax.returncode,0,syntax.stderr)

    def test_outro_baileys_recusado(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            f=self.fixture(root,version="7.0.0-rc14")
            previous=f.read_bytes()
            self.assertNotEqual(self.patch(root).returncode,0)
            self.assertEqual(f.read_bytes(),previous)

    def test_transporte_inesperado_recusado(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            f=self.fixture(root,code=SAMPLE.replace("EMECA_RC9_HTTPS_UPLOAD_V2","OUTRA_VERSAO"))
            previous=f.read_bytes()
            self.assertNotEqual(self.patch(root).returncode,0)
            self.assertEqual(f.read_bytes(),previous)

if __name__=="__main__":
    unittest.main()
