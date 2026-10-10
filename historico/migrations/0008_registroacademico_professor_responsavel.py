from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("historico", "0007_relacao_academica_ativa"),
    ]

    operations = [
        migrations.AddField(
            model_name="registroacademico",
            name="professor_responsavel",
            field=models.CharField(
                blank=True,
                max_length=255,
                verbose_name="Professor(a) responsável",
            ),
        ),
    ]
