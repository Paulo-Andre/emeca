"""Vincula boletins existentes a Declarações somente quando não há ambiguidade.

A migração não cria nem apaga aluno, nota ou declaração. Perfis não vinculados
devem ser resolvidos manualmente antes de publicar períodos com pendências.
"""
import unicodedata

from django.db import migrations, models
import django.db.models.deletion


def normalizar(valor):
    texto = unicodedata.normalize("NFKD", valor or "")
    return " ".join("".join(c for c in texto if not unicodedata.combining(c)).casefold().split())


def vincular_perfis_inequivocos(apps, schema_editor):
    Perfil = apps.get_model("site_publico", "AlunoBoletim")
    Declaracao = apps.get_model("usuarioSec", "declaracao")
    mapa = {}
    contagem_perfis = {}
    for registro in Declaracao.objects.using(schema_editor.connection.alias).all().iterator():
        mapa.setdefault(normalizar(registro.nomeDoAluno), []).append(registro)
    for perfil in Perfil.objects.using(schema_editor.connection.alias).all().iterator():
        chave = normalizar(perfil.nome)
        contagem_perfis[chave] = contagem_perfis.get(chave, 0) + 1
    usados = set()
    for perfil in Perfil.objects.using(schema_editor.connection.alias).all().iterator():
        chave = normalizar(perfil.nome)
        candidatos = mapa.get(chave, [])
        if len(candidatos) != 1 or contagem_perfis[chave] != 1:
            continue
        declaracao = candidatos[0]
        if declaracao.pk in usados:
            continue
        if perfil.data_nascimento and declaracao.dataNascimentoAluno and perfil.data_nascimento != declaracao.dataNascimentoAluno:
            continue
        perfil.declaracao_id = declaracao.pk
        perfil.data_nascimento = declaracao.dataNascimentoAluno
        perfil.cpf_mae = declaracao.cpfMae or ""
        perfil.cpf_responsavel = declaracao.cpfResponsavel or ""
        perfil.save(update_fields=["declaracao", "data_nascimento", "cpf_mae", "cpf_responsavel"])
        usados.add(declaracao.pk)


class Migration(migrations.Migration):
    dependencies = [
        ("site_publico", "0012_validadores_upload_seguros"),
        ("usuarioSec", "0001_initial"),
    ]
    operations = [
        migrations.AddField(
            model_name="alunoboletim",
            name="declaracao",
            field=models.OneToOneField(
                to="usuarioSec.declaracao",
                on_delete=django.db.models.deletion.PROTECT,
                blank=True, null=True, related_name="perfil_boletim",
            ),
        ),
        migrations.RunPython(vincular_perfis_inequivocos, migrations.RunPython.noop),
    ]
