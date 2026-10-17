from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("usuarioSec", "0010_contato_agenda_whatsapp"),
    ]

    operations = [
        migrations.CreateModel(
            name="EstadoConversaWhatsApp",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sessao", models.CharField(max_length=120)),
                ("jid", models.CharField(max_length=120)),
                ("fixado", models.BooleanField(default=False)),
                ("silenciado", models.BooleanField(default=False)),
                ("arquivado", models.BooleanField(default=False)),
                ("bloqueado", models.BooleanField(default=False)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Estado de conversa WhatsApp",
                "verbose_name_plural": "Estados de conversas WhatsApp",
            },
        ),
        migrations.AddConstraint(
            model_name="estadoconversawhatsapp",
            constraint=models.UniqueConstraint(
                fields=("sessao", "jid"), name="uniq_estado_conversa_whatsapp"
            ),
        ),
    ]
