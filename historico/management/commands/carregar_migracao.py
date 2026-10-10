import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from historico.models import Aluno, ConfiguracaoAno, RegistroAcademico, Nota

class Command(BaseCommand):
    help = "Carrega o pacote de migração gerado do sistema legado. Não lê arquivos Excel."

    def add_arguments(self, parser):
        parser.add_argument("arquivo", nargs="?", default="data/migracao_inicial_historico_egidio.json")

    @transaction.atomic
    def handle(self, *args, **opts):
        path = Path(opts["arquivo"])
        if not path.exists():
            raise SystemExit(f"Pacote de migração não encontrado: {path}")

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        Nota.objects.all().delete()
        RegistroAcademico.objects.all().delete()
        ConfiguracaoAno.objects.all().delete()
        Aluno.objects.all().delete()

        alunos = []
        for item in data.get("alunos", []):
            alunos.append(Aluno(
                codigo=item["codigo"],
                nome=item.get("nome", ""),
                uf=item.get("uf", ""),
                pai=item.get("pai", ""),
                mae=item.get("mae", ""),
                nascimento=item.get("nascimento", ""),
                naturalidade=item.get("naturalidade", ""),
                nacionalidade=item.get("nacionalidade", ""),
                sexo=item.get("sexo", ""),
            ))
        Aluno.objects.bulk_create(alunos, batch_size=1000)
        mapa_alunos = {a.codigo: a for a in Aluno.objects.all()}

        configs = []
        for item in data.get("parametros_ano", []):
            configs.append(ConfiguracaoAno(
                ano=item["ano"],
                ch_ingles=str(item.get("ch_ingles") or ""),
                ch_anual=str(item.get("ch_anual") or ""),
                dias_letivos=str(item.get("dias_letivos") or ""),
                ch_sem_ingles=str(item.get("ch_sem_ingles") or ""),
                media_minima=str(item.get("media") or ""),
                escola=str(item.get("escola") or ""),
            ))
        ConfiguracaoAno.objects.bulk_create(configs, batch_size=100)

        total_registros = 0
        total_notas = 0
        for item in data.get("registros_academicos", []):
            aluno = mapa_alunos.get(item.get("aluno_codigo"))
            config = next((c for c in configs if c.ano == item["ano"]), None)
            registro = RegistroAcademico.objects.create(
                aluno=aluno,
                nome_original=item.get("nome_original", ""),
                ano=item["ano"],
                serie=item.get("serie"),
                turma=item.get("turma", ""),
                faltas=str(item.get("faltas") or ""),
                resultado=str(item.get("resultado") or ""),
                escola=(config.escola if config else ""),
                linha_origem=item.get("linha_origem"),
            )
            notas = [
                Nota(registro=registro, componente=comp, valor=str(valor if valor is not None else ""))
                for comp, valor in item.get("notas", {}).items()
            ]
            Nota.objects.bulk_create(notas, batch_size=100)
            total_registros += 1
            total_notas += len(notas)

        self.stdout.write(self.style.SUCCESS(
            f"Migração concluída: {Aluno.objects.count()} alunos, "
            f"{total_registros} registros acadêmicos e {total_notas} notas."
        ))
