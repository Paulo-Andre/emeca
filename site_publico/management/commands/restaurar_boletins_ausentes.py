"""Recuperação seletiva de lançamentos apagados acidentalmente.

Somente SQLite; escolhe backup válido de 27 boletins, cria snapshot do banco
atual e restaura APENAS BoletimAluno/NotaBoletim que estejam ausentes.
Nunca substitui a base inteira, nem dados das Declarações.
"""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from site_publico.models import (
    AlunoBoletim, BoletimAluno, DisciplinaBoletim, NotaBoletim,
    PeriodoBoletim,
)


TABLE_B = "site_publico_boletimaluno"
TABLE_N = "site_publico_notaboletim"
TABLE_A = "site_publico_alunoboletim"
TABLE_P = "site_publico_periodoboletim"
TABLE_D = "site_publico_disciplinaboletim"


def abrir_origem(path):
    uri = "file:" + quote(str(path), safe="/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def snapshot_atual(destino, origem):
    # Snapshot transacional da versão corrente; WAL é incluído corretamente.
    fd = os.open(destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        with abrir_origem(origem) as src, sqlite3.connect(str(destino)) as dst:
            src.backup(dst, pages=256, sleep=0.1)
            if dst.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise CommandError("Backup anterior à restauração não passou integridade")
    except Exception:
        destino.unlink(missing_ok=True)
        raise


def dados_backup(path):
    with abrir_origem(path) as conn:
        nomes = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if not {TABLE_B, TABLE_N, TABLE_A, TABLE_P, TABLE_D} <= nomes:
            return None
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            return None
        boletins = {
            int(row["id"]): dict(row)
            for row in conn.execute(
                "SELECT id, aluno_id, periodo_id, numero_chamada, faltas_totais "
                "FROM " + TABLE_B
            )
        }
        if len(boletins) != 27:
            return None
        alunos = {
            int(row["id"]): dict(row)
            for row in conn.execute(
                "SELECT id, declaracao_id FROM " + TABLE_A
            )
        }
        periodos = {
            int(row["id"]): dict(row)
            for row in conn.execute(
                "SELECT id, tipo, numero, ano, turma FROM " + TABLE_P
            )
        }
        disciplinas = {
            int(row["id"]): dict(row)
            for row in conn.execute("SELECT id, periodo_id FROM " + TABLE_D)
        }
        notas = [
            dict(row) for row in conn.execute(
                "SELECT id, boletim_id, disciplina_id, nota, faltas FROM " + TABLE_N
            )
        ]
    return (boletins, alunos, periodos, disciplinas, notas)


class Command(BaseCommand):
    help = "Restaura boletins ausentes de snapshot íntegro sem sobrescrever os atuais"

    def add_arguments(self, parser):
        parser.add_argument("--aplicar", action="store_true",
                            help="Permite gravação após snapshot, se todas as validações passarem")

    def handle(self, *args, **opts):
        if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError("Recuperação interrompida: banco não é SQLite")
        origem = Path(settings.DATABASES["default"]["NAME"])
        root = Path("/backups")
        if not origem.is_file() or not root.is_dir():
            raise CommandError("Banco atual ou diretório de backups indisponível")

        atuais = {
            b.pk: (b.periodo_id, b.aluno_id)
            for b in BoletimAluno.objects.only("id", "periodo_id", "aluno_id")
        }
        # Não recuperar automaticamente quando a situação é diferente daquela
        # diagnosticada: três atuais, histórico com 27 no backup.
        if len(atuais) != 3:
            raise CommandError(
                "Estado mudou: restauração automática só é permitida com 3 boletins atuais"
            )

        arquivos = sorted(
            (p for p in root.rglob("*.sqlite3")
             if p.is_file() and not p.is_symlink()
             and len(p.relative_to(root).parts) <= 4),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        selecionado = None
        dados = None
        for caminho in arquivos[:80]:
            try:
                candidato = dados_backup(caminho)
            except (sqlite3.Error, OSError, ValueError):
                continue
            if candidato is None:
                continue
            antigos = candidato[0]
            # Os boletins existentes devem ser exatamente os mesmos IDs e
            # vínculos do snapshot. Jamais misturar bases com IDs reutilizados.
            if all(i in antigos and (
                int(antigos[i]["periodo_id"]), int(antigos[i]["aluno_id"])
            ) == ref for i, ref in atuais.items()):
                selecionado, dados = caminho, candidato
                break
        if dados is None:
            raise CommandError(
                "Nenhum backup íntegro com 27 boletins e os 3 vínculos atuais; "
                "restauração cancelada para não misturar cadastros"
            )

        antigos, alunos_bkp, periodos_bkp, disciplinas_bkp, notas_bkp = dados
        faltantes = [b for i, b in sorted(antigos.items()) if i not in atuais]
        if len(faltantes) != 24:
            raise CommandError("Quantidade inesperada de boletins ausentes")
        alunos = {a.pk: a for a in AlunoBoletim.objects.all()}
        periodos = {p.pk: p for p in PeriodoBoletim.objects.all()}
        disciplinas = {d.pk: d for d in DisciplinaBoletim.objects.all()}
        ids_faltantes = {int(b["id"]) for b in faltantes}
        notas = [n for n in notas_bkp if int(n["boletim_id"]) in ids_faltantes]
        notas_atuais = set(NotaBoletim.objects.values_list("pk", flat=True))
        if any(int(n["id"]) in notas_atuais for n in notas):
            raise CommandError("Conflito de ID de nota; operação cancelada")

        for b in faltantes:
            a_id, p_id = int(b["aluno_id"]), int(b["periodo_id"])
            if a_id not in alunos or p_id not in periodos:
                raise CommandError("Aluno ou período ausente; não é seguro restaurar")
            anterior_a = alunos_bkp.get(a_id)
            anterior_p = periodos_bkp.get(p_id)
            atual_a, atual_p = alunos[a_id], periodos[p_id]
            if (not anterior_a or not anterior_p or
                anterior_a["declaracao_id"] != atual_a.declaracao_id or
                (anterior_p["tipo"], anterior_p["numero"],
                 anterior_p["ano"], anterior_p["turma"]) !=
                (atual_p.tipo, atual_p.numero, atual_p.ano, atual_p.turma)):
                raise CommandError("Vínculo do aluno ou período mudou; operação cancelada")
            if BoletimAluno.objects.filter(periodo_id=p_id, aluno_id=a_id).exists():
                raise CommandError("Já existe outro boletim para aluno/período")

        for n in notas:
            d_id, b_id = int(n["disciplina_id"]), int(n["boletim_id"])
            d = disciplinas.get(d_id)
            dbkp = disciplinas_bkp.get(d_id)
            if not d or not dbkp or (
                d.periodo_id != int(antigos[b_id]["periodo_id"])
                or d.periodo_id != int(dbkp["periodo_id"])
            ):
                raise CommandError("Disciplina mudou; não é seguro restaurar as notas")

        self.stdout.write("Boletins existentes preservados: 3")
        self.stdout.write("Boletins recuperáveis: 24")
        self.stdout.write("Lançamentos de notas/faltas recuperáveis: " + str(len(notas)))
        self.stdout.write("Referência válida: " + selecionado.name)
        if not opts["aplicar"]:
            self.stdout.write("SIMULAÇÃO APROVADA. Use --aplicar para recuperar.")
            return

        snapshot = root / (
            "emeca_antes_reposicao_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + ".sqlite3"
        )
        snapshot_atual(snapshot, origem)
        self.stdout.write("Snapshot de segurança criado: " + snapshot.name)

        with transaction.atomic():
            # Conferência final dentro da transação; impedir corrida com alteração
            # feita por outro operador entre a auditoria e o início da gravação.
            ultima = {
                b.pk: (b.periodo_id, b.aluno_id)
                for b in BoletimAluno.objects.only("id", "periodo_id", "aluno_id")
            }
            if ultima != atuais:
                raise CommandError("Os boletins foram alterados durante a verificação")
            for b in faltantes:
                BoletimAluno.objects.create(
                    id=int(b["id"]),
                    aluno_id=int(b["aluno_id"]),
                    periodo_id=int(b["periodo_id"]),
                    numero_chamada=b["numero_chamada"],
                    faltas_totais=b["faltas_totais"],
                )
            for n in notas:
                NotaBoletim.objects.create(
                    id=int(n["id"]),
                    boletim_id=int(n["boletim_id"]),
                    disciplina_id=int(n["disciplina_id"]),
                    nota=n["nota"],
                    faltas=n["faltas"],
                )
            if BoletimAluno.objects.count() != 27:
                raise CommandError("Contagem final incorreta; transação revertida")

        self.stdout.write(self.style.SUCCESS(
            "RECUPERAÇÃO CONCLUÍDA: 27 boletins, 24 restaurados, "
            + str(len(notas)) + " notas/faltas restauradas. "
            "Declarações e os 3 registros atuais foram preservados."
        ))
