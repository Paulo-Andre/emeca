# Generated manually for WhatsApp bulletin delivery queue.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("site_publico", "0011_boletimaluno_faltas_totais"),
        ("usuarioSec", "0005_declaracao_cpfs_familia"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EnvioBoletimWhatsApp",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo_periodo", models.CharField(max_length=12)),
                ("numero_periodo", models.PositiveSmallIntegerField()),
                ("ano", models.PositiveSmallIntegerField()),
                ("modo", models.CharField(choices=[("todos", "Todos"), ("turma", "Por turma"), ("individual", "Individual")], max_length=12)),
                ("turma", models.CharField(blank=True, max_length=160)),
                ("mensagem", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("PENDENTE", "Pendente"), ("PROCESSANDO", "Processando"), ("CONCLUIDO", "Concluído"), ("COM_ERROS", "Concluído com erros"), ("FALHOU", "Falhou")], default="PENDENTE", max_length=16)),
                ("total", models.PositiveIntegerField(default=0)),
                ("enviados", models.PositiveIntegerField(default=0)),
                ("falhas", models.PositiveIntegerField(default=0)),
                ("ignorados", models.PositiveIntegerField(default=0)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("iniciado_em", models.DateTimeField(blank=True, null=True)),
                ("concluido_em", models.DateTimeField(blank=True, null=True)),
                ("usuario", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="envios_boletim_whatsapp", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Envio de boletim por WhatsApp",
                "verbose_name_plural": "Envios de boletim por WhatsApp",
                "ordering": ["-criado_em"],
            },
        ),
        migrations.CreateModel(
            name="ItemEnvioBoletimWhatsApp",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("jid", models.CharField(max_length=80)),
                ("tipo_contato", models.CharField(blank=True, max_length=20)),
                ("status", models.CharField(choices=[("PENDENTE", "Pendente"), ("PROCESSANDO", "Processando"), ("ENVIADO", "Enviado"), ("ERRO", "Erro")], default="PENDENTE", max_length=16)),
                ("erro", models.CharField(blank=True, max_length=500)),
                ("enviado_em", models.DateTimeField(blank=True, null=True)),
                ("boletim", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="envios_whatsapp", to="site_publico.boletimaluno")),
                ("envio", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="itens", to="usuarioSec.envioboletimwhatsapp")),
            ],
            options={
                "verbose_name": "Item de envio de boletim por WhatsApp",
                "verbose_name_plural": "Itens de envio de boletim por WhatsApp",
                "ordering": ["id"],
            },
        ),
        migrations.AddConstraint(
            model_name="itemenvioboletimwhatsapp",
            constraint=models.UniqueConstraint(fields=("envio", "boletim", "jid"), name="uniq_boletim_jid_por_envio_whatsapp"),
        ),
    ]
