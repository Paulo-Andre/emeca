from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from PIL import Image, UnidentifiedImageError
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


EXT_IMAGEM_VALIDATOR = FileExtensionValidator(["jpg", "jpeg", "png", "webp"])
EXT_PAGINA_VALIDATOR = FileExtensionValidator(["jpg", "jpeg", "png", "webp", "pdf"])
EXT_DOCUMENTO_VALIDATOR = FileExtensionValidator(["pdf", "doc", "docx", "xls", "xlsx", "odt"])


def _limitar_tamanho(arquivo, max_mb):
    tamanho = getattr(arquivo, "size", 0) or 0
    if tamanho > max_mb * 1024 * 1024:
        raise ValidationError(f"O arquivo deve ter no máximo {max_mb} MB.")


def _assinatura(arquivo, tamanho=12):
    posicao = arquivo.tell() if hasattr(arquivo, "tell") else 0
    try:
        arquivo.seek(0)
        return arquivo.read(tamanho)
    finally:
        try:
            arquivo.seek(posicao)
        except Exception:
            pass


def validar_imagem_upload(arquivo):
    EXT_IMAGEM_VALIDATOR(arquivo)
    _limitar_tamanho(arquivo, 10)
    posicao = arquivo.tell() if hasattr(arquivo, "tell") else 0
    try:
        arquivo.seek(0)
        imagem = Image.open(arquivo)
        if imagem.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValidationError("O arquivo enviado não é uma imagem JPG, PNG ou WEBP válida.")
        largura, altura = imagem.size
        if largura <= 0 or altura <= 0 or largura * altura > 25_000_000:
            raise ValidationError("A imagem possui dimensões inválidas ou excessivas.")
        imagem.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError("O conteúdo do arquivo não corresponde a uma imagem válida.") from exc
    finally:
        try:
            arquivo.seek(posicao)
        except Exception:
            pass


def validar_pagina_upload(arquivo):
    EXT_PAGINA_VALIDATOR(arquivo)
    extensao = Path(getattr(arquivo, "name", "")).suffix.lower()
    if extensao == ".pdf":
        _limitar_tamanho(arquivo, 25)
        if not _assinatura(arquivo, 5).startswith(b"%PDF-"):
            raise ValidationError("O conteúdo do arquivo não corresponde a um PDF válido.")
        return
    validar_imagem_upload(arquivo)


def validar_documento_upload(arquivo):
    EXT_DOCUMENTO_VALIDATOR(arquivo)
    _limitar_tamanho(arquivo, 25)
    extensao = Path(getattr(arquivo, "name", "")).suffix.lower()
    cabecalho = _assinatura(arquivo, 12)

    if extensao == ".pdf":
        valido = cabecalho.startswith(b"%PDF-")
    elif extensao in {".doc", ".xls"}:
        valido = cabecalho.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    else:
        valido = cabecalho.startswith(b"PK\x03\x04") or cabecalho.startswith(b"PK\x05\x06")

    if not valido:
        raise ValidationError(
            "O conteúdo do arquivo não corresponde ao formato informado pela extensão."
        )


IMAGEM_VALIDATOR = validar_imagem_upload
PAGINA_ARQUIVO_VALIDATOR = validar_pagina_upload
DOCUMENTO_VALIDATOR = validar_documento_upload


def _slug_unico(instance, valor):
    base = slugify(valor)[:170] or "item"
    candidato = base
    indice = 2
    queryset = instance.__class__.objects.all()
    if instance.pk:
        queryset = queryset.exclude(pk=instance.pk)
    while queryset.filter(slug=candidato).exists():
        sufixo = f"-{indice}"
        candidato = f"{base[:180-len(sufixo)]}{sufixo}"
        indice += 1
    return candidato


