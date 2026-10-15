from django.db.utils import OperationalError, ProgrammingError

from .models import ConfiguracaoSite, PaginaPublica


def site_publico(request):
    try:
        paginas = {item.chave: item for item in PaginaPublica.objects.all()}
        paginas_ativas = {chave: pagina.ativa for chave, pagina in paginas.items()}
        config_site = ConfiguracaoSite.objects.first()
    except (OperationalError, ProgrammingError):
        paginas = {}
        paginas_ativas = {}
        config_site = None

    return {
        "config_site": config_site,
        "paginas_site": paginas,
        "paginas_ativas": paginas_ativas,
    }
