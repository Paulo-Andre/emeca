"""Testes offline do patch cirúrgico no uploader Baileys rc.9.

Não depende de rede, Docker, sessão, credenciais nem mídia de aluno.
"""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("preparo_media_rc9", HERE / "preparar_fix_upload_rc9.py")
PREPARO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARO)

FAKE_SOURCE = """
export const getWAUploadToServer = (config) => {
  return async (filePath) => {
    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/octet-stream',
        Origin: DEFAULT_ORIGIN
      }
    });
    let parsed = undefined;
    result = parsed;
    if (result?.url || result?.directPath) {
      urls = {
        mediaUrl: result.url,
        directPath: result.direct_path,
      };
    }
  }
}
const getMediaRetryKey = () => {};
"""


class PatchRc9Tests(unittest.TestCase):
    def run_patch(self, root: Path):
        return subprocess.run(
            ["node", str(HERE / "patch-baileys-rc9.cjs"), str(root)],
            capture_output=True, text=True, check=False
        )

    def create_pkg(self, root, version="7.0.0-rc.9", code=FAKE_SOURCE):
        f = root / "lib" / "Utils" / "messages-media.js"
        f.parent.mkdir(parents=True)
        f.write_text(code, encoding="utf-8")
        (root / "package.json").write_text(json.dumps({"version": version}), encoding="utf-8")
        return f

    def test_patcher_criptografado_status_e_direct_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = self.create_pkg(folder)
            first = self.run_patch(folder)
            self.assertEqual(first.returncode, 0, first.stderr)
            patched = source.read_text()
            self.assertIn("'Content-Length': emecaEncryptedFileSize", patched)
            self.assertIn("stat(filePath)", patched)
            self.assertIn("WA-MEDIA-HTTP-DIAG", patched)
            self.assertIn("result?.direct_path", patched)
            self.assertIn("directPath: result.direct_path || result.directPath", patched)
            self.assertNotIn("fetchAgent: mediaFetchAgent", patched)
            self.assertEqual(self.run_patch(folder).returncode, 0)
            self.assertEqual(patched, source.read_text())

    def test_nao_patchar_outra_versao(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = self.create_pkg(folder, version="7.0.0-rc14")
            original = source.read_bytes()
            result = self.run_patch(folder)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(original, source.read_bytes())

    def test_fonte_desconhecida_nao_modificada(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = self.create_pkg(folder, code="export const unknownUploader = 1;")
            original = source.read_bytes()
            result = self.run_patch(folder)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(original, source.read_bytes())

    def test_preparo_dockerfile_e_manifestos(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "Dockerfile").write_text(
                "FROM node:26-alpine\nCOPY . .\nRUN npx prisma generate && npm run build\n"
            )
            (source / "package.json").write_text(json.dumps({
                "dependencies": {"@whiskeysockets/baileys": "7.0.0-rc.9"}
            }))
            (source / "package-lock.json").write_text(json.dumps({
                "packages": {"node_modules/@whiskeysockets/baileys": {"version": "7.0.0-rc.9"}}
            }))
            patch_file = HERE / "patch-baileys-rc9.cjs"
            changes = PREPARO.preparar(source, patch_file, dry_run=True)
            self.assertEqual(len(changes), 2)
            self.assertFalse((source / "emeca-patches").exists())
            PREPARO.preparar(source, patch_file, dry_run=False)
            actual = (source / "Dockerfile").read_text()
            self.assertIn("RUN node emeca-patches/patch-baileys-rc9.cjs", actual)
            self.assertTrue((source / "emeca-patches" / "patch-baileys-rc9.cjs").exists())
            self.assertEqual(PREPARO.preparar(source, patch_file, dry_run=False), [])

    def test_manifesto_nao_rc9_e_rejeitado(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            docker = source / "Dockerfile"
            docker.write_text("RUN npx prisma generate && npm run build\n")
            (source / "package.json").write_text(json.dumps({
                "dependencies": {"@whiskeysockets/baileys": "7.0.0-rc14"}
            }))
            (source / "package-lock.json").write_text(json.dumps({
                "packages": {"node_modules/@whiskeysockets/baileys": {"version": "7.0.0-rc14"}}
            }))
            with self.assertRaises(RuntimeError):
                PREPARO.preparar(source, HERE / "patch-baileys-rc9.cjs", dry_run=False)
            self.assertEqual(docker.read_text(), "RUN npx prisma generate && npm run build\n")


if __name__ == "__main__":
    unittest.main()