class ConfiguracaoSite(models.Model):
    nome_escola = models.CharField(max_length=180, default="E. M. Egídio Cordeiro Aquino")
    subtitulo = models.CharField(max_length=220, default="Educação, acolhimento e aprendizagem construídos juntos.")
    apresentacao = models.TextField(blank=True)
    historia = models.TextField(blank=True)
    missao_valores = models.TextField(blank=True)
    vida_escolar = models.TextField(blank=True)
    home_titulo = models.CharField(max_length=220, blank=True, default="Um espaço para aprender, conviver e crescer")
    home_texto = models.TextField(blank=True)
    home_pilar1_titulo = models.CharField(max_length=120, blank=True, default="Aprendizagem")
    home_pilar1_texto = models.TextField(blank=True)
    home_pilar2_titulo = models.CharField(max_length=120, blank=True, default="Convivência")
    home_pilar2_texto = models.TextField(blank=True)
    home_pilar3_titulo = models.CharField(max_length=120, blank=True, default="Família e comunidade")
    home_pilar3_texto = models.TextField(blank=True)
    logo_site = models.FileField(
        upload_to="site_publico/configuracao/",
        validators=[IMAGEM_VALIDATOR],
        blank=True,
    )
    endereco = models.CharField(max_length=255, blank=True)
    cidade = models.CharField(max_length=120, default="Montes Claros/MG", blank=True)
    telefone = models.CharField(max_length=60, blank=True)
    whatsapp = models.CharField(max_length=60, blank=True)
    email = models.EmailField(blank=True)
    horario_atendimento = models.CharField(max_length=180, blank=True)
    mapa_url = models.URLField(blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuração do site"
        verbose_name_plural = "Configurações do site"

    def __str__(self):
        return self.nome_escola


class PaginaPublica(models.Model):
    CHAVES = [
        ("escola", "A Escola"),
        ("vida_escolar", "Vida Escolar"),
        ("atividades", "Atividades e Jogos"),
        ("projetos", "Projetos"),
        ("noticias", "Notícias"),
        ("galeria", "Galeria"),
        ("matricula", "Matrícula"),
        ("boletim", "Boletim"),
        ("documentos", "Documentos"),
        ("faq", "Perguntas Frequentes"),
        ("contato", "Contato"),
    ]

    chave = models.CharField(max_length=40, choices=CHAVES, unique=True)
    nome = models.CharField(max_length=120)
    ativa = models.BooleanField(default=True)
    rotulo = models.CharField(max_length=180, blank=True)
    titulo = models.CharField(max_length=180, blank=True)
    subtitulo = models.CharField(max_length=360, blank=True)
    texto_principal = models.TextField(blank=True)
    imagem_capa = models.FileField(
        upload_to="site_publico/paginas/",
        validators=[PAGINA_ARQUIVO_VALIDATOR],
        blank=True,
    )
    ordem = models.PositiveSmallIntegerField(default=0)
    atualizado_em = models.DateTimeField(auto_now=True)

    @property
    def capa_e_pdf(self):
        return bool(self.imagem_capa and self.imagem_capa.name.lower().endswith(".pdf"))

    @property
    def arquivos_ativos(self):
        return self.arquivos.filter(ativo=True)

    class Meta:
        ordering = ["ordem", "nome"]
        verbose_name = "Página pública"
        verbose_name_plural = "Páginas públicas"

    def __str__(self):
        return self.nome


class ArquivoPaginaPublica(models.Model):
    pagina = models.ForeignKey(
        PaginaPublica,
        on_delete=models.CASCADE,
        related_name="arquivos",
    )
    titulo = models.CharField(max_length=180, blank=True)
    arquivo = models.FileField(
        upload_to="site_publico/paginas/documentos/",
        validators=[DOCUMENTO_VALIDATOR],
    )
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ordem", "id"]
        verbose_name = "Documento da página"
        verbose_name_plural = "Documentos da página"

    @property
    def nome_exibicao(self):
        return self.titulo or self.arquivo.name.rsplit("/", 1)[-1]

    def __str__(self):
        return self.nome_exibicao


class SecaoPagina(models.Model):
    PAGINAS = [("home", "Início")] + PaginaPublica.CHAVES

    pagina = models.CharField(max_length=40, choices=PAGINAS)
    chave = models.SlugField(max_length=90, unique=True)
    nome = models.CharField(max_length=180)
    rotulo = models.CharField(
        max_length=180,
        blank=True,
        help_text="Texto pequeno exibido acima do título, quando o bloco usar esse elemento.",
    )
    titulo = models.CharField(max_length=220, blank=True)
    texto = models.TextField(blank=True)
    imagem = models.FileField(
        upload_to="site_publico/secoes/",
        validators=[IMAGEM_VALIDATOR],
        blank=True,
    )
    ativa = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["pagina", "ordem", "nome"]
        verbose_name = "Seção editável"
        verbose_name_plural = "Seções editáveis"

    def __str__(self):
        return self.nome


class DestaqueHome(models.Model):
    CATEGORIAS = [
        ("NOTICIA", "Notícia"),
        ("EVENTO", "Evento"),
        ("PROJETO", "Projeto"),
        ("COMUNICADO", "Comunicado"),
    ]
    titulo = models.CharField(max_length=180)
    descricao = models.CharField(max_length=320, blank=True)
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default="NOTICIA")
    imagem = models.FileField(
        upload_to="site_publico/destaques/",
        validators=[IMAGEM_VALIDATOR],
        blank=True,
    )
    texto_botao = models.CharField(max_length=60, blank=True, default="Saiba mais")
    link = models.CharField(max_length=500, blank=True)
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)
    inicio = models.DateTimeField(blank=True, null=True)
    fim = models.DateTimeField(blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ordem", "-criado_em"]
        verbose_name = "Destaque do carrossel"
        verbose_name_plural = "Destaques do carrossel"

    def __str__(self):
        return self.titulo


class Aviso(models.Model):
    TIPOS = [
        ("INFO", "Informativo"),
        ("IMPORTANTE", "Importante"),
        ("URGENTE", "Urgente"),
    ]
    titulo = models.CharField(max_length=160)
    texto = models.TextField()
    tipo = models.CharField(max_length=20, choices=TIPOS, default="INFO")
    link = models.CharField(max_length=500, blank=True)
    texto_link = models.CharField(max_length=60, blank=True, default="Saiba mais")
    ativo = models.BooleanField(default=True)
    inicio = models.DateTimeField(blank=True, null=True)
    fim = models.DateTimeField(blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return self.titulo


class Noticia(models.Model):
    titulo = models.CharField(max_length=180)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    resumo = models.CharField(max_length=360, blank=True)
    conteudo = models.TextField()
    imagem = models.FileField(
        upload_to="site_publico/noticias/",
        validators=[IMAGEM_VALIDATOR],
        blank=True,
    )
    publicado_em = models.DateTimeField()
    ativo = models.BooleanField(default=True)
    destaque = models.BooleanField(default=False)

    class Meta:
        ordering = ["-publicado_em"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _slug_unico(self, self.titulo)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("site_publico:noticia", args=[self.slug])

    def __str__(self):
        return self.titulo


class Projeto(models.Model):
    titulo = models.CharField(max_length=180)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    resumo = models.CharField(max_length=360, blank=True)
    conteudo = models.TextField()
    imagem = models.FileField(
        upload_to="site_publico/projetos/",
        validators=[IMAGEM_VALIDATOR],
        blank=True,
    )
    ativo = models.BooleanField(default=True)
    destaque = models.BooleanField(default=False)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "titulo"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _slug_unico(self, self.titulo)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("site_publico:projeto", args=[self.slug])

    def __str__(self):
        return self.titulo


class AtividadeJogo(models.Model):
    TIPOS = [
        ("JOGO", "Jogo"),
        ("QUIZ", "Quiz"),
        ("ATIVIDADE", "Atividade"),
        ("DESAFIO", "Desafio"),
        ("VIDEO", "Vídeo educativo"),
        ("MATERIAL", "Material"),
    ]
    DIFICULDADES = [
        ("FACIL", "Fácil"),
        ("MEDIO", "Médio"),
        ("DESAFIO", "Desafio"),
    ]
    titulo = models.CharField(max_length=180)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    descricao = models.TextField()
    tipo = models.CharField(max_length=20, choices=TIPOS, default="ATIVIDADE")
    ano_escolar = models.CharField(max_length=80, blank=True)
    disciplina = models.CharField(max_length=100, blank=True)
    dificuldade = models.CharField(max_length=20, choices=DIFICULDADES, default="FACIL")
    imagem = models.FileField(
        upload_to="site_publico/atividades/",
        validators=[IMAGEM_VALIDATOR],
        blank=True,
    )
    link = models.URLField(blank=True)
    arquivo = models.FileField(
        upload_to="site_publico/atividades/arquivos/",
        validators=[DOCUMENTO_VALIDATOR],
        blank=True,
    )
    ativo = models.BooleanField(default=True)
    destaque = models.BooleanField(default=False)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "titulo"]
        verbose_name = "Atividade ou jogo"
        verbose_name_plural = "Atividades e jogos"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _slug_unico(self, self.titulo)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("site_publico:atividade", args=[self.slug])

    def __str__(self):
        return self.titulo


class Evento(models.Model):
    titulo = models.CharField(max_length=180)
    descricao = models.CharField(max_length=320, blank=True)
    inicio = models.DateTimeField()
    fim = models.DateTimeField(blank=True, null=True)
    local = models.CharField(max_length=180, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["inicio"]

    def __str__(self):
        return self.titulo


class AlbumGaleria(models.Model):
    titulo = models.CharField(max_length=180)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    descricao = models.CharField(max_length=360, blank=True)
    capa = models.FileField(
        upload_to="site_publico/galeria/capas/",
        validators=[IMAGEM_VALIDATOR],
        blank=True,
    )
    data_evento = models.DateField(blank=True, null=True)
    foto_capa = models.ForeignKey(
        "FotoGaleria",
        on_delete=models.SET_NULL,
        related_name="+",
        blank=True,
        null=True,
    )
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["-data_evento", "-id"]
        verbose_name = "Álbum da galeria"
        verbose_name_plural = "Álbuns da galeria"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _slug_unico(self, self.titulo)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("site_publico:album", args=[self.slug])

    def __str__(self):
        return self.titulo


class FotoGaleria(models.Model):
    album = models.ForeignKey(AlbumGaleria, on_delete=models.CASCADE, related_name="fotos")
    imagem = models.FileField(
        upload_to="site_publico/galeria/fotos/",
        validators=[IMAGEM_VALIDATOR],
    )
    legenda = models.CharField(max_length=220, blank=True)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "id"]
        verbose_name = "Foto da galeria"
        verbose_name_plural = "Fotos da galeria"

    def __str__(self):
        return self.legenda or f"Foto de {self.album}"


class DocumentoPublico(models.Model):
    CATEGORIAS = [
        ("FORMULARIO", "Formulário"),
        ("ORIENTACAO", "Orientação"),
        ("LISTA", "Lista"),
        ("OUTRO", "Outro"),
    ]
    titulo = models.CharField(max_length=180)
    descricao = models.CharField(max_length=360, blank=True)
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default="OUTRO")
    arquivo = models.FileField(
        upload_to="site_publico/documentos/",
        validators=[DOCUMENTO_VALIDATOR],
    )
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "titulo"]
        verbose_name = "Documento público"
        verbose_name_plural = "Documentos públicos"

    def __str__(self):
        return self.titulo


