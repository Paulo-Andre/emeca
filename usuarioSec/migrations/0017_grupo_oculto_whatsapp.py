from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("usuarioSec", "0016_conversa_excluida_whatsapp"),
    ]

    operations = [
        migrations.CreateModel(
            name="GrupoOcultoWhatsApp",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sessao", models.CharField(max_length=120)),
                ("jid", models.CharField(max_length=120)),
                ("motivo", models.CharField(default="REMOVIDO", max_length=20)),
                ("ocultado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Grupo removido da lista EMECA",
                "verbose_name_plural": "Grupos removidos da lista EMECA",
            },
        ),
        migrations.AddConstraint(
            model_name="grupoocultowhatsapp",
            constraint=models.UniqueConstraint(
                fields=("sessao", "jid"), name="uniq_grupo_oculto_wa_sessao"
            ),
        ),
    ]
