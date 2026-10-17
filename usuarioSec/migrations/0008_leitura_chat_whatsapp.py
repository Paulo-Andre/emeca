# Controle persistente de mensagens novas na caixa de atendimento WhatsApp.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("usuarioSec", "0007_security_rbac_rate_limit"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LeituraChatWhatsApp",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("jid", models.CharField(max_length=120)),
                ("ultima_verificacao_em", models.DateTimeField(blank=True, null=True)),
                ("nao_lidas", models.PositiveIntegerField(default=0)),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="leituras_chats_whatsapp", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Leitura de conversa WhatsApp",
                "verbose_name_plural": "Leituras de conversas WhatsApp",
            },
        ),
        migrations.AddConstraint(
            model_name="leiturachatwhatsapp",
            constraint=models.UniqueConstraint(fields=("usuario", "jid"), name="uniq_leitura_whatsapp_usuario_jid"),
        ),
    ]
