"""QA com dados fictícios para o ensaio de restauração do pacote."""
import io
import sqlite3
import tarfile
import tempfile
import unittest
from pathlib import Path

from validar_backups_lote import validar_pacote, validar_sqlite, validar_tar_gzip


class ValidacaoBackupsTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.raiz = Path(self._temp.name)

    def criar_sqlite(self, nome="emeca.sqlite3"):
        caminho = self.raiz / nome
        with sqlite3.connect(caminho) as con:
            con.execute("CREATE TABLE aluno_ficticio (id INTEGER)")
            con.execute("INSERT INTO aluno_ficticio VALUES (1)")
        return caminho

    def criar_tar(self, nome, entrada="media/documento-ficticio.txt"):
        destino = self.raiz / nome
        with tarfile.open(destino, "w:gz") as arq:
            dados = b"conteudo sintetico"
            item = tarfile.TarInfo(entrada)
            item.size = len(dados)
            arq.addfile(item, io.BytesIO(dados))
        return destino

    def test_restaura_sqlite_de_forma_isolada(self):
        caminho = self.criar_sqlite()
        validar_sqlite(caminho)
        self.assertTrue(caminho.is_file())

    def test_rejeita_sqlite_corrompido(self):
        caminho = self.raiz / "emeca.sqlite3"
        caminho.write_bytes(b"isto nao e um sqlite")
        with self.assertRaises(sqlite3.DatabaseError):
            validar_sqlite(caminho)

    def test_rejeita_tar_com_caminho_inseguro(self):
        caminho = self.criar_tar("mau.tar.gz", "../segredo")
        with self.assertRaisesRegex(RuntimeError, "inseguro"):
            validar_tar_gzip(caminho)

    def test_pacote_valido_com_dump_sintetico(self):
        self.criar_sqlite()
        self.criar_tar("emeca-media.tar.gz")
        self.criar_tar("wa-akg-volumes.tar.gz", "data/sessao-ficticia")
        (self.raiz / "wa-akg.sql").write_bytes(
            b"-- Dump synthetic\nCREATE TABLE teste (id int);\n"
            b"-- Dump completed on 2026-10-18 00:00:00\n"
        )
        validar_pacote(self.raiz)

    def test_pacote_rejeita_dump_incompleto(self):
        self.criar_sqlite()
        self.criar_tar("emeca-media.tar.gz")
        self.criar_tar("wa-akg-volumes.tar.gz")
        (self.raiz / "wa-akg.sql").write_bytes(b"CREATE TABLE apenas_parte")
        with self.assertRaisesRegex(RuntimeError, "conclusão"):
            validar_pacote(self.raiz)

    def test_instalador_precria_snapshot_no_host_e_exige_proprietario(self):
        # Regressão de produção: se sqlite3.backup cria o arquivo como root
        # dentro do container, o usuário SSH não lê a cópia 0600 e o
        # instalador falha depois de gerar os backups.
        script = (Path(__file__).resolve().parents[1]
                  / "deploy" / "atualizar_lote_seguro.sh").read_text(
                      encoding="utf-8",
                  )
        criar = 'install -m 600 /dev/null "$DEST/emeca.sqlite3"'
        executar = 'docker compose exec -T web python - "$SQLITE_SNAPSHOT_REL"'
        conferir = 'test -r "$DEST/emeca.sqlite3" || falhar'
        self.assertIn(criar, script)
        self.assertIn(executar, script)
        self.assertIn(conferir, script)
        self.assertLess(script.index(criar), script.index(executar))
        self.assertIn('stat -c %u "$DEST/emeca.sqlite3"', script)

    def test_sqlite_backup_para_arquivo_precriado_nao_troca_inode(self):
        origem = self.criar_sqlite()
        destino = self.raiz / "snapshot-precriado.sqlite3"
        destino.touch(mode=0o600)
        inode_original = destino.stat().st_ino
        with sqlite3.connect(origem) as banco, sqlite3.connect(destino) as copia:
            banco.backup(copia)
        self.assertEqual(inode_original, destino.stat().st_ino)
        with sqlite3.connect(destino) as banco:
            self.assertEqual(
                banco.execute("PRAGMA quick_check").fetchone(),
                ("ok",),
            )


if __name__ == "__main__":
    unittest.main()
