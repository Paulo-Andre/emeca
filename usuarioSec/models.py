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
    sessao = models.CharField(max_length=120, default="")
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
    sessao = models.CharField(max_length=120, default="")
    jid = models.CharField(max_length=120)
    ultima_verificacao_em = models.DateTimeField(blank=True, null=True)
    nao_lidas = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "sessao", "jid"],
                name="uniq_leitura_whatsapp_usuario_sessao_jid",
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


class EstadoConversaWhatsApp(models.Model):
    """Últimos comandos de organização confirmados pelo WA-AKG, por sessão.

    Estes valores refletem as ações realizadas no EMECA; se o estado for
    modificado no telefone, o WA-AKG precisa sincronizar o novo estado.
    """
    sessao = models.CharField(max_length=120)
    jid = models.CharField(max_length=120)
    fixado = models.BooleanField(default=False)
    silenciado = models.BooleanField(default=False)
    arquivado = models.BooleanField(default=False)
    bloqueado = models.BooleanField(default=False)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sessao", "jid"], name="uniq_estado_conversa_whatsapp"
            )
        ]
        verbose_name = "Estado de conversa WhatsApp"
        verbose_name_plural = "Estados de conversas WhatsApp"


class SessaoWhatsAppAtiva(models.Model):
    """Aponta para a sessão isolada atualmente usada pela Secretaria.

    Ao trocar de conta o apontador muda; o banco antigo do WA-AKG permanece
    arquivado na sessão anterior, sem copiar conversas para a nova.
    """
    chave = models.CharField(max_length=40, primary_key=True, default="secretaria")
    sessao_id = models.CharField(max_length=120, unique=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sessão WhatsApp ativa"
        verbose_name_plural = "Sessões WhatsApp ativas"


class EtiquetaConversaWhatsApp(models.Model):
    """Etiqueta efetivamente associada no WA-AKG; exibição rápida no EMECA.

    Guarda apenas informações de apresentação. Mensagens e contatos continuam
    no WA-AKG; sessões diferentes jamais compartilham essas associações.
    """
    sessao = models.CharField(max_length=120)
    jid = models.CharField(max_length=120)
    etiqueta_id = models.CharField(max_length=120)
    nome = models.CharField(max_length=100)
    cor = models.CharField(max_length=16, default="#94a3b8")
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sessao", "jid", "etiqueta_id"],
                name="uniq_etiqueta_conversa_wa",
            )
        ]
        indexes = [
            models.Index(fields=["sessao", "jid"], name="idx_etiqueta_wa_sessao_jid"),
        ]
        verbose_name = "Etiqueta de conversa WhatsApp"
        verbose_name_plural = "Etiquetas de conversas WhatsApp"


class MensagemOcultaWhatsApp(models.Model):
    """Oculta uma mensagem apenas para o operador no EMECA.

    Não exclui conteúdo do WhatsApp, do banco WA-AKG ou de outros usuários.
    A chave inclui a sessão, impedindo vazamento entre contas conectadas.
    """
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="mensagens_ocultas_whatsapp"
    )
    sessao = models.CharField(max_length=120)
    mensagem_id = models.CharField(max_length=190)
    ocultada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "sessao", "mensagem_id"],
                name="uniq_mensagem_oculta_wa_operador"
            )
        ]
        verbose_name = "Mensagem oculta no EMECA"
        verbose_name_plural = "Mensagens ocultas no EMECA"


class ConversaExcluidaWhatsApp(models.Model):
    """Limpeza local de uma conversa no EMECA, por usuário e sessão.

    Armazena o horário da última mensagem no momento da exclusão.
    Mensagens até esse instante ficam ocultas para este operador; novas
    mensagens permitem que a conversa volte a aparecer. Não remove o
    histórico WA-AKG nem altera o WhatsApp do dispositivo.
    """
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="conversas_excluidas_whatsapp",
    )
    sessao = models.CharField(max_length=120)
    jid = models.CharField(max_length=120)
    ultima_mensagem_em = models.CharField(max_length=60, blank=True, default="")
    excluida_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "sessao", "jid"],
                name="uniq_conversa_excluida_wa_operador",
            )
        ]
        verbose_name = "Conversa excluída no EMECA"
        verbose_name_plural = "Conversas excluídas no EMECA"


class GrupoOcultoWhatsApp(models.Model):
    """Grupo retirado da lista administrativa do EMECA, por conta.

    Não apaga o grupo de outras pessoas nem elimina mensagens do WA-AKG.
    A saída real do grupo é uma operação distinta executada via Baileys.
    """
    sessao = models.CharField(max_length=120)
    jid = models.CharField(max_length=120)
    motivo = models.CharField(max_length=20, default="REMOVIDO")
    ocultado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sessao", "jid"], name="uniq_grupo_oculto_wa_sessao"
            )
        ]
        verbose_name = "Grupo removido da lista EMECA"
        verbose_name_plural = "Grupos removidos da lista EMECA"
