from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("usuarioSec", "0013_sessao_envios_whatsapp")]

    operations = [
        migrations.CreateModel(
            name="EtiquetaConversaWhatsApp",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sessao", models.CharField(max_length=120)),
                ("jid", models.CharField(max_length=120)),
                ("etiqueta_id", models.CharField(max_length=120)),
                ("nome", models.CharField(max_length=100)),
                ("cor", models.CharField(default="#94a3b8", max_length=16)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Etiqueta de conversa WhatsApp",
                "verbose_name_plural": "Etiquetas de conversas WhatsApp",
            },
        ),
        migrations.AddConstraint(
            model_name="etiquetaconversawhatsapp",
            constraint=models.UniqueConstraint(
                fields=("sessao", "jid", "etiqueta_id"),
                name="uniq_etiqueta_conversa_wa",
            ),
        ),
        migrations.AddIndex(
            model_name="etiquetaconversawhatsapp",
            index=models.Index(
                fields=["sessao", "jid"], name="idx_etiqueta_wa_sessao_jid"
            ),
        ),
    ]
