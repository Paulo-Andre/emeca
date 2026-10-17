from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("usuarioSec", "0017_grupo_oculto_whatsapp")]

    operations = [
        migrations.AddField(
            model_name="sessaowhatsappativa",
            name="limpeza_pendente",
            field=models.BooleanField(default=False),
        ),
    ]