class PerguntaFrequente(models.Model):
    pergunta = models.CharField(max_length=220)
    resposta = models.TextField()
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "id"]
        verbose_name = "Pergunta frequente"
        verbose_name_plural = "Perguntas frequentes"

    def __str__(self):
        return self.pergunta


class MensagemContato(models.Model):
    nome = models.CharField(max_length=160)
    email = models.EmailField(blank=True)
    telefone = models.CharField(max_length=40, blank=True)
    assunto = models.CharField(max_length=180)
    mensagem = models.TextField()
    lida = models.BooleanField(default=False)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criada_em"]
        verbose_name = "Mensagem de contato"
        verbose_name_plural = "Mensagens de contato"

    def __str__(self):
        return f"{self.nome} — {self.assunto}"



class PeriodoBoletim(models.Model):
    TIPOS = [
        ("BIMESTRE", "Bimestre"),
        ("TRIMESTRE", "Trimestre"),
    ]

    tipo = models.CharField(max_length=12, choices=TIPOS)
    numero = models.PositiveSmallIntegerField()
    ano = models.PositiveSmallIntegerField()
    turma = models.CharField(max_length=160)
    regente = models.CharField(max_length=180, blank=True)
    publicado = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-ano", "tipo", "numero", "turma"]
        constraints = [
            models.UniqueConstraint(
                fields=["tipo", "numero", "ano", "turma"],
                name="uniq_periodo_boletim_turma",
            )
        ]
        verbose_name = "Período de boletim"
        verbose_name_plural = "Períodos de boletim"

    def clean(self):
        if self.tipo and self.numero is not None:
            limite = 4 if self.tipo == "BIMESTRE" else 3
            if self.numero < 1 or self.numero > limite:
                raise ValidationError(
                    {"numero": f"Para {self.get_tipo_display().lower()}, informe um período entre 1 e {limite}."}
                )
        if self.ano is not None and (self.ano < 2000 or self.ano > 2100):
            raise ValidationError({"ano": "Informe um ano letivo válido."})

    @property
    def nome_periodo(self):
        ordinal = f"{self.numero}º"
        return f"{ordinal} {self.get_tipo_display()}"

    @property
    def titulo(self):
        return f"{self.nome_periodo} · {self.turma} · {self.ano}"

    def __str__(self):
        return self.titulo


