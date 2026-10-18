from django import forms
from django.forms import modelform_factory
from usuarioSec.models import declaracao
from urllib.parse import urlparse


from .models import (
    AlbumGaleria,
    AtividadeJogo,
    Aviso,
    ConfiguracaoSite,
    DestaqueHome,
    DocumentoPublico,
    Evento,
    FotoGaleria,
    IMAGEM_VALIDATOR,
    Noticia,
    PaginaPublica,
    PeriodoBoletim,
    PerguntaFrequente,
    SecaoPagina,
    Projeto,
)


class StyledModelForm(forms.ModelForm):
    def clean_link(self):
        link = (self.cleaned_data.get("link") or "").strip()
        if not link:
            return ""
        if link.startswith("/") and not link.startswith("//"):
            return link
        scheme = urlparse(link).scheme.lower()
        if scheme not in {"http", "https"}:
            raise forms.ValidationError(
                "Use um endereço interno iniciado por / ou uma URL http/https."
            )
        return link

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "site-manager-check"
            elif isinstance(widget, forms.Textarea):
                widget.attrs["class"] = "site-manager-input site-manager-textarea"
                widget.attrs.setdefault("rows", 5)
            else:
                widget.attrs["class"] = "site-manager-input"

            if isinstance(widget, forms.DateTimeInput):
                widget.input_type = "datetime-local"
                widget.format = "%Y-%m-%dT%H:%M"
                field.input_formats = ["%Y-%m-%dT%H:%M"]
            elif isinstance(widget, forms.DateInput):
                widget.input_type = "date"
                widget.format = "%Y-%m-%d"
                field.input_formats = ["%Y-%m-%d"]


class ConfiguracaoSiteForm(StyledModelForm):
    class Meta:
        model = ConfiguracaoSite
        fields = [
            "nome_escola", "subtitulo", "apresentacao", "historia", "missao_valores",
            "vida_escolar", "home_titulo", "home_texto",
            "home_pilar1_titulo", "home_pilar1_texto",
            "home_pilar2_titulo", "home_pilar2_texto",
            "home_pilar3_titulo", "home_pilar3_texto", "logo_site",
            "endereco", "cidade", "telefone", "whatsapp", "email",
            "horario_atendimento", "mapa_url",
        ]


class HomePageForm(StyledModelForm):
    class Meta:
        model = ConfiguracaoSite
        fields = [
            "home_titulo",
            "home_texto",
            "home_pilar1_titulo",
            "home_pilar1_texto",
            "home_pilar2_titulo",
            "home_pilar2_texto",
            "home_pilar3_titulo",
            "home_pilar3_texto",
        ]
        labels = {
            "home_titulo": "Título principal da apresentação",
            "home_texto": "Texto principal da apresentação",
            "home_pilar1_titulo": "Título do pilar 1",
            "home_pilar1_texto": "Texto do pilar 1",
            "home_pilar2_titulo": "Título do pilar 2",
            "home_pilar2_texto": "Texto do pilar 2",
            "home_pilar3_titulo": "Título do pilar 3",
            "home_pilar3_texto": "Texto do pilar 3",
        }


class PaginaPublicaForm(StyledModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["imagem_capa"].widget.attrs["accept"] = "image/jpeg,image/png,image/webp,application/pdf"

    class Meta:
        model = PaginaPublica
        fields = ["ativa", "rotulo", "titulo", "subtitulo", "texto_principal", "imagem_capa"]
        labels = {
            "rotulo": "Texto de destaque",
            "imagem_capa": "Imagem ou PDF da página",
        }
        help_texts = {
            "rotulo": "Texto pequeno exibido acima do título da página.",
            "imagem_capa": "Formatos permitidos: JPG, JPEG, PNG, WEBP ou PDF.",
        }


class SecaoPaginaForm(StyledModelForm):
    class Meta:
        model = SecaoPagina
        fields = ["rotulo", "titulo", "texto", "imagem"]
        labels = {
            "rotulo": "Texto de destaque",
            "titulo": "Título",
            "texto": "Texto",
            "imagem": "Imagem",
        }
        help_texts = {
            "rotulo": "É o texto menor que aparece acima do título em alguns blocos.",
            "imagem": "Opcional. Quando o layout do bloco aceitar imagem, ela será exibida sem alterar menus ou botões.",
        }


class MultipleImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.FileField):
    widget = MultipleImageInput

    def clean(self, data, initial=None):
        if not data and self.required:
            raise forms.ValidationError("Selecione pelo menos uma foto.")
        arquivos = data if isinstance(data, (list, tuple)) else [data]
        limpos = []
        for arquivo in arquivos:
            if arquivo:
                limpos.append(super().clean(arquivo, initial))
        return limpos


