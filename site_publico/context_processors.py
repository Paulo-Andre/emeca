from django.db.utils import OperationalError, ProgrammingError

from .models import ConfiguracaoSite, PaginaPublica, SecaoPagina


def site_publico(request):
    paginas_ativas = {chave: True for chave, _ in PaginaPublica.CHAVES}
    try:
        paginas = {item.chave: item for item in PaginaPublica.objects.all()}
        paginas_ativas.update({chave: pagina.ativa for chave, pagina in paginas.items()})
        config_site = ConfiguracaoSite.objects.first()
        secoes_site = {item.chave: item for item in SecaoPagina.objects.all()}
    except (OperationalError, ProgrammingError):
        paginas = {}
        config_site = None
        secoes_site = {}

    return {
        "config_site": config_site,
        "paginas_site": paginas,
        "paginas_ativas": paginas_ativas,
        "secoes_site": secoes_site,
    }
