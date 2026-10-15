from functools import wraps

from django.db.utils import OperationalError, ProgrammingError
from django.http import Http404

from .models import PaginaPublica


DEFAULT_KEYS = [item[0] for item in PaginaPublica.CHAVES]


def paginas_ativas_dict():
    try:
        valores = {item.chave: item.ativa for item in PaginaPublica.objects.all()}
    except (OperationalError, ProgrammingError):
        valores = {}
    return {chave: valores.get(chave, True) for chave in DEFAULT_KEYS}


def pagina_esta_ativa(chave):
    return paginas_ativas_dict().get(chave, True)


def pagina_publica_required(chave):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not pagina_esta_ativa(chave):
                raise Http404("Página temporariamente indisponível.")
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator
