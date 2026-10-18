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


if __name__ == "__main__":
    unittest.main()
