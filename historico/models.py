import uuid

from django.conf import settings
from django.db import models


class Aluno(models.Model):
    codigo = models.PositiveIntegerField(unique=True, db_index=True)
    nome = models.CharField(max_length=255, db_index=True)
    matricula = models.CharField(max_length=50, blank=True)
    cpf = models.CharField(max_length=14, blank=True)
    curso = models.CharField(max_length=120, blank=True, default="ENSINO FUNDAMENTAL")
    identidade = models.CharField(max_length=40, blank=True)
    orgao_expedidor = models.CharField(max_length=80, blank=True)
    data_conclusao = models.CharField(max_length=30, blank=True)
    serie_conclusao = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Série de conclusão no certificado",
        help_text=(
            "Valor opcional exibido na linha de conclusão do certificado, "
            "mesmo quando não há relação acadêmica ativa para a série."
        ),
    )
    data_expedicao = models.CharField(max_length=30, blank=True)
    observacao_historico = models.TextField(blank=True)
    uf = models.CharField(max_length=10, blank=True)
    pai = models.CharField(max_length=255, blank=True)
    mae = models.CharField(max_length=255, blank=True)
    nascimento = models.CharField(max_length=30, blank=True)
    naturalidade = models.CharField(max_length=120, blank=True)
    nacionalidade = models.CharField(max_length=120, blank=True)
    sexo = models.CharField(max_length=30, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return f"{self.codigo} - {self.nome}"


class ConfiguracaoAno(models.Model):
    ano = models.PositiveIntegerField(unique=True)
    ch_ingles = models.CharField(max_length=30, blank=True)
    ch_anual = models.CharField(max_length=30, blank=True)
    dias_letivos = models.CharField(max_length=30, blank=True)
    ch_sem_ingles = models.CharField(max_length=30, blank=True)
    media_minima = models.CharField(max_length=30, blank=True)
    data_conclusao = models.CharField(max_length=30, blank=True)
    escola = models.CharField(max_length=255, blank=True)
    municipio = models.CharField(max_length=120, default="MONTES CLAROS")
    uf = models.CharField(max_length=2, default="MG")
    matriz_curricular = models.ForeignKey(
        "MatrizCurricularVersao",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="configuracoes_anuais",
    )

    class Meta:
        ordering = ["ano"]

    def __str__(self):
        return str(self.ano)


class MatrizCurricularVersao(models.Model):
    codigo = models.CharField(max_length=40, unique=True)
    nome = models.CharField(max_length=160)
    vigente_de = models.PositiveIntegerField(db_index=True)
    vigente_ate = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    descricao = models.TextField(blank=True)
    ativa = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-vigente_de", "codigo"]
        verbose_name = "Versão da matriz curricular"
        verbose_name_plural = "Versões da matriz curricular"

    def __str__(self):
        intervalo = (
            f"{self.vigente_de}-{self.vigente_ate}"
            if self.vigente_ate
            else f"{self.vigente_de}+"
        )
        return f"{self.codigo} · {self.nome} ({intervalo})"


class MatrizComponente(models.Model):
    matriz = models.ForeignKey(
        MatrizCurricularVersao,
        on_delete=models.CASCADE,
        related_name="componentes",
    )
    componente = models.CharField(max_length=40)
    nome_exibicao = models.CharField(max_length=120)
    carga_horaria = models.CharField(max_length=30, blank=True)
    peso = models.DecimalField(max_digits=7, decimal_places=3, default=1)
    ordem = models.PositiveSmallIntegerField(default=0)
    obrigatorio = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordem", "nome_exibicao"]
        constraints = [
            models.UniqueConstraint(
                fields=["matriz", "componente"],
                name="uniq_matriz_componente",
            )
        ]

    def __str__(self):
        return f"{self.matriz.codigo} · {self.nome_exibicao}"


class RegistroAcademico(models.Model):
    aluno = models.ForeignKey(
        Aluno,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registros_academicos",
    )
    nome_original = models.CharField(max_length=255, blank=True)
    ano = models.PositiveIntegerField(db_index=True)
    serie = models.PositiveSmallIntegerField(null=True, blank=True)
    turma = models.CharField(max_length=120, blank=True)
    professor_responsavel = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Professor(a) responsável",
    )
    faltas = models.CharField(max_length=40, blank=True)
    frequencia = models.CharField(max_length=30, blank=True)
    carga_horaria = models.CharField(max_length=30, blank=True)
    resultado = models.CharField(max_length=80, blank=True)
    escola = models.CharField(max_length=255, blank=True)
    municipio = models.CharField(max_length=120, default="MONTES CLAROS")
    uf = models.CharField(max_length=2, default="MG")
    linha_origem = models.PositiveIntegerField(null=True, blank=True)
    observacao = models.TextField(blank=True)
    ativo_no_historico = models.BooleanField(
        default=True,
        db_index=True,
        help_text=(
            "Somente relações ativas entram no Histórico Escolar oficial. "
            "Desativar não remove notas nem apaga o registro."
        ),
    )
    matriz_curricular = models.ForeignKey(
        MatrizCurricularVersao,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="registros_academicos",
    )

    class Meta:
        ordering = ["ano", "serie", "turma", "nome_original"]
        constraints = [
            models.UniqueConstraint(
                fields=["ano", "linha_origem"],
                name="uniq_registro_ano_linha",
            ),
            models.UniqueConstraint(
                fields=["aluno", "serie"],
                condition=models.Q(
                    ativo_no_historico=True,
                    aluno__isnull=False,
                    serie__isnull=False,
                ),
                name="uniq_registro_ativo_aluno_serie",
            ),
        ]
        indexes = [
            models.Index(
                fields=["aluno", "ano", "serie"],
                name="hist_reg_aluno_ano_serie_idx",
            ),
            models.Index(
                fields=["ano", "serie", "turma"],
                name="hist_reg_ano_serie_turma_idx",
            ),
        ]

    def __str__(self):
        nome = self.aluno.nome if self.aluno_id else self.nome_original
        return f"{self.ano} - {nome}"


