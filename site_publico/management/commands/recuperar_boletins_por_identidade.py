"""Recupera exclusivamente boletins cuja identidade tenha correspondência forte.

Compara NOME NORMALIZADO + DATA DE NASCIMENTO do cadastro de Declarações
entre backup e banco atual. Nunca reutiliza IDs antigos de alunos, boletins
ou notas. Não altera boletins existentes, Declarações, outros períodos ou WA.
Itens ambíguos não são importados. Execução sem --aplicar é simulação.
"""
import os
import re
import sqlite3
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from site_publico.models import (
    AlunoBoletim, BoletimAluno, NotaBoletim, PeriodoBoletim, DisciplinaBoletim,
)

FONTE = "antes-atualizacao-validado-W7A2S2.sqlite3"
PID = 3
TABLE_B = "site_publico_boletimaluno"
TABLE_N = "site_publico_notaboletim"
TABLE_A = "site_publico_alunoboletim"
TABLE_P = "site_publico_periodoboletim"
TABLE_D = "site_publico_disciplinaboletim"
TABLE_DECL = "usuarioSec_declaracao"


def _nome(valor):
    normal = unicodedata.normalize("NFKD", str(valor or "").upper())
    sem_acento = "".join(c for c in normal if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", sem_acento)).strip()


def _nasc(valor):
    return str(valor.isoformat() if hasattr(valor, "isoformat") else (valor or "")).strip()[:10]


def _chave(nome, nascimento):
    n, d = _nome(nome), _nasc(nascimento)
    return (n, d) if n and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) else None


def _tabela(conexao, nome):
    cursor = conexao.execute("SELECT * FROM " + nome)
    colunas = [x[0] for x in cursor.description]
    return {int(linha[colunas.index("id")]): dict(zip(colunas, linha)) for linha in cursor.fetchall()}


