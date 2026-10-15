from django.contrib import admin
from .models import (
    AlbumGaleria,
    AtividadeJogo,
    Aviso,
    ConfiguracaoSite,
    DestaqueHome,
    DocumentoPublico,
    Evento,
    FotoGaleria,
    MensagemContato,
    Noticia,
    PerguntaFrequente,
    Projeto,
    PaginaPublica,
)


@admin.register(ConfiguracaoSite)
class ConfiguracaoSiteAdmin(admin.ModelAdmin):
    list_display = ("nome_escola", "cidade", "telefone", "atualizado_em")


@admin.register(DestaqueHome)
class DestaqueHomeAdmin(admin.ModelAdmin):
    list_display = ("titulo", "categoria", "ativo", "ordem", "inicio", "fim")
    list_filter = ("categoria", "ativo")
    list_editable = ("ativo", "ordem")


@admin.register(Aviso)
class AvisoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "tipo", "ativo", "inicio", "fim")
    list_filter = ("tipo", "ativo")
    list_editable = ("ativo",)


@admin.register(Noticia)
class NoticiaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "publicado_em", "ativo", "destaque")
    list_filter = ("ativo", "destaque")
    search_fields = ("titulo", "resumo", "conteudo")
    prepopulated_fields = {"slug": ("titulo",)}


@admin.register(Projeto)
class ProjetoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "ativo", "destaque", "ordem")
    list_filter = ("ativo", "destaque")
    list_editable = ("ativo", "destaque", "ordem")
    search_fields = ("titulo", "resumo")
    prepopulated_fields = {"slug": ("titulo",)}


@admin.register(AtividadeJogo)
class AtividadeJogoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "tipo", "ano_escolar", "disciplina", "ativo", "destaque", "ordem")
    list_filter = ("tipo", "dificuldade", "ativo", "destaque")
    list_editable = ("ativo", "destaque", "ordem")
    search_fields = ("titulo", "descricao", "disciplina", "ano_escolar")
    prepopulated_fields = {"slug": ("titulo",)}


@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "inicio", "local", "ativo")
    list_filter = ("ativo",)


class FotoGaleriaInline(admin.TabularInline):
    model = FotoGaleria
    extra = 1


@admin.register(AlbumGaleria)
class AlbumGaleriaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "data_evento", "ativo")
    list_filter = ("ativo",)
    prepopulated_fields = {"slug": ("titulo",)}
    inlines = [FotoGaleriaInline]


@admin.register(DocumentoPublico)
class DocumentoPublicoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "categoria", "ativo", "ordem")
    list_filter = ("categoria", "ativo")
    list_editable = ("ativo", "ordem")


@admin.register(PerguntaFrequente)
class PerguntaFrequenteAdmin(admin.ModelAdmin):
    list_display = ("pergunta", "ativo", "ordem")
    list_editable = ("ativo", "ordem")


@admin.register(MensagemContato)
class MensagemContatoAdmin(admin.ModelAdmin):
    list_display = ("nome", "assunto", "criada_em", "lida")
    list_filter = ("lida", "criada_em")
    search_fields = ("nome", "email", "telefone", "assunto", "mensagem")
    readonly_fields = ("nome", "email", "telefone", "assunto", "mensagem", "criada_em")


@admin.register(PaginaPublica)
class PaginaPublicaAdmin(admin.ModelAdmin):
    list_display = ("nome", "chave", "ativa", "ordem", "atualizado_em")
    list_editable = ("ativa", "ordem")
    readonly_fields = ("chave", "atualizado_em")
