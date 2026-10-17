from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("usuarioSec", "0014_etiqueta_conversa_whatsapp"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MensagemOcultaWhatsApp",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sessao", models.CharField(max_length=120)),
                ("mensagem_id", models.CharField(max_length=190)),
                ("ocultada_em", models.DateTimeField(auto_now_add=True)),
                ("usuario", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="mensagens_ocultas_whatsapp",
                    to=settings.AUTH_USER_MODEL
                )),
            ],
            options={
                "verbose_name": "Mensagem oculta no EMECA",
                "verbose_name_plural": "Mensagens ocultas no EMECA",
            },
        ),
        migrations.AddConstraint(
            model_name="mensagemocultawhatsapp",
            constraint=models.UniqueConstraint(
                fields=("usuario", "sessao", "mensagem_id"),
                name="uniq_mensagem_oculta_wa_operador"
            ),
        ),
    ]
