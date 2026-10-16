from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("cadastro", "0007_matricula_escolaanterioraluno"),
        ("site_publico", "0009_albumgaleria_foto_capa"),
    ]

    operations = [
        migrations.CreateModel(
            name="AlunoBoletim",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=255)),
                ("data_nascimento", models.DateField(blank=True, null=True)),
                ("cpf_mae", models.CharField(blank=True, max_length=20)),
                ("cpf_responsavel", models.CharField(blank=True, max_length=20)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("matricula", models.OneToOneField(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="perfil_boletim",
                    to="cadastro.matricula",
                )),
            ],
            options={
                "verbose_name": "Aluno de boletim",
                "verbose_name_plural": "Alunos de boletim",
                "ordering": ["nome"],
            },
        ),
        migrations.CreateModel(
            name="PeriodoBoletim",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(choices=[("BIMESTRE", "Bimestre"), ("TRIMESTRE", "Trimestre")], max_length=12)),
                ("numero", models.PositiveSmallIntegerField()),
                ("ano", models.PositiveSmallIntegerField()),
                ("turma", models.CharField(max_length=160)),
                ("regente", models.CharField(blank=True, max_length=180)),
                ("publicado", models.BooleanField(default=False)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Período de boletim",
                "verbose_name_plural": "Períodos de boletim",
                "ordering": ["-ano", "tipo", "numero", "turma"],
            },
        ),
        migrations.CreateModel(
            name="DisciplinaBoletim",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=160)),
                ("ordem", models.PositiveSmallIntegerField(default=0)),
                ("periodo", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="disciplinas", to="site_publico.periodoboletim")),
            ],
            options={
                "verbose_name": "Disciplina do boletim",
                "verbose_name_plural": "Disciplinas do boletim",
                "ordering": ["ordem", "id"],
            },
        ),
        migrations.CreateModel(
            name="BoletimAluno",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero_chamada", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("aluno", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="boletins", to="site_publico.alunoboletim")),
                ("periodo", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="boletins", to="site_publico.periodoboletim")),
            ],
            options={
                "verbose_name": "Boletim do aluno",
                "verbose_name_plural": "Boletins dos alunos",
                "ordering": ["numero_chamada", "aluno__nome"],
            },
        ),
        migrations.CreateModel(
            name="NotaBoletim",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nota", models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ("faltas", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("boletim", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="resultados", to="site_publico.boletimaluno")),
                ("disciplina", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="resultados", to="site_publico.disciplinaboletim")),
            ],
            options={
                "verbose_name": "Nota do boletim",
                "verbose_name_plural": "Notas do boletim",
                "ordering": ["disciplina__ordem", "disciplina__id"],
            },
        ),
        migrations.AddConstraint(
            model_name="periodoboletim",
            constraint=models.UniqueConstraint(fields=("tipo", "numero", "ano", "turma"), name="uniq_periodo_boletim_turma"),
        ),
        migrations.AddConstraint(
            model_name="disciplinaboletim",
            constraint=models.UniqueConstraint(fields=("periodo", "nome"), name="uniq_disciplina_periodo_boletim"),
        ),
        migrations.AddConstraint(
            model_name="boletimaluno",
            constraint=models.UniqueConstraint(fields=("periodo", "aluno"), name="uniq_boletim_aluno_periodo"),
        ),
        migrations.AddConstraint(
            model_name="notaboletim",
            constraint=models.UniqueConstraint(fields=("boletim", "disciplina"), name="uniq_nota_disciplina_boletim"),
        ),
    ]
