from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("historico", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="aluno",
            name="cpf",
            field=models.CharField(blank=True, max_length=14),
        ),
        migrations.AddField(
            model_name="aluno",
            name="curso",
            field=models.CharField(
                blank=True,
                default="ENSINO FUNDAMENTAL",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="aluno",
            name="matricula",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="registroacademico",
            name="carga_horaria",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="registroacademico",
            name="frequencia",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="nota",
            name="carga_horaria",
            field=models.CharField(blank=True, max_length=30),
        ),
    ]
