"""Verificação sintética do leitor de backups, sem banco de produção."""
import sqlite3
from tempfile import TemporaryDirectory
from pathlib import Path

from django.test import SimpleTestCase

from site_publico.management.commands.restaurar_boletins_ausentes import (
    dados_backup, snapshot_atual
)


class ValidacaoBackupBoletinsTests(SimpleTestCase):
    def montar(self, path, n):
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE site_publico_boletimaluno "
                       "(id INTEGER PRIMARY KEY, aluno_id INTEGER, periodo_id INTEGER,"
                       " numero_chamada INTEGER, faltas_totais INTEGER)")
            db.execute("CREATE TABLE site_publico_notaboletim "
                       "(id INTEGER PRIMARY KEY, boletim_id INTEGER,"
                       " disciplina_id INTEGER, nota NUMERIC, faltas INTEGER)")
            db.execute("CREATE TABLE site_publico_alunoboletim "
                       "(id INTEGER PRIMARY KEY, declaracao_id INTEGER)")
            db.execute("CREATE TABLE site_publico_periodoboletim "
                       "(id INTEGER PRIMARY KEY, tipo TEXT, numero INTEGER,"
                       " ano INTEGER, turma TEXT)")
            db.execute("CREATE TABLE site_publico_disciplinaboletim "
                       "(id INTEGER PRIMARY KEY, periodo_id INTEGER)")
            db.execute("INSERT INTO site_publico_periodoboletim VALUES "
                       "(3,'TRIMESTRE',2,2026,'TURMA SINTETICA')")
            db.execute("INSERT INTO site_publico_disciplinaboletim VALUES (9,3)")
            for i in range(1,n+1):
                db.execute("INSERT INTO site_publico_alunoboletim VALUES (?, NULL)",(i,))
                db.execute("INSERT INTO site_publico_boletimaluno VALUES (?,?,3,?,0)",
                           (i,i,i))
                db.execute("INSERT INTO site_publico_notaboletim VALUES (?,?,9,8,0)",
                           (i,i))

    def test_carrega_27_boletins_e_notas(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/"backup.sqlite3"
            self.montar(path,27)
            x=dados_backup(path)
            self.assertEqual(len(x[0]),27)
            self.assertEqual(len(x[4]),27)
            self.assertEqual(x[0][27]["aluno_id"],27)

    def test_descarta_snapshot_incompleto(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/"backup.sqlite3"
            self.montar(path,3)
            self.assertIsNone(dados_backup(path))

    def test_snapshot_original_continua_intacto(self):
        with TemporaryDirectory() as tmp:
            origem=Path(tmp)/"original.sqlite3"
            destino=Path(tmp)/"snapshot.sqlite3"
            self.montar(origem,27)
            snapshot_atual(destino,origem)
            self.assertIsNotNone(dados_backup(destino))
            self.assertIsNotNone(dados_backup(origem))