def _abrir_ro(arquivo):
    uri = "file:" + quote(str(arquivo), safe="/") + "?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=20)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _snapshot_atual():
    root = Path("/backups")
    src = Path(settings.DATABASES["default"]["NAME"])
    if not root.is_dir() or not src.is_file():
        raise CommandError("Backup ou banco atual indisponível; nenhuma alteração.")
    nome = "emeca-antes-recuperacao-identidade-" + datetime.now(
        timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".sqlite3"
    destino = root / nome
    os.umask(0o077)
    fd = os.open(destino, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        src_uri = "file:" + quote(str(src), safe="/") + "?mode=ro"
        with sqlite3.connect(src_uri, uri=True, timeout=20) as entrada:
            with sqlite3.connect(str(destino), timeout=20) as saida:
                entrada.backup(saida, pages=256, sleep=0.10)
                if saida.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise CommandError("Snapshot atual não passou no quick_check")
        os.chmod(destino, 0o600)
    except Exception:
        destino.unlink(missing_ok=True)
        raise
    return nome


class Command(BaseCommand):
    help = "Repor somente boletins do período 3 com nome e nascimento únicos e idênticos ao backup"

    def add_arguments(self, parser):
        parser.add_argument("--aplicar", action="store_true",
                            help="Criar cópia do banco e repor apenas os vínculos fortes")

    def handle(self, *args, **opts):
        if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError("Somente banco SQLite é suportado.")
        caminhos = [p for p in Path("/backups").rglob(FONTE)
                    if p.is_file() and not p.is_symlink()]
        if len(caminhos) != 1:
            raise CommandError("Backup histórico único não foi encontrado; nenhuma alteração.")

        with _abrir_ro(caminhos[0]) as backup:
            if backup.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise CommandError("Backup histórico inválido.")
            oldb = _tabela(backup, TABLE_B)
            olda = _tabela(backup, TABLE_A)
            oldd = _tabela(backup, TABLE_DECL)
            oldp = _tabela(backup, TABLE_P)
            olddisc = _tabela(backup, TABLE_D)
            oldn = _tabela(backup, TABLE_N)

        periodo = PeriodoBoletim.objects.filter(pk=PID).first()
        ref_periodo = oldp.get(PID)
        if not periodo or not ref_periodo or (
            periodo.tipo, periodo.numero, periodo.ano, periodo.turma
        ) != (
            ref_periodo["tipo"], ref_periodo["numero"], ref_periodo["ano"],
            ref_periodo["turma"],
        ):
            raise CommandError("Período escolar não coincide com o backup. Não restaurado.")

        boletins = [b for b in oldb.values() if int(b["periodo_id"]) == PID]
        if len(boletins) != 27:
            raise CommandError("Backup não contém exatamente 27 boletins do período.")
        existentes = list(
            BoletimAluno.objects.filter(periodo_id=PID)
            .select_related("aluno__declaracao")
        )
        if not 3 <= len(existentes) <= 27:
            raise CommandError("Estado atual inesperado; não alterar.")
        # Identificar os atuais sem depender de PK; preservar notas já editadas.
        chaves_existentes = []
        for b in existentes:
            decl = b.aluno.declaracao
            key = _chave(decl.nomeDoAluno, decl.dataNascimentoAluno) if decl else None
            if not key:
                raise CommandError("Boletim atual com identidade incompleta.")
            chaves_existentes.append(key)
        if len(set(chaves_existentes)) != len(chaves_existentes):
            raise CommandError("Identidades duplicadas no período atual.")

        # Cadastro atual deve ter chave única por nome+nascimento.
        por_identidade = defaultdict(list)
        for perfil in AlunoBoletim.objects.select_related("declaracao").filter(
            declaracao__isnull=False
        ):
            decl = perfil.declaracao
            key = _chave(decl.nomeDoAluno, decl.dataNascimentoAluno)
            if key:
                por_identidade[key].append(perfil)

        origem_chaves = {}
        for b in boletins:
            perfil = olda.get(int(b["aluno_id"]))
            decl = oldd.get(int(perfil["declaracao_id"])) if (
                perfil and perfil.get("declaracao_id") is not None
            ) else None
            key = _chave(decl.get("nomeDoAluno"), decl.get("dataNascimentoAluno")) if decl else None
            fallback = _chave(perfil.get("nome"), perfil.get("data_nascimento")) if perfil else None
            origem_chaves[b["id"]] = (key, fallback)
        declaradas = [k for k, fb in origem_chaves.values() if k]
        if len(set(declaradas)) != len(declaradas):
            raise CommandError("Backup com identidades repetidas; recuperação bloqueada.")
        if not set(chaves_existentes).issubset(set(declaradas)):
            raise CommandError("Boletins ainda existentes não correspondem à identidade histórica.")

        disciplinas_atuais = defaultdict(list)
        for d in DisciplinaBoletim.objects.filter(periodo_id=PID):
            disciplinas_atuais[_nome(d.nome)].append(d)
        disciplinas_backup = defaultdict(list)
        for d in olddisc.values():
            if int(d["periodo_id"]) == PID:
                disciplinas_backup[_nome(d["nome"])].append(d)
        if set(disciplinas_backup) != set(disciplinas_atuais) or (
            any(len(v) != 1 for v in disciplinas_backup.values()) or
            any(len(v) != 1 for v in disciplinas_atuais.values())
        ):
            raise CommandError("Disciplinas divergentes ou ambíguas. Nenhuma alteração.")
        map_disciplinas = {
            int(d["id"]): disciplinas_atuais[_nome(d["nome"])][0]
            for d in olddisc.values() if int(d["periodo_id"]) == PID
        }
        notas_por_boletim = defaultdict(list)
        for n in oldn.values():
            notas_por_boletim[int(n["boletim_id"])].append(n)

        # Seleção uma a uma: se houver ambiguidades, nenhuma associação inferida.
        usados = set(chaves_existentes)
        itens = []
        pendentes = 0
        for b in sorted(boletins, key=lambda x: x["id"]):
            key, fallback = origem_chaves[b["id"]]
            if key in usados:
                continue
            if not key or len(por_identidade[key]) != 1:
                # Alternativa: nome e nascimento do perfil antigo devem coincidir
                # com a Declaração atual e com o próprio perfil atual.
                candidatos = por_identidade.get(fallback, []) if fallback else []
                candidatos = [p for p in candidatos if (
                    _chave(p.nome, p.data_nascimento) == fallback
                )]
                if len(candidatos) != 1:
                    pendentes += 1
                    continue
                key = fallback
            if key in usados or len(por_identidade[key]) != 1:
                pendentes += 1
                continue
            perfil = por_identidade[key][0]
            if BoletimAluno.objects.filter(periodo_id=PID, aluno_id=perfil.pk).exists():
                pendentes += 1
                continue
            notas = notas_por_boletim.get(int(b["id"]), [])
            if (len({int(n["disciplina_id"]) for n in notas}) != len(notas)
                or any(int(n["disciplina_id"]) not in map_disciplinas for n in notas)):
                raise CommandError("Notas não correspondem a disciplinas atuais. Não restaurado.")
            itens.append((key, perfil, b, notas))
            usados.add(key)

        if len(existentes) == 27:
            self.stdout.write("Todos os 27 boletins já existem. Nenhuma mudança necessária.")
            return
        if len(existentes) == 3 and len(itens) < 23:
            raise CommandError(
                "Menos de 23 vínculos com identidade forte. Nenhum boletim restaurado."
            )
        if len(existentes) + len(itens) > 27:
            raise CommandError("Contagem inesperada; recuperação cancelada.")
        self.stdout.write(
            f"Boletins atuais: {len(existentes)}; recuperáveis seguros: {len(itens)}; "
            f"dependentes de revisão: {pendentes}."
        )
        if not opts["aplicar"]:
            self.stdout.write("SIMULAÇÃO: nenhum dado foi alterado.")
            return
        if not itens:
            self.stdout.write("Nenhum vínculo seguro a acrescentar.")
            return

        copia = _snapshot_atual()
        self.stdout.write("Snapshot íntegro anterior ao reparo: " + copia)
        with transaction.atomic():
            ids_antes = set(BoletimAluno.objects.filter(
                periodo_id=PID).values_list("pk", flat=True))
            if ids_antes != {b.pk for b in existentes}:
                raise CommandError("Boletins foram alterados durante a análise.")
            for key, perfil, dados, notas in itens:
                boletim = BoletimAluno.objects.create(
                    periodo_id=PID,
                    aluno_id=perfil.pk,
                    numero_chamada=dados["numero_chamada"],
                    faltas_totais=dados["faltas_totais"],
                )
                for nota in notas:
                    NotaBoletim.objects.create(
                        boletim=boletim,
                        disciplina=map_disciplinas[int(nota["disciplina_id"])],
                        nota=nota["nota"],
                        faltas=nota["faltas"],
                    )
            total = BoletimAluno.objects.filter(periodo_id=PID).count()
            if total != len(existentes) + len(itens):
                raise CommandError("Contagem pós-recuperação incorreta. Transação revertida.")

        self.stdout.write(self.style.SUCCESS(
            f"REPOSIÇÃO SEGURA: {len(itens)} boletins acrescentados; "
            f"{pendentes} para revisão manual; {total} boletins no período. "
            "Nenhum boletim existente ou Declaração foi alterado."
        ))
