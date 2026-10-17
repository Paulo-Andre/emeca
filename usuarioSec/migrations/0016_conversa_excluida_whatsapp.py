from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("usuarioSec", "0015_mensagem_oculta_whatsapp"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ConversaExcluidaWhatsApp",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sessao", models.CharField(max_length=120)),
                ("jid", models.CharField(max_length=120)),
                ("ultima_mensagem_em", models.CharField(max_length=60, blank=True, default="")),
                ("excluida_em", models.DateTimeField(auto_now=True)),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="conversas_excluidas_whatsapp", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Conversa excluída no EMECA",
                "verbose_name_plural": "Conversas excluídas no EMECA",
            },
        ),
        migrations.AddConstraint(
            model_name="conversaexcluidawhatsapp",
            constraint=models.UniqueConstraint(
                fields=("usuario", "sessao", "jid"),
                name="uniq_conversa_excluida_wa_operador",
            ),
        ),
    ]
