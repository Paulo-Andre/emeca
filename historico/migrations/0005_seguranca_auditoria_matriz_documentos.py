import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("historico", "0004_configuracaoano_data_conclusao"),
    ]

    operations = [
        migrations.CreateModel(
            name="MatrizCurricularVersao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codigo", models.CharField(max_length=40, unique=True)),
                ("nome", models.CharField(max_length=160)),
                ("vigente_de", models.PositiveIntegerField(db_index=True)),
                ("vigente_ate", models.PositiveIntegerField(blank=True, db_index=True, null=True)),
                ("descricao", models.TextField(blank=True)),
                ("ativa", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Versão da matriz curricular",
                "verbose_name_plural": "Versões da matriz curricular",
                "ordering": ["-vigente_de", "codigo"],
            },
        ),
        migrations.CreateModel(
            name="MatrizComponente",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("componente", models.CharField(max_length=40)),
                ("nome_exibicao", models.CharField(max_length=120)),
                ("carga_horaria", models.CharField(blank=True, max_length=30)),
                ("peso", models.DecimalField(decimal_places=3, default=1, max_digits=7)),
                ("ordem", models.PositiveSmallIntegerField(default=0)),
                ("obrigatorio", models.BooleanField(default=True)),
                ("matriz", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="componentes", to="historico.matrizcurricularversao")),
            ],
            options={
                "ordering": ["ordem", "nome_exibicao"],
            },
        ),
        migrations.AddConstraint(
            model_name="matrizcomponente",
            constraint=models.UniqueConstraint(fields=("matriz", "componente"), name="uniq_matriz_componente"),
        ),
        migrations.AddField(
            model_name="configuracaoano",
            name="matriz_curricular",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="configuracoes_anuais", to="historico.matrizcurricularversao"),
        ),
        migrations.AddField(
            model_name="registroacademico",
            name="matriz_curricular",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="registros_academicos", to="historico.matrizcurricularversao"),
        ),
        migrations.CreateModel(
            name="DocumentoHistorico",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("emitido_em", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("hash_sha256", models.CharField(db_index=True, max_length=64)),
                ("assinatura_hmac", models.CharField(max_length=64)),
                ("snapshot", models.JSONField()),
                ("revogado", models.BooleanField(default=False)),
                ("revogado_em", models.DateTimeField(blank=True, null=True)),
                ("motivo_revogacao", models.CharField(blank=True, max_length=255)),
                ("aluno", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="documentos_emitidos", to="historico.aluno")),
                ("emitido_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="historicos_emitidos", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-emitido_em"],
            },
        ),
        migrations.CreateModel(
            name="AuditoriaEvento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("acao", models.CharField(choices=[("REQUEST_SENSIVEL", "Requisição sensível"), ("ALUNO_CRIADO", "Aluno criado"), ("ALUNO_ALTERADO", "Aluno alterado"), ("NOTAS_ALTERADAS", "Notas alteradas"), ("IMPORTACAO_ALUNOS", "Importação de alunos"), ("IMPORTACAO_NOTAS", "Importação de notas"), ("HISTORICO_EMITIDO", "Histórico emitido"), ("HISTORICO_VISUALIZADO", "Histórico visualizado"), ("DOCUMENTO_REVOGADO", "Documento revogado")], db_index=True, max_length=40)),
                ("entidade", models.CharField(blank=True, db_index=True, max_length=80)),
                ("objeto_id", models.CharField(blank=True, max_length=80)),
                ("objeto_repr", models.CharField(blank=True, max_length=255)),
                ("metodo", models.CharField(blank=True, max_length=10)),
                ("caminho", models.CharField(blank=True, max_length=255)),
                ("ip_hash", models.CharField(blank=True, max_length=64)),
                ("user_agent", models.CharField(blank=True, max_length=255)),
                ("request_id", models.UUIDField(blank=True, db_index=True, null=True)),
                ("detalhes", models.JSONField(blank=True, default=dict)),
                ("usuario", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="eventos_auditoria", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-criado_em"],
            },
        ),
        migrations.AddIndex(
            model_name="auditoriaevento",
            index=models.Index(fields=["acao", "criado_em"], name="historico_a_acao_8cc985_idx"),
        ),
        migrations.AddIndex(
            model_name="auditoriaevento",
            index=models.Index(fields=["entidade", "objeto_id"], name="historico_a_entidad_65ea04_idx"),
        ),
    ]
