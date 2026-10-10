# Generated to align the database schema with cadastro.models.matricula.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cadastro", "0006_matricula_cepaluno_matricula_descricaoalergia_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="matricula",
            name="escolaAnteriorAluno",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
