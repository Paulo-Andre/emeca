from django.conf import settings
from django.db import migrations, models


def associar_fila_antiga(apps, schema_editor):
    Envio = apps.get_model("usuarioSec", "EnvioBoletimWhatsApp")
    sessao_antiga = getattr(settings, "WA_AKG_SESSION_ID", "") or ""
    # A fila já existente pertence à sessão histórica, mesmo se uma conta
    # nova estiver conectada depois. Não a reatribuir ao número atual.
    Envio.objects.filter(sessao="").update(sessao=sessao_antiga)


class Migration(migrations.Migration):
    dependencies = [("usuarioSec", "0012_sessao_whatsapp_isolada")]

    operations = [
        migrations.AddField(
            model_name="envioboletimwhatsapp",
            name="sessao",
            field=models.CharField(default="", max_length=120),
        ),
        migrations.RunPython(associar_fila_antiga, migrations.RunPython.noop),
    ]
