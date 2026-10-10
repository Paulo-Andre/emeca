from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Aluno",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codigo", models.PositiveIntegerField(db_index=True, unique=True)),
                ("nome", models.CharField(db_index=True, max_length=255)),
                ("uf", models.CharField(blank=True, max_length=10)),
                ("pai", models.CharField(blank=True, max_length=255)),
                ("mae", models.CharField(blank=True, max_length=255)),
                ("nascimento", models.CharField(blank=True, max_length=30)),
                ("naturalidade", models.CharField(blank=True, max_length=120)),
                ("nacionalidade", models.CharField(blank=True, max_length=120)),
                ("sexo", models.CharField(blank=True, max_length=30)),
                ("ativo", models.BooleanField(default=True)),
            ],
            options={"ordering": ["nome"]},
        ),
        migrations.CreateModel(
            name="ConfiguracaoAno",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ano", models.PositiveIntegerField(unique=True)),
                ("ch_ingles", models.CharField(blank=True, max_length=30)),
                ("ch_anual", models.CharField(blank=True, max_length=30)),
                ("dias_letivos", models.CharField(blank=True, max_length=30)),
                ("ch_sem_ingles", models.CharField(blank=True, max_length=30)),
                ("media_minima", models.CharField(blank=True, max_length=30)),
                ("escola", models.CharField(blank=True, max_length=255)),
                ("municipio", models.CharField(default="MONTES CLAROS", max_length=120)),
                ("uf", models.CharField(default="MG", max_length=2)),
            ],
            options={"ordering": ["ano"]},
        ),
        migrations.CreateModel(
            name="RegistroAcademico",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome_original", models.CharField(blank=True, max_length=255)),
                ("ano", models.PositiveIntegerField(db_index=True)),
                ("serie", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("turma", models.CharField(blank=True, max_length=120)),
                ("faltas", models.CharField(blank=True, max_length=40)),
                ("resultado", models.CharField(blank=True, max_length=80)),
                ("escola", models.CharField(blank=True, max_length=255)),
                ("municipio", models.CharField(default="MONTES CLAROS", max_length=120)),
                ("uf", models.CharField(default="MG", max_length=2)),
                ("linha_origem", models.PositiveIntegerField(blank=True, null=True)),
                ("observacao", models.TextField(blank=True)),
                ("aluno", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="registros_academicos", to="historico.aluno")),
            ],
            options={
                "ordering": ["ano", "serie", "turma", "nome_original"],
                "constraints": [models.UniqueConstraint(fields=("ano", "linha_origem"), name="uniq_registro_ano_linha")],
            },
        ),
        migrations.CreateModel(
            name="Nota",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("componente", models.CharField(choices=[
                    ("arte", "Arte"), ("ciencias", "Ciências"), ("educacao_fisica", "Educação Física"),
                    ("educacao_religiosa", "Educação Religiosa"), ("geografia", "Geografia"), ("historia", "História"),
                    ("lingua_inglesa", "Língua Inglesa"), ("matematica", "Matemática"),
                    ("lingua_portuguesa", "Língua Portuguesa/Literatura")
                ], max_length=40)),
                ("valor", models.CharField(blank=True, max_length=40)),
                ("registro", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notas", to="historico.registroacademico")),
            ],
            options={
                "constraints": [models.UniqueConstraint(fields=("registro", "componente"), name="uniq_nota_registro_componente")],
            },
        ),
    ]
