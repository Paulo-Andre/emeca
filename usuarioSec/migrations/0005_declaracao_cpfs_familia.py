from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("usuarioSec", "0004_declaracao_nome_responsavel")]

    operations = [
        migrations.AddField(
            model_name="declaracao",
            name="cpfPai",
            field=models.CharField(blank=True, max_length=14, null=True),
        ),
        migrations.AddField(
            model_name="declaracao",
            name="cpfMae",
            field=models.CharField(blank=True, max_length=14, null=True),
        ),
        migrations.AddField(
            model_name="declaracao",
            name="cpfResponsavel",
            field=models.CharField(blank=True, max_length=14, null=True),
        ),
    ]
