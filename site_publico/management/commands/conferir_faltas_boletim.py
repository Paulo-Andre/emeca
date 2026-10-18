"""Confere/reconcilia totais de faltas de um período com a coluna H da planilha.

Não recria boletins, não toca nas notas e não associa alunos automaticamente.
Sem --aplicar, apenas informa quantidades. Com --aplicar, exige backup prévio
e não altera nenhum registro caso a conferência tenha ambiguidades.
"""
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from site_publico.boletim_importacao import (
    ImportacaoBoletimErro,
    ler_planilha_boletim,
    normalizar_nome,
)
from site_publico.models import BoletimAluno, PeriodoBoletim


class Command(BaseCommand):
    help = (
        "Compara faltas atuais do boletim com a primeira falta (H) do XLS. "
        "Use --aplicar --backup-confirmado para corrigir apenas o campo total."
    )

    def add_arguments(self, parser):
        parser.add_argument("arquivo", help="Arquivo .xls/.xlsx do período.")
        parser.add_argument(
            "--periodo-id", required=True, type=int,
            help="ID exato do período de boletim a conferir.",
        )
        parser.add_argument(
            "--aplicar", action="store_true",
            help="Salva apenas as diferenças seguras de faltas totais.",
        )
        parser.add_argument(
            "--backup-confirmado", action="store_true",
            help="Confirma que existe backup restaurável do banco EMECA.",
        )

    def handle(self, *args, **options):
        caminho = Path(options["arquivo"])
        if not caminho.is_file():
            raise CommandError("A planilha não foi encontrada no caminho indicado.")
        if options["aplicar"] and not options["backup_confirmado"]:
            raise CommandError(
                "A correção exige backup prévio do banco. "
                "Utilize --backup-confirmado apenas depois de verificá-lo."
            )

        periodo = PeriodoBoletim.objects.filter(
            pk=options["periodo_id"],
        ).first()
        if periodo is None:
            raise CommandError("Período informado não existe.")

        try:
            with caminho.open("rb") as arquivo:
                dados = ler_planilha_boletim(arquivo)
        except ImportacaoBoletimErro as exc:
            raise CommandError(str(exc)) from exc

        meta = dados["metadados"]
        if (
            meta.get("tipo") != periodo.tipo
            or meta.get("numero") != periodo.numero
            or meta.get("ano") != periodo.ano
            or normalizar_nome(meta.get("turma"))
            != normalizar_nome(periodo.turma)
        ):
            raise CommandError(
                "Os metadados de organização, período, ano ou turma "
                "não correspondem ao registro selecionado. Nada foi alterado."
            )

        # A conciliação exige correspondência unívoca dentro do período,
        # usando o nome original do lançamento e, se houver, a chamada.
        registros = defaultdict(list)
        for boletim in BoletimAluno.objects.filter(
            periodo=periodo,
        ).select_related("aluno"):
            registros[normalizar_nome(boletim.aluno.nome)].append(boletim)

        contagem_linhas = defaultdict(int)
        for aluno in dados["alunos"]:
            contagem_linhas[normalizar_nome(aluno["nome"])] += 1

        divergencias = []
        problemas = 0
        iguais = 0
        for aluno in dados["alunos"]:
            chave = normalizar_nome(aluno["nome"])
            candidatos = registros.get(chave, [])
            if len(candidatos) != 1 or contagem_linhas[chave] != 1:
                problemas += 1
                continue
            boletim = candidatos[0]
            chamada_planilha = aluno.get("numero_chamada")
            if (
                chamada_planilha is not None and
                boletim.numero_chamada is not None and
                chamada_planilha != boletim.numero_chamada
            ):
                problemas += 1
                continue
            esperado = aluno.get("faltas_totais")
            if esperado is None:
                problemas += 1
                continue
            if boletim.faltas_totais == esperado:
                iguais += 1
            else:
                divergencias.append((boletim.pk, esperado))

        # Boletins sem linha correspondente também precisam ser avaliados
        # antes de realizar uma correção em massa.
        chaves_planilha = set(contagem_linhas)
        for chave, boletins in registros.items():
            if chave not in chaves_planilha:
                problemas += len(boletins)

        self.stdout.write(
            "Conferência de faltas pela coluna H: "
            f"{iguais} corretos, {len(divergencias)} divergentes, "
            f"{problemas} pendentes de revisão."
        )
        if periodo.publicado:
            self.stdout.write(
                "Aviso: período publicado. PDFs já enviados não serão "
                "modificados retroativamente."
            )
        if not options["aplicar"]:
            self.stdout.write(
                "Prévia concluída: nenhum dado foi modificado. "
                "Revise as pendências e faça backup antes de aplicar."
            )
            return

        if problemas:
            raise CommandError(
                "Existem alunos sem correspondência segura. "
                "Correção em lote cancelada; nenhum dado foi modificado."
            )

        with transaction.atomic():
            bloqueados = {
                obj.pk: obj for obj in
                BoletimAluno.objects.select_for_update().filter(
                    periodo=periodo,
                    pk__in=[pk for pk, _ in divergencias],
                )
            }
            if len(bloqueados) != len(divergencias):
                raise CommandError(
                    "Um boletim mudou desde a conferência. "
                    "Nenhum dado foi modificado."
                )
            for pk, faltas in divergencias:
                boletim = bloqueados[pk]
                boletim.faltas_totais = faltas
                boletim.save(update_fields=["faltas_totais", "atualizado_em"])

        self.stdout.write(self.style.SUCCESS(
            f"{len(divergencias)} total(is) de faltas corrigido(s). "
            "Notas, vínculos e demais informações foram preservados."
        ))