class AlunoBoletim(models.Model):
    # A identidade atual usada para consultar o boletim vem exclusivamente
    # de Declarações. Matrícula mantém-se como registro histórico independente.
    declaracao = models.OneToOneField(
        "usuarioSec.declaracao",
        on_delete=models.PROTECT,
        related_name="perfil_boletim",
        blank=True,
        null=True,
    )
    matricula = models.OneToOneField(
        "cadastro.matricula",
        on_delete=models.SET_NULL,
        related_name="perfil_boletim",
        blank=True,
        null=True,
    )
    nome = models.CharField(max_length=255)
    data_nascimento = models.DateField(blank=True, null=True)
    cpf_mae = models.CharField(max_length=20, blank=True)
    cpf_responsavel = models.CharField(max_length=20, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Aluno de boletim"
        verbose_name_plural = "Alunos de boletim"

    @property
    def nome_oficial(self):
        """Identificação atual da Declaração sem reescrever nomes das planilhas."""
        return (
            self.declaracao.nomeDoAluno if self.declaracao_id
            else self.nome
        )

    def __str__(self):
        return self.nome


class DisciplinaBoletim(models.Model):
    periodo = models.ForeignKey(
        PeriodoBoletim,
        on_delete=models.CASCADE,
        related_name="disciplinas",
    )
    nome = models.CharField(max_length=160)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["periodo", "nome"],
                name="uniq_disciplina_periodo_boletim",
            )
        ]
        verbose_name = "Disciplina do boletim"
        verbose_name_plural = "Disciplinas do boletim"

    def __str__(self):
        return self.nome


