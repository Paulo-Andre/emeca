from django.conf import settings
from django.db import migrations, models


def migrar_leituras_anteriores(apps, schema_editor):
    Leitura = apps.get_model("usuarioSec", "LeituraChatWhatsApp")
    sessao_anterior = getattr(settings, "WA_AKG_SESSION_ID", "") or ""
    Leitura.objects.filter(sessao="").update(sessao=sessao_anterior)


class Migration(migrations.Migration):
    dependencies = [("usuarioSec", "0011_estado_conversa_whatsapp")]

    operations = [
        migrations.CreateModel(
            name="SessaoWhatsAppAtiva",
            fields=[
                ("chave", models.CharField(default="secretaria", max_length=40, primary_key=True, serialize=False)),
                ("sessao_id", models.CharField(max_length=120, unique=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Sessão WhatsApp ativa",
                "verbose_name_plural": "Sessões WhatsApp ativas",
            },
        ),
        migrations.AddField(
            model_name="leiturachatwhatsapp",
            name="sessao",
            field=models.CharField(default="", max_length=120),
        ),
        migrations.RunPython(migrar_leituras_anteriores, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="leiturachatwhatsapp",
            name="uniq_leitura_whatsapp_usuario_jid",
        ),
        migrations.AddConstraint(
            model_name="leiturachatwhatsapp",
            constraint=models.UniqueConstraint(
                fields=("usuario", "sessao", "jid"),
                name="uniq_leitura_whatsapp_usuario_sessao_jid",
            ),
        ),
    ]
