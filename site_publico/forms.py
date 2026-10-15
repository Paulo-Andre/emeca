from django import forms
from django.forms import modelform_factory

from .models import (
    AlbumGaleria,
    AtividadeJogo,
    Aviso,
    ConfiguracaoSite,
    DestaqueHome,
    DocumentoPublico,
    Evento,
    FotoGaleria,
    Noticia,
    PaginaPublica,
    PerguntaFrequente,
    SecaoPagina,
    Projeto,
)


class StyledModelForm(forms.ModelForm):
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


class PaginaPublicaForm(StyledModelForm):
    class Meta:
        model = PaginaPublica
        fields = ["ativa", "titulo", "subtitulo", "texto_principal", "imagem_capa"]


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
    return modelform_factory(
        config["model"],
        form=StyledModelForm,
        fields=config["fields"],
    )
