# Contatos importados da agenda Android; não altera mensagens ou credenciais.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("usuarioSec", "0009_identidade_contato_whatsapp"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContatoAgendaWhatsApp",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sessao", models.CharField(max_length=120)),
                ("telefone_jid", models.CharField(max_length=40)),
                ("nome", models.CharField(max_length=160)),
                ("origem", models.CharField(default="ANDROID_VCF", max_length=24)),
                ("importado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Contato importado da agenda WhatsApp",
                "verbose_name_plural": "Contatos importados da agenda WhatsApp",
            },
        ),
        migrations.AddConstraint(
            model_name="contatoagendawhatsapp",
            constraint=models.UniqueConstraint(
                fields=("sessao", "telefone_jid"), name="uniq_agenda_wa_sessao_telefone"
            ),
        ),
        migrations.AddIndex(
            model_name="contatoagendawhatsapp",
            index=models.Index(
                fields=["sessao", "telefone_jid"], name="idx_agenda_wa_telefone"
            ),
        ),
    ]
