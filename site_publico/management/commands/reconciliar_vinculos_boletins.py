"""Concilia perfis de boletim com Declarações já existentes.

Simulação por padrão. Nunca altera dados cadastrais, notas, faltas ou publicação.
"""
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from site_publico.boletim_importacao import normalizar_nome
from site_publico.boletim_services import sincronizar_perfil_declaracao, somente_digitos
from site_publico.models import AlunoBoletim
from usuarioSec.models import declaracao


def planejar():
    registros = defaultdict(list)
    for d in declaracao.objects.all().only(
        "id", "nomeDoAluno", "dataNascimentoAluno", "cpfMae", "cpfResponsavel"
    ):
        registros[normalizar_nome(d.nomeDoAluno)].append(d)
    perfis = list(AlunoBoletim.objects.filter(boletins__isnull=False)
                   .select_related("declaracao").distinct().order_by("pk"))
    usados = {p.declaracao_id for p in perfis if p.declaracao_id}
    acoes, pendencias = [], []
    for p in perfis:
        candidatos = registros.get(normalizar_nome(p.nome), [])
        if p.declaracao_id:
            d = p.declaracao
            if d and normalizar_nome(p.nome) == normalizar_nome(d.nomeDoAluno):
                if p.data_nascimento and d.dataNascimentoAluno and p.data_nascimento != d.dataNascimentoAluno:
                    pendencias.append((p.pk, "Nascimento divergente"))
                elif not d.dataNascimentoAluno:
                    pendencias.append((p.pk, "Nascimento ausente na Declaração"))
                elif not any(len(somente_digitos(x)) == 11 for x in (d.cpfMae, d.cpfResponsavel)):
                    pendencias.append((p.pk, "CPF da mãe/responsável ausente"))
                else:
                    acoes.append((p.pk, d.pk, "sincronizar"))
            else:
                pendencias.append((p.pk, "Vínculo existente exige revisão manual"))
            continue
        if len(candidatos) != 1:
            pendencias.append((p.pk, "Sem nome idêntico" if not candidatos else "Nome duplicado"))
            continue
        d = candidatos[0]
        if d.pk in usados:
            pendencias.append((p.pk, "Declaração já vinculada a outro perfil"))
        elif not d.dataNascimentoAluno:
            pendencias.append((p.pk, "Nascimento ausente na Declaração"))
        elif p.data_nascimento and p.data_nascimento != d.dataNascimentoAluno:
            pendencias.append((p.pk, "Nascimento divergente"))
        elif not any(len(somente_digitos(x)) == 11 for x in (d.cpfMae, d.cpfResponsavel)):
            pendencias.append((p.pk, "CPF da mãe/responsável ausente"))
        else:
            acoes.append((p.pk, d.pk, "vincular"))
            usados.add(d.pk)
    return acoes, pendencias


class Command(BaseCommand):
    help = "Simula vínculos dos boletins a Declarações; --aplicar exige confirmação e não publica boletins."

    def add_arguments(self, parser):
        parser.add_argument("--aplicar", action="store_true")
        parser.add_argument("--confirmar", default="")

    def handle(self, *args, **opts):
        if opts["aplicar"] and opts["confirmar"] != "VINCULAR-SEM-PUBLICAR":
            self.stderr.write("Confirmação ausente. Nada alterado.")
            return
        acoes, pendencias = planejar()
        contagem = Counter(motivo for _, motivo in pendencias)
        self.stdout.write(f"PERFIS APTOS: {len(acoes)}")
        self.stdout.write(f"PENDÊNCIAS: {len(pendencias)}")
        for motivo, total in sorted(contagem.items()):
            self.stdout.write(f"  {motivo}: {total}")
        if not opts["aplicar"]:
            self.stdout.write("SIMULAÇÃO: nenhum dado alterado.")
            return
        with transaction.atomic():
            novas_acoes, _ = planejar()
            if novas_acoes != acoes:
                raise ValueError("O conjunto de vínculos mudou. Refazer simulação.")
            for perfil_id, declaracao_id, _ in acoes:
                perfil = AlunoBoletim.objects.select_for_update().get(pk=perfil_id)
                fonte = declaracao.objects.get(pk=declaracao_id)
                if perfil.declaracao_id and perfil.declaracao_id != fonte.pk:
                    raise ValueError("Conflito de vínculo; nenhuma alteração aplicada.")
                sincronizar_perfil_declaracao(perfil, fonte)
        self.stdout.write(f"CONCLUÍDO: {len(acoes)} perfis conferidos/vinculados.")
        self.stdout.write("Boletins continuam PRIVADOS até publicação explícita pela Secretaria.")
