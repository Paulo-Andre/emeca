"""Testes offline do patch cirúrgico no uploader Baileys rc.9.

Não depende de rede, Docker, sessão, credenciais nem mídia de aluno.
"""
from __future__ import annotations
import importlib.util
import json
import shutil
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
        if shutil.which("node"):
            cmd = ["node", str(HERE / "patch-baileys-rc9.cjs"), str(root)]
        else:
            # No mini PC não é preciso instalar Node no host: usar a imagem
            # Docker existente, com fixture isolada e sem acesso ao WhatsApp.
            cmd = [
                "docker", "run", "--rm", "--network", "none",
                "-v", str(HERE) + ":/scripts:ro",
                "-v", str(root) + ":/fixture",
                "node:26-alpine", "node", "/scripts/patch-baileys-rc9.cjs", "/fixture",
            ]
        return subprocess.run(cmd, capture_output=True, text=True, check=False)

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


    def test_compilado_com_campo_de_confirmacao_ja_corrigido(self):
        # Reproduz a variação do JS compilado observada no contêiner:
        # não há a expressão exata antiga com result?.directPath.
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            compiled = FAKE_SOURCE.replace(
                "if (result?.url || result?.directPath) {",
                "if (result?.url || result?.direct_path) {",
            )
            source = self.create_pkg(folder, code=compiled)
            result = self.run_patch(folder)
            self.assertEqual(result.returncode, 0, result.stderr)
            patched = source.read_text()
            self.assertIn("'Content-Length': emecaEncryptedFileSize", patched)
            self.assertIn("WA-MEDIA-HTTP-DIAG", patched)
            self.assertEqual(self.run_patch(folder).returncode, 0)

    def test_compilado_com_condicao_desconhecida_conserva_condicao(self):
        # Não alterar uma condição compilada que não seja reconhecida.
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            compiled = FAKE_SOURCE.replace(
                "if (result?.url || result?.directPath) {",
                "if (result && result.url) {",
            )
            source = self.create_pkg(folder, code=compiled)
            result = self.run_patch(folder)
            self.assertEqual(result.returncode, 0, result.stderr)
            patched = source.read_text()
            self.assertIn("if (result && result.url) {", patched)
            self.assertIn("'Content-Length': emecaEncryptedFileSize", patched)

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
                "RUN npm prune --omit=dev && npm install --no-save tsx typescript\n"
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
            self.assertEqual(actual.count("RUN node emeca-patches/patch-baileys-rc9.cjs"), 2)
            self.assertTrue((source / "emeca-patches" / "patch-baileys-rc9.cjs").exists())
            self.assertEqual(PREPARO.preparar(source, patch_file, dry_run=False), [])

    def test_patch_residual_conhecido_pode_ser_atualizado(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "Dockerfile").write_text(
                "FROM node:26-alpine\n"
                "RUN npx prisma generate && npm run build\n"
                "RUN npm prune --omit=dev && npm install --no-save tsx typescript\n"
            )
            (source / "package.json").write_text(json.dumps({
                "dependencies": {"@whiskeysockets/baileys": "7.0.0-rc.9"}
            }))
            (source / "package-lock.json").write_text(json.dumps({
                "packages": {"node_modules/@whiskeysockets/baileys": {"version": "7.0.0-rc.9"}}
            }))
            legacy = source / "emeca-patches" / "patch-baileys-rc9.cjs"
            legacy.parent.mkdir()
            previous = "\n".join((
                "EMECA_BAILEYS_RC9_UPLOAD_V1",
                "Estrutura inesperada (",
                "if (result?.url || result?.directPath) {",
                "directPath: result.direct_path || result.directPath,",
                "WA-MEDIA-HTTP-DIAG",
            ))
            legacy.write_text(previous)
            changes = PREPARO.preparar(source, HERE / "patch-baileys-rc9.cjs", dry_run=True)
            self.assertEqual(len(changes), 2)
            self.assertEqual(legacy.read_text(), previous)
            PREPARO.preparar(source, HERE / "patch-baileys-rc9.cjs", dry_run=False)
            self.assertEqual(legacy.read_text(), (HERE / "patch-baileys-rc9.cjs").read_text())

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
