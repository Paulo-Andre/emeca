from django.conf import settings
from django.db import models

# Create your models here.

class declaracao(models.Model):

    # ================= ALUNO =================

    nomeDoAluno = models.CharField(max_length=255)
    nacionaliadeAluno = models.CharField(max_length=100, blank=True, null=True)
    natularidadeAluno = models.CharField(max_length=100, blank=True, null=True)
    ufAluno = models.CharField(max_length=10, blank=True, null=True)
    dataNascimentoAluno = models.DateField(blank=True, null=True)
    sexoDoAluno = models.CharField(max_length=20, blank=True, null=True)
    turmaDoAluno = models.CharField(max_length=50, blank=True, null=True)
    cartaoSusDoAluno = models.CharField(max_length=30, blank=True, null=True)
    cpfDoAluno = models.CharField(max_length=14, blank=True, null=True)
    nomePai = models.CharField(max_length=255, blank=True, null=True)
    cpfPai = models.CharField(max_length=14, blank=True, null=True)
    nomeMae = models.CharField(max_length=255, blank=True, null=True)
    cpfMae = models.CharField(max_length=14, blank=True, null=True)
    nomeResponsavel = models.CharField(max_length=255, blank=True, null=True)
    cpfResponsavel = models.CharField(max_length=14, blank=True, null=True)
    
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nomeDoAluno


class TelefoneDeclaracao(models.Model):
    TIPOS = [
        ("PAI", "Pai"),
        ("MAE", "Mãe"),
        ("RESPONSAVEL", "Responsável"),
    ]

    declaracao = models.ForeignKey(
        declaracao,
        on_delete=models.CASCADE,
        related_name="telefones",
    )
    tipo = models.CharField(max_length=20, choices=TIPOS)
    telefone = models.CharField(max_length=20)

    class Meta:
        ordering = ["tipo", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["declaracao", "tipo", "telefone"],
                name="uniq_telefone_por_responsavel_declaracao",
            )
        ]
        verbose_name = "Telefone da declaração"
        verbose_name_plural = "Telefones da declaração"

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.telefone}"


class EnvioBoletimWhatsApp(models.Model):
    STATUS = [
        ("PENDENTE", "Pendente"),
        ("PROCESSANDO", "Processando"),
        ("CONCLUIDO", "Concluído"),
        ("COM_ERROS", "Concluído com erros"),
        ("FALHOU", "Falhou"),
    ]
    MODOS = [
        ("todos", "Todos"),
        ("turma", "Por turma"),
        ("individual", "Individual"),
    ]

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="envios_boletim_whatsapp",
    )
    tipo_periodo = models.CharField(max_length=12)
    numero_periodo = models.PositiveSmallIntegerField()
    ano = models.PositiveSmallIntegerField()
    modo = models.CharField(max_length=12, choices=MODOS)
    turma = models.CharField(max_length=160, blank=True)
    mensagem = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STATUS, default="PENDENTE")
    total = models.PositiveIntegerField(default=0)
    enviados = models.PositiveIntegerField(default=0)
    falhas = models.PositiveIntegerField(default=0)
    ignorados = models.PositiveIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)
    iniciado_em = models.DateTimeField(blank=True, null=True)
    concluido_em = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "Envio de boletim por WhatsApp"
        verbose_name_plural = "Envios de boletim por WhatsApp"

    @property
    def periodo_rotulo(self):
        nome = "Bimestre" if self.tipo_periodo == "BIMESTRE" else "Trimestre"
        return f"{self.numero_periodo}º {nome}"

    def __str__(self):
        return f"{self.periodo_rotulo} / {self.ano} - {self.get_status_display()}"


