from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("historico", "0005_seguranca_auditoria_matriz_documentos"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="registroacademico",
            index=models.Index(
                fields=["aluno", "ano", "serie"],
                name="hist_reg_aluno_ano_serie_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="registroacademico",
            index=models.Index(
                fields=["ano", "serie", "turma"],
                name="hist_reg_ano_serie_turma_idx",
            ),
        ),
    ]
