# Associação persistente, por sessão, entre LID e telefone identificados.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("usuarioSec", "0008_leitura_chat_whatsapp"),
    ]

    operations = [
        migrations.CreateModel(
            name="IdentidadeContatoWhatsApp",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sessao", models.CharField(max_length=120)),
                ("jid", models.CharField(max_length=120)),
                ("telefone_jid", models.CharField(blank=True, max_length=120)),
                ("nome_exibicao", models.CharField(blank=True, max_length=160)),
                ("origem", models.CharField(choices=[("MANUAL", "Confirmado pelo operador"), ("METADATA", "Dados WhatsApp")], default="MANUAL", max_length=12)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Identidade de contato WhatsApp",
                "verbose_name_plural": "Identidades de contatos WhatsApp",
            },
        ),
        migrations.AddConstraint(
            model_name="identidadecontatowhatsapp",
            constraint=models.UniqueConstraint(fields=("sessao", "jid"), name="uniq_identidade_wa_sessao_jid"),
        ),
    ]
