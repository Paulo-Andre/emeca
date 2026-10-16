from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("usuarioSec", "0003_telefonedeclaracao")]

    operations = [
        migrations.AddField(
            model_name="declaracao",
            name="nomeResponsavel",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
