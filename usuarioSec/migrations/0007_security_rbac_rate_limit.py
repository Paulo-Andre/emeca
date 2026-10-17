from django.conf import settings
from django.db import migrations, models


GRUPOS = [
    "EMECA - Administração",
    "EMECA - Secretaria",
    "EMECA - Histórico",
    "EMECA - Boletins",
    "EMECA - Site",
    "EMECA - WhatsApp",
]


def criar_grupos_e_preservar_acessos(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)

    grupos = {}
    for nome in GRUPOS:
        grupo, _ = Group.objects.get_or_create(name=nome)
        grupos[nome] = grupo

    admin = grupos["EMECA - Administração"]
    for user in User.objects.filter(is_superuser=False):
        admin.user_set.add(user)


def remover_grupos(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=GRUPOS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("usuarioSec", "0006_envio_boletim_whatsapp"),
    ]

    operations = [
        migrations.CreateModel(
            name="SecurityRateLimit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("chave", models.CharField(max_length=64, unique=True)),
                ("janela_inicio", models.DateTimeField()),
                ("contador", models.PositiveIntegerField(default=0)),
                ("bloqueado_ate", models.DateTimeField(blank=True, null=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Limite de segurança",
                "verbose_name_plural": "Limites de segurança",
            },
        ),
        migrations.RunPython(criar_grupos_e_preservar_acessos, remover_grupos),
    ]
