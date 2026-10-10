from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("historico", "0008_registroacademico_professor_responsavel"),
    ]

    operations = [
        migrations.AddField(
            model_name="aluno",
            name="serie_conclusao",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Valor opcional exibido na linha de conclusão do certificado, "
                    "mesmo quando não há relação acadêmica ativa para a série."
                ),
                max_length=20,
                verbose_name="Série de conclusão no certificado",
            ),
        ),
    ]
