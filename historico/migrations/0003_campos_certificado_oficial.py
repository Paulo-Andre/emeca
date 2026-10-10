from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("historico", "0002_editor_documento"),
    ]

    operations = [
        migrations.AddField(
            model_name="aluno",
            name="identidade",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="aluno",
            name="orgao_expedidor",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="aluno",
            name="data_conclusao",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="aluno",
            name="data_expedicao",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="aluno",
            name="observacao_historico",
            field=models.TextField(blank=True),
        ),
    ]