class ItemEnvioBoletimWhatsApp(models.Model):
    STATUS = [
        ("PENDENTE", "Pendente"),
        ("PROCESSANDO", "Processando"),
        ("ENVIADO", "Enviado"),
        ("ERRO", "Erro"),
    ]

    envio = models.ForeignKey(
        EnvioBoletimWhatsApp,
        on_delete=models.CASCADE,
        related_name="itens",
    )
    boletim = models.ForeignKey(
        "site_publico.BoletimAluno",
        on_delete=models.CASCADE,
        related_name="envios_whatsapp",
    )
    jid = models.CharField(max_length=80)
    tipo_contato = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=16, choices=STATUS, default="PENDENTE")
    erro = models.CharField(max_length=500, blank=True)
    enviado_em = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["envio", "boletim", "jid"],
                name="uniq_boletim_jid_por_envio_whatsapp",
            )
        ]
        verbose_name = "Item de envio de boletim por WhatsApp"
        verbose_name_plural = "Itens de envio de boletim por WhatsApp"

    def __str__(self):
        return f"{self.boletim.aluno.nome} - {self.get_status_display()}"


class SecurityRateLimit(models.Model):
    chave = models.CharField(max_length=64, unique=True)
    janela_inicio = models.DateTimeField()
    contador = models.PositiveIntegerField(default=0)
    bloqueado_ate = models.DateTimeField(blank=True, null=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Limite de segurança"
        verbose_name_plural = "Limites de segurança"

    def __str__(self):
        return f"{self.chave[:12]}… ({self.contador})"


class LeituraChatWhatsApp(models.Model):
    """Estado de leitura local do atendimento, por usuário e conversa.

    O WA-AKG não expõe contadores de não lidas em seu endpoint de chats.
    A primeira sincronização estabelece uma referência; os contadores
    posteriores são baseados apenas nas mensagens recebidas após ela.
    """

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="leituras_chats_whatsapp",
    )
    jid = models.CharField(max_length=120)
    ultima_verificacao_em = models.DateTimeField(blank=True, null=True)
    nao_lidas = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "jid"],
                name="uniq_leitura_whatsapp_usuario_jid",
            )
        ]
        verbose_name = "Leitura de conversa WhatsApp"
        verbose_name_plural = "Leituras de conversas WhatsApp"

    def __str__(self):
        return f"{self.usuario_id}: {self.jid} ({self.nao_lidas})"


class IdentidadeContatoWhatsApp(models.Model):
    """Associação verificada entre LID, telefone e apelido interno do atendimento.

    A API do WA-AKG pode retornar um LID sem o número telefônico; nunca
    converter os dígitos do LID em número. Associações manuais são persistentes.
    """

    sessao = models.CharField(max_length=120)
    jid = models.CharField(max_length=120)
    telefone_jid = models.CharField(max_length=120, blank=True)
    nome_exibicao = models.CharField(max_length=160, blank=True)
    origem = models.CharField(
        max_length=12,
        choices=[("MANUAL", "Confirmado pelo operador"), ("METADATA", "Dados WhatsApp")],
        default="MANUAL",
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sessao", "jid"],
                name="uniq_identidade_wa_sessao_jid",
            )
        ]
        verbose_name = "Identidade de contato WhatsApp"
        verbose_name_plural = "Identidades de contatos WhatsApp"

    def __str__(self):
        return f"{self.sessao}: {self.jid} => {self.telefone_jid or self.nome_exibicao}"


class ContatoAgendaWhatsApp(models.Model):
    """Contato importado da agenda Android, independente das mensagens WA-AKG.

    Nunca identifica @lid sem correspondência telefônica comprovada.
    """
    sessao = models.CharField(max_length=120)
    telefone_jid = models.CharField(max_length=40)
    nome = models.CharField(max_length=160)
    origem = models.CharField(max_length=24, default="ANDROID_VCF")
    importado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sessao", "telefone_jid"],
                name="uniq_agenda_wa_sessao_telefone",
            )
        ]
        indexes = [
            models.Index(fields=["sessao", "telefone_jid"], name="idx_agenda_wa_telefone")
        ]
        verbose_name = "Contato importado da agenda WhatsApp"
        verbose_name_plural = "Contatos importados da agenda WhatsApp"

    def __str__(self):
        return f"{self.nome} ({self.telefone_jid})"
