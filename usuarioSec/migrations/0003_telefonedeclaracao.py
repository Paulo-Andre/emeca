from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("usuarioSec", "0002_rename_declaração_declaracao")]

    operations = [
        migrations.CreateModel(
            name="TelefoneDeclaracao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(
                    choices=[
                        ("PAI", "Pai"),
                        ("MAE", "Mãe"),
                        ("RESPONSAVEL", "Responsável"),
                    ],
                    max_length=20,
                )),
                ("telefone", models.CharField(max_length=20)),
                ("declaracao", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="telefones",
                    to="usuarioSec.declaracao",
                )),
            ],
            options={
                "verbose_name": "Telefone da declaração",
                "verbose_name_plural": "Telefones da declaração",
                "ordering": ["tipo", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="telefonedeclaracao",
            constraint=models.UniqueConstraint(
                fields=("declaracao", "tipo", "telefone"),
                name="uniq_telefone_por_responsavel_declaracao",
            ),
        ),
    ]