class FotoGaleriaLoteForm(forms.Form):
    album_existente = forms.ModelChoiceField(
        queryset=AlbumGaleria.objects.none(),
        required=False,
        label="Usar álbum existente",
        empty_label="Selecione um álbum já criado",
    )
    novo_album = forms.CharField(
        max_length=180,
        required=False,
        label="Nome do novo álbum",
        widget=forms.TextInput(attrs={"placeholder": "Ex.: Festa Junina 2026"}),
    )
    descricao_album = forms.CharField(
        max_length=360,
        required=False,
        label="Descrição do novo álbum",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Opcional"}),
    )
    data_evento = forms.DateField(
        required=False,
        label="Data do evento",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={
                "type": "date",
                "placeholder": "dd/mm/aaaa",
            },
        ),
    )
    fotos = MultipleImageField(
        required=True,
        label="Fotos",
        validators=[IMAGEM_VALIDATOR],
        widget=MultipleImageInput(attrs={
            "accept": "image/jpeg,image/png,image/webp",
            "multiple": True,
        }),
        help_text="Selecione várias fotos de uma vez. Formatos: JPG, JPEG, PNG ou WEBP.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["album_existente"].queryset = AlbumGaleria.objects.all()
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.Textarea):
                widget.attrs["class"] = "site-manager-input site-manager-textarea"
            else:
                widget.attrs["class"] = "site-manager-input"

    def clean(self):
        cleaned = super().clean()
        album_existente = cleaned.get("album_existente")
        novo_album = (cleaned.get("novo_album") or "").strip()

        if album_existente and novo_album:
            raise forms.ValidationError(
                "Escolha um álbum existente ou informe o nome de um novo álbum, não os dois."
            )
        if not album_existente and not novo_album:
            raise forms.ValidationError(
                "Selecione um álbum existente ou escreva o nome de um novo álbum."
            )
        return cleaned


CONTENT_FORMS = {
    "carrossel": {
        "model": DestaqueHome,
        "label": "Carrossel",
        "singular": "destaque",
        "icon": "gallery-horizontal-end",
        "fields": ["titulo", "descricao", "categoria", "imagem", "ativo", "ordem", "inicio", "fim"],
    },
    "avisos": {
        "model": Aviso,
        "label": "Avisos",
        "singular": "aviso",
        "icon": "megaphone",
        "fields": ["titulo", "texto", "tipo", "link", "ativo", "inicio", "fim"],
    },
    "noticias": {
        "model": Noticia,
        "label": "Notícias",
        "singular": "notícia",
        "icon": "newspaper",
        "fields": ["titulo", "resumo", "conteudo", "imagem", "publicado_em", "ativo", "destaque"],
    },
    "projetos": {
        "model": Projeto,
        "label": "Projetos",
        "singular": "projeto",
        "icon": "users-round",
        "fields": ["titulo", "resumo", "conteudo", "imagem", "ativo", "destaque", "ordem"],
    },
    "atividades": {
        "model": AtividadeJogo,
        "label": "Atividades e Jogos",
        "singular": "atividade",
        "icon": "gamepad-2",
        "fields": [
            "titulo", "descricao", "tipo", "ano_escolar", "disciplina", "dificuldade",
            "imagem", "link", "arquivo", "ativo", "destaque", "ordem",
        ],
    },
    "eventos": {
        "model": Evento,
        "label": "Eventos",
        "singular": "evento",
        "icon": "calendar-days",
        "fields": ["titulo", "descricao", "inicio", "fim", "local", "ativo"],
    },
    "albuns": {
        "model": AlbumGaleria,
        "label": "Álbuns da Galeria",
        "singular": "álbum",
        "icon": "images",
        "fields": ["titulo", "descricao", "capa", "data_evento", "ativo"],
    },
    "fotos": {
        "model": FotoGaleria,
        "label": "Fotos da Galeria",
        "singular": "foto",
        "icon": "image",
        "fields": ["album", "imagem", "legenda", "ordem"],
    },
    "documentos": {
        "model": DocumentoPublico,
        "label": "Documentos",
        "singular": "documento",
        "icon": "folder-down",
        "fields": ["titulo", "descricao", "categoria", "arquivo", "ativo", "ordem"],
    },
    "faq": {
        "model": PerguntaFrequente,
        "label": "Perguntas Frequentes",
        "singular": "pergunta",
        "icon": "circle-help",
        "fields": ["pergunta", "resposta", "ativo", "ordem"],
    },
}


def get_content_form(tipo):
    config = CONTENT_FORMS[tipo]
    extras = {}
    if tipo == "albuns":
        extras["labels"] = {
            "capa": "Capa enviada manualmente (opcional)",
        }
        extras["help_texts"] = {
            "capa": "Opcional. Depois de adicionar fotos ao álbum, você também pode escolher qualquer uma delas como capa.",
        }

    return modelform_factory(
        config["model"],
        form=StyledModelForm,
        fields=config["fields"],
        **extras,
    )



