from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CONTENT_FORMS, ConfiguracaoSiteForm, PaginaPublicaForm, get_content_form
from .models import ConfiguracaoSite, PaginaPublica


def _tipo_config(tipo):
    config = CONTENT_FORMS.get(tipo)
    if not config:
        raise Http404("Tipo de conteúdo inválido.")
    return config


@login_required
def gestao_site(request):
    paginas = PaginaPublica.objects.all()
    conteudos = []
    for chave, config in CONTENT_FORMS.items():
        conteudos.append({
            "chave": chave,
            "label": config["label"],
            "icon": config["icon"],
            "total": config["model"].objects.count(),
        })
    return render(request, "site_publico/gestao/dashboard.html", {
        "paginas": paginas,
        "conteudos": conteudos,
    })


@login_required
def gestao_configuracao(request):
    config, _ = ConfiguracaoSite.objects.get_or_create(pk=1)
    form = ConfiguracaoSiteForm(request.POST or None, instance=config)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Informações institucionais atualizadas.")
        return redirect("site_publico:gestao_configuracao")
    return render(request, "site_publico/gestao/form.html", {
        "form": form,
        "titulo": "Informações institucionais",
        "descricao": "Edite os textos e canais gerais exibidos no site.",
        "voltar": "site_publico:gestao_site",
    })


@login_required
def gestao_paginas(request):
    return render(request, "site_publico/gestao/paginas.html", {
        "paginas": PaginaPublica.objects.all(),
    })


@login_required
def gestao_pagina_editar(request, chave):
    pagina = get_object_or_404(PaginaPublica, chave=chave)
    form = PaginaPublicaForm(request.POST or None, request.FILES or None, instance=pagina)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f'Página "{pagina.nome}" atualizada.')
        return redirect("site_publico:gestao_paginas")
    return render(request, "site_publico/gestao/form.html", {
        "form": form,
        "titulo": f"Editar página: {pagina.nome}",
        "descricao": "Altere os textos, imagem principal e disponibilidade pública desta página.",
        "objeto": pagina,
        "imagem_atual": pagina.imagem_capa,
        "voltar": "site_publico:gestao_paginas",
    })


@require_POST
@login_required
def gestao_pagina_toggle(request, chave):
    pagina = get_object_or_404(PaginaPublica, chave=chave)
    pagina.ativa = not pagina.ativa
    pagina.save(update_fields=["ativa", "atualizado_em"])
    estado = "ativada" if pagina.ativa else "desativada"
    messages.success(request, f'Página "{pagina.nome}" {estado}.')
    return redirect(request.POST.get("next") or "site_publico:gestao_paginas")


@login_required
def gestao_conteudo_lista(request, tipo):
    config = _tipo_config(tipo)
    objetos = config["model"].objects.all()
    linhas = []
    for obj in objetos:
        linhas.append({
            "obj": obj,
            "ativo": getattr(obj, "ativo", None),
            "destaque": getattr(obj, "destaque", None),
        })
    return render(request, "site_publico/gestao/lista.html", {
        "tipo": tipo,
        "config": config,
        "linhas": linhas,
    })


@login_required
def gestao_conteudo_novo(request, tipo):
    config = _tipo_config(tipo)
    FormClass = get_content_form(tipo)
    form = FormClass(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, f'{config["singular"].capitalize()} criado com sucesso.')
        return redirect("site_publico:gestao_conteudo_lista", tipo=tipo)
    return render(request, "site_publico/gestao/form.html", {
        "form": form,
        "titulo": f'Novo {config["singular"]}',
        "descricao": f'Adicione conteúdo em {config["label"]}.',
        "voltar_url": "site_publico:gestao_conteudo_lista",
        "voltar_tipo": tipo,
    })


@login_required
def gestao_conteudo_editar(request, tipo, pk):
    config = _tipo_config(tipo)
    obj = get_object_or_404(config["model"], pk=pk)
    FormClass = get_content_form(tipo)
    form = FormClass(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f'{config["singular"].capitalize()} atualizado com sucesso.')
        return redirect("site_publico:gestao_conteudo_lista", tipo=tipo)
    imagem = getattr(obj, "imagem", None) or getattr(obj, "capa", None)
    return render(request, "site_publico/gestao/form.html", {
        "form": form,
        "titulo": f'Editar {config["singular"]}',
        "descricao": str(obj),
        "objeto": obj,
        "imagem_atual": imagem,
        "voltar_url": "site_publico:gestao_conteudo_lista",
        "voltar_tipo": tipo,
    })


@require_POST
@login_required
def gestao_conteudo_excluir(request, tipo, pk):
    config = _tipo_config(tipo)
    obj = get_object_or_404(config["model"], pk=pk)
    nome = str(obj)
    obj.delete()
    messages.success(request, f'"{nome}" removido.')
    return redirect("site_publico:gestao_conteudo_lista", tipo=tipo)