class BoletimAluno(models.Model):
    periodo = models.ForeignKey(
        PeriodoBoletim,
        on_delete=models.CASCADE,
        related_name="boletins",
    )
    aluno = models.ForeignKey(
        AlunoBoletim,
        on_delete=models.CASCADE,
        related_name="boletins",
    )
    numero_chamada = models.PositiveSmallIntegerField(blank=True, null=True)
    faltas_totais = models.PositiveSmallIntegerField(blank=True, null=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["numero_chamada", "aluno__nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["periodo", "aluno"],
                name="uniq_boletim_aluno_periodo",
            )
        ]
        verbose_name = "Boletim do aluno"
        verbose_name_plural = "Boletins dos alunos"

    def __str__(self):
        return f"{self.aluno.nome} · {self.periodo.titulo}"


class NotaBoletim(models.Model):
    boletim = models.ForeignKey(
        BoletimAluno,
        on_delete=models.CASCADE,
        related_name="resultados",
    )
    disciplina = models.ForeignKey(
        DisciplinaBoletim,
        on_delete=models.CASCADE,
        related_name="resultados",
    )
    nota = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    faltas = models.PositiveSmallIntegerField(blank=True, null=True)

    class Meta:
        ordering = ["disciplina__ordem", "disciplina__id"]
        constraints = [
            models.UniqueConstraint(
                fields=["boletim", "disciplina"],
                name="uniq_nota_disciplina_boletim",
            )
        ]
        verbose_name = "Nota do boletim"
        verbose_name_plural = "Notas do boletim"

    def __str__(self):
        return f"{self.boletim.aluno.nome} · {self.disciplina.nome}"