DISCIPLINAS_BOLETIM_PADRAO = """Língua Portuguesa
Experiências Literárias
Artes
Educação Física
LEM - Inglês
Matemática
Ciências Naturais
Geografia
História
Ensino Religioso"""


class BoletimConsultaForm(forms.Form):
    cpf = forms.CharField(
        max_length=14,
        label="CPF da mãe ou do responsável",
        widget=forms.TextInput(
            attrs={
                "class": "bulletin-access-input",
                "inputmode": "numeric",
                "autocomplete": "off",
                "placeholder": "000.000.000-00",
                "maxlength": "14",
                "data-cpf-mask": "true",
            }
        ),
    )
    data_nascimento = forms.DateField(
        label="Data de nascimento da criança",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={
                "class": "bulletin-access-input",
                "type": "date",
                "autocomplete": "off",
            },
        ),
    )


class PeriodoBoletimForm(StyledModelForm):
    class Meta:
        model = PeriodoBoletim
        fields = ["tipo", "numero", "ano", "turma", "regente", "publicado"]
        labels = {
            "tipo": "Organização do ano",
            "numero": "Período",
            "ano": "Ano letivo",
            "turma": "Turma",
            "regente": "Professor(a) regente",
            "publicado": "Disponibilizar para os responsáveis",
        }
        help_texts = {
            "tipo": "Escolha Bimestre ou Trimestre.",
            "numero": "Bimestre: 1 a 4. Trimestre: 1 a 3.",
            "publicado": "Quando marcado, os responsáveis já poderão consultar este boletim.",
        }


class PeriodoBoletimNovoForm(PeriodoBoletimForm):
    disciplinas = forms.CharField(
        label="Disciplinas",
        initial=DISCIPLINAS_BOLETIM_PADRAO,
        widget=forms.Textarea(
            attrs={
                "class": "site-manager-input site-manager-textarea",
                "rows": 11,
            }
        ),
        help_text="Informe uma disciplina por linha. Você poderá lançar Nota e Faltas para cada uma.",
    )


class BoletimImportacaoForm(forms.Form):
    arquivo = forms.FileField(
        label="Planilha de notas e faltas",
        widget=forms.ClearableFileInput(
            attrs={
                "class": "site-manager-input",
                "accept": ".xls,.xlsx",
            }
        ),
        help_text=(
            "Envie a planilha .xls ou .xlsx. Organização do ano, período, ano letivo, "
            "turma, professor(a) regente e disciplinas serão extraídos automaticamente."
        ),
    )


class BoletimAlunoManualForm(forms.Form):
    declaracao_aluno = forms.ModelChoiceField(
        queryset=declaracao.objects.all().order_by("nomeDoAluno", "id"),
        required=False,
        label="Cadastro do aluno em Declarações",
        empty_label="Selecione uma declaração existente...",
        widget=forms.Select(attrs={"class": "site-manager-input"}),
        help_text=(
            "Vínculo obrigatório antes da publicação. Em homônimos, selecione "
            "o registro correto; CPFs e nascimento serão lidos de Declarações."
        ),
    )
    nome_aluno = forms.CharField(
        max_length=255,
        label="Nome do aluno",
        widget=forms.TextInput(
            attrs={
                "class": "site-manager-input",
                "placeholder": "Nome completo do aluno",
                "autocomplete": "off",
            }
        ),
        help_text=(
            "Nome apresentado nas notas; não altera o cadastro de Declarações."
        ),
    )
    numero_chamada = forms.IntegerField(
        required=False,
        min_value=1,
        label="Número da chamada",
        widget=forms.NumberInput(attrs={"class": "site-manager-input", "min": 1}),
    )
    faltas_totais = forms.IntegerField(
        required=False,
        min_value=0,
        label="Faltas totais no período",
        widget=forms.NumberInput(
            attrs={"class": "site-manager-input", "min": 0, "inputmode": "numeric"}
        ),
        help_text=(
            "Na importação, este valor vem exclusivamente da coluna F da planilha. "
            "Não é feita soma de faltas por disciplina."
        ),
    )

    def __init__(self, *args, **kwargs):
        perfil_fixo = kwargs.pop("perfil_fixo", None)
        super().__init__(*args, **kwargs)

        if perfil_fixo is not None and not self.is_bound:
            self.fields["nome_aluno"].initial = perfil_fixo.nome
            if perfil_fixo.declaracao_id:
                self.fields["declaracao_aluno"].initial = perfil_fixo.declaracao_id

    def clean_nome_aluno(self):
        nome = " ".join((self.cleaned_data.get("nome_aluno") or "").split()).strip()
        if not nome:
            raise forms.ValidationError("Informe o nome do aluno.")
        return nome