class Nota(models.Model):
    ARTE = "arte"
    CIENCIAS = "ciencias"
    EDUCACAO_FISICA = "educacao_fisica"
    EDUCACAO_RELIGIOSA = "educacao_religiosa"
    GEOGRAFIA = "geografia"
    HISTORIA = "historia"
    LINGUA_INGLESA = "lingua_inglesa"
    MATEMATICA = "matematica"
    LINGUA_PORTUGUESA = "lingua_portuguesa"

    COMPONENTES = [
        (ARTE, "Arte"),
        (CIENCIAS, "Ciências"),
        (EDUCACAO_FISICA, "Educação Física"),
        (EDUCACAO_RELIGIOSA, "Educação Religiosa"),
        (GEOGRAFIA, "Geografia"),
        (HISTORIA, "História"),
        (LINGUA_INGLESA, "Língua Inglesa"),
        (MATEMATICA, "Matemática"),
        (LINGUA_PORTUGUESA, "Língua Portuguesa/Literatura"),
    ]

    registro = models.ForeignKey(
        RegistroAcademico,
        on_delete=models.CASCADE,
        related_name="notas",
    )
    componente = models.CharField(max_length=40, choices=COMPONENTES)
    valor = models.CharField(max_length=40, blank=True)
    carga_horaria = models.CharField(max_length=30, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["registro", "componente"],
                name="uniq_nota_registro_componente",
            )
        ]

    def __str__(self):
        return f"{self.get_componente_display()}: {self.valor}"


class DocumentoHistorico(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    aluno = models.ForeignKey(
        Aluno,
        on_delete=models.PROTECT,
        related_name="documentos_emitidos",
    )
    emitido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="historicos_emitidos",
    )
    emitido_em = models.DateTimeField(auto_now_add=True, db_index=True)
    hash_sha256 = models.CharField(max_length=64, db_index=True)
    assinatura_hmac = models.CharField(max_length=64)
    snapshot = models.JSONField()
    revogado = models.BooleanField(default=False)
    revogado_em = models.DateTimeField(null=True, blank=True)
    motivo_revogacao = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-emitido_em"]

    def __str__(self):
        return f"{self.aluno.nome} · {self.emitido_em:%d/%m/%Y %H:%M}"


class AuditoriaEvento(models.Model):
    ACAO_CHOICES = [
        ("REQUEST_SENSIVEL", "Requisição sensível"),
        ("ALUNO_CRIADO", "Aluno criado"),
        ("ALUNO_ALTERADO", "Aluno alterado"),
        ("NOTAS_ALTERADAS", "Notas alteradas"),
        ("IMPORTACAO_ALUNOS", "Importação de alunos"),
        ("IMPORTACAO_NOTAS", "Importação de notas"),
        ("HISTORICO_EMITIDO", "Histórico emitido"),
        ("HISTORICO_VISUALIZADO", "Histórico visualizado"),
        ("DOCUMENTO_REVOGADO", "Documento revogado"),
    ]

    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_auditoria",
    )
    acao = models.CharField(max_length=40, choices=ACAO_CHOICES, db_index=True)
    entidade = models.CharField(max_length=80, blank=True, db_index=True)
    objeto_id = models.CharField(max_length=80, blank=True)
    objeto_repr = models.CharField(max_length=255, blank=True)
    metodo = models.CharField(max_length=10, blank=True)
    caminho = models.CharField(max_length=255, blank=True)
    ip_hash = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    request_id = models.UUIDField(null=True, blank=True, db_index=True)
    detalhes = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(
                fields=["acao", "criado_em"],
                name="historico_a_acao_8cc985_idx",
            ),
            models.Index(
                fields=["entidade", "objeto_id"],
                name="historico_a_entidad_65ea04_idx",
            ),
        ]

    def __str__(self):
        return f"{self.criado_em:%d/%m/%Y %H:%M} · {self.get_acao_display()}"
