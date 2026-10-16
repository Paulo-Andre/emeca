import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.cache import never_cache

from .services import pagina_publica_required, paginas_ativas_dict
from .boletim_services import (
    aplicar_headers_privacidade,
    consulta_bloqueada,
    conceder_acesso_boletim,
    gerar_pdf_boletim,
    ler_acesso_boletim,
    localizar_alunos_por_credenciais,
    registrar_tentativa,
)
from .forms import BoletimConsultaForm

from .models import (
    AlbumGaleria,
    AtividadeJogo,
    Aviso,
    ConfiguracaoSite,
    DestaqueHome,
    DocumentoPublico,
    Evento,
    MensagemContato,
    Noticia,
    AlunoBoletim,
    BoletimAluno,
    PerguntaFrequente,
    Projeto,
)


def _config():
    return ConfiguracaoSite.objects.first()


def _visiveis_no_periodo(queryset):
    agora = timezone.now()
    return queryset.filter(
        ativo=True,
    ).filter(
        Q(inicio__isnull=True) | Q(inicio__lte=agora),
        Q(fim__isnull=True) | Q(fim__gte=agora),
    )


def _base_context():
    return {"config_site": _config()}


def _slides_home(agora, paginas_ativas):
    """Monta o carrossel com destaques, notícias e fotos da galeria."""
    slides = []

    links_paginas = {
        "/a-escola/": "escola",
        "/vida-escolar/": "vida_escolar",
        "/atividades-jogos/": "atividades",
        "/projetos/": "projetos",
        "/noticias/": "noticias",
        "/galeria/": "galeria",
        "/matricula-escolar/": "matricula",
        "/boletim/": "boletim",
        "/documentos/": "documentos",
        "/perguntas-frequentes/": "faq",
        "/contato/": "contato",
    }

    for item in _visiveis_no_periodo(DestaqueHome.objects.all())[:5]:
        link = item.link
        chave_link = next(
            (chave for prefixo, chave in links_paginas.items() if link.startswith(prefixo)),
            None,
        ) if link else None
        if chave_link and not paginas_ativas.get(chave_link, True):
            link = ""

        slides.append({
            "rotulo": item.get_categoria_display(),
            "titulo": item.titulo,
            "descricao": item.descricao,
            "imagem": item.imagem.url if item.imagem else "",
            "link": link,
            "texto_botao": item.texto_botao or "Saiba mais",
        })

    if paginas_ativas.get("noticias", True):
        noticias = (
            Noticia.objects
            .filter(ativo=True, publicado_em__lte=agora)
            .exclude(imagem="")
            .order_by("-destaque", "-publicado_em")
        )
        for item in noticias[:4]:
            if len(slides) >= 7:
                break
            slides.append({
                "rotulo": "Notícia",
                "titulo": item.titulo,
                "descricao": item.resumo,
                "imagem": item.imagem.url,
                "link": item.get_absolute_url(),
                "texto_botao": "Ler notícia",
            })

    if paginas_ativas.get("galeria", True):
        albuns = (
            AlbumGaleria.objects
            .filter(ativo=True)
            .select_related("foto_capa")
            .prefetch_related("fotos")
            .order_by("-data_evento", "-id")
        )
        for item in albuns[:5]:
            if len(slides) >= 8:
                break
            fotos = list(item.fotos.all())
            imagem = (
                item.foto_capa.imagem.url
                if item.foto_capa_id
                else (item.capa.url if item.capa else (fotos[0].imagem.url if fotos else ""))
            )
            if not imagem:
                continue
            slides.append({
                "rotulo": "Fotos",
                "titulo": item.titulo,
                "descricao": item.descricao,
                "imagem": imagem,
                "link": item.get_absolute_url(),
                "texto_botao": "Ver fotos",
            })

    return slides


def configuracao_publica(request):
    config = _config()
    return JsonResponse({
        "paginas": paginas_ativas_dict(),
        "site": {
            "nome_escola": config.nome_escola if config else "E. M. Egídio Cordeiro Aquino",
            "subtitulo": config.subtitulo if config else "Educação pública, acolhimento e aprendizagem",
        },
    })


def home(request):
    agora = timezone.now()
    paginas_ativas = paginas_ativas_dict()
    contexto = _base_context()
    contexto.update({
        "slides_home": _slides_home(agora, paginas_ativas),
        "avisos": _visiveis_no_periodo(Aviso.objects.all())[:4],
        "noticias": (
            Noticia.objects.filter(ativo=True, publicado_em__lte=agora)[:3]
            if paginas_ativas.get("noticias", True) else []
        ),
        "atividades": (
            AtividadeJogo.objects.filter(ativo=True, destaque=True)[:4]
            if paginas_ativas.get("atividades", True) else []
        ),
        "projetos": (
            Projeto.objects.filter(ativo=True, destaque=True)[:3]
            if paginas_ativas.get("projetos", True) else []
        ),
        "eventos": Evento.objects.filter(ativo=True, inicio__gte=agora)[:4],
        "albuns": (
            AlbumGaleria.objects.filter(ativo=True).select_related("foto_capa").prefetch_related("fotos")[:4]
            if paginas_ativas.get("galeria", True) else []
        ),
        "paginas_ativas_home": paginas_ativas,
    })
    return render(request, "site_publico/home.html", contexto)


@pagina_publica_required("escola")
def escola(request):
    return render(request, "site_publico/escola.html", _base_context())


@pagina_publica_required("vida_escolar")
def vida_escolar(request):
    return render(request, "site_publico/vida_escolar.html", _base_context())


@pagina_publica_required("atividades")
def atividades(request):
    qs = AtividadeJogo.objects.filter(ativo=True)
    tipo = request.GET.get("tipo", "").strip().upper()
    if tipo:
        qs = qs.filter(tipo=tipo)
    contexto = _base_context()
    contexto.update({"itens": qs, "tipo_atual": tipo, "tipos": AtividadeJogo.TIPOS})
    return render(request, "site_publico/atividades.html", contexto)


@pagina_publica_required("atividades")
def atividade(request, slug):
    item = get_object_or_404(AtividadeJogo, slug=slug, ativo=True)
    contexto = _base_context()
    contexto["item"] = item
    return render(request, "site_publico/atividade.html", contexto)


@pagina_publica_required("projetos")
def projetos(request):
    contexto = _base_context()
    contexto["itens"] = Projeto.objects.filter(ativo=True)
    return render(request, "site_publico/projetos.html", contexto)


@pagina_publica_required("projetos")
def projeto(request, slug):
    item = get_object_or_404(Projeto, slug=slug, ativo=True)
    contexto = _base_context()
    contexto["item"] = item
    return render(request, "site_publico/projeto.html", contexto)


@pagina_publica_required("noticias")
def noticias(request):
    agora = timezone.now()
    contexto = _base_context()
    contexto["itens"] = Noticia.objects.filter(ativo=True, publicado_em__lte=agora)
    return render(request, "site_publico/noticias.html", contexto)


@pagina_publica_required("noticias")
def noticia(request, slug):
    item = get_object_or_404(Noticia, slug=slug, ativo=True, publicado_em__lte=timezone.now())
    contexto = _base_context()
    contexto["item"] = item
    return render(request, "site_publico/noticia.html", contexto)


@pagina_publica_required("galeria")
def galeria(request):
    contexto = _base_context()
    contexto["itens"] = AlbumGaleria.objects.filter(ativo=True).select_related("foto_capa").prefetch_related("fotos")
    return render(request, "site_publico/galeria.html", contexto)


@pagina_publica_required("galeria")
def album(request, slug):
    item = get_object_or_404(
        AlbumGaleria.objects.select_related("foto_capa").prefetch_related("fotos"),
        slug=slug,
        ativo=True,
    )
    contexto = _base_context()
    contexto["item"] = item
    return render(request, "site_publico/album.html", contexto)


@pagina_publica_required("matricula")
def matricula_landing(request):
    return render(request, "site_publico/matricula.html", _base_context())


@pagina_publica_required("boletim")
@never_cache
def boletim(request):
    contexto = _base_context()
    form = BoletimConsultaForm(request.POST or None)
    bloqueada = consulta_bloqueada(request)

    if request.method == "POST":
        if bloqueada:
            messages.error(
                request,
                "Muitas tentativas foram realizadas. Aguarde alguns minutos antes de tentar novamente.",
            )
        elif form.is_valid():
            encontrados = localizar_alunos_por_credenciais(
                form.cleaned_data["cpf"],
                form.cleaned_data["data_nascimento"],
            )
            if encontrados:
                registrar_tentativa(request, sucesso=True)
                conceder_acesso_boletim(request, encontrados)
                return redirect("site_publico:boletim_acesso")

            # Diferencia credenciais incorretas de um boletim que existe,
            # mas ainda está em rascunho na gestão.
            encontrados_nao_publicados = localizar_alunos_por_credenciais(
                form.cleaned_data["cpf"],
                form.cleaned_data["data_nascimento"],
                somente_publicados=False,
            )
            registrar_tentativa(request)
            if encontrados_nao_publicados:
                messages.warning(
                    request,
                    "Os dados do estudante foram reconhecidos, mas o boletim ainda não foi publicado pela escola.",
                )
            else:
                messages.error(
                    request,
                    "Não foi possível localizar um boletim com os dados informados. Confira o CPF e a data de nascimento.",
                )
        else:
            registrar_tentativa(request)

    contexto.update({
        "form": form,
        "consulta_bloqueada": bloqueada,
    })
    response = render(request, "site_publico/boletim.html", contexto)
    return aplicar_headers_privacidade(response)


@pagina_publica_required("boletim")
@never_cache
def boletim_acesso(request):
    ids = ler_acesso_boletim(request)
    if not ids:
        messages.error(request, "O acesso ao boletim expirou. Informe os dados novamente.")
        return redirect("site_publico:boletim")

    alunos = list(
        AlunoBoletim.objects
        .filter(pk__in=ids, boletins__periodo__publicado=True)
        .distinct()
        .order_by("nome")
    )
    if not alunos:
        messages.error(request, "Nenhum boletim publicado está disponível para este acesso.")
        return redirect("site_publico:boletim")

    boletins = list(
        BoletimAluno.objects
        .filter(aluno_id__in=ids, periodo__publicado=True)
        .select_related("aluno", "periodo")
        .prefetch_related("resultados__disciplina")
        .order_by("-periodo__ano", "-periodo__numero", "aluno__nome")
    )
    boletins_por_aluno = {aluno.pk: [] for aluno in alunos}
    for item in boletins:
        boletins_por_aluno.setdefault(item.aluno_id, []).append(item)
    alunos_contexto = [
        {
            "aluno": aluno,
            "boletins": boletins_por_aluno.get(aluno.pk, []),
        }
        for aluno in alunos
    ]

    solicitado = request.GET.get("boletim")
    selecionado = None
    if solicitado and solicitado.isdigit():
        selecionado = next(
            (item for item in boletins if item.pk == int(solicitado)),
            None,
        )
    if selecionado is None and boletins:
        selecionado = boletins[0]

    contexto = _base_context()
    contexto.update({
        "alunos_boletim": alunos,
        "alunos_contexto": alunos_contexto,
        "boletins_disponiveis": boletins,
        "boletim_selecionado": selecionado,
    })
    response = render(request, "site_publico/boletim_resultado.html", contexto)
    return aplicar_headers_privacidade(response)


@pagina_publica_required("boletim")
@never_cache
def boletim_pdf(request, pk):
    ids = ler_acesso_boletim(request)
    if not ids:
        raise Http404

    boletim_obj = get_object_or_404(
        BoletimAluno.objects
        .select_related("aluno", "periodo")
        .prefetch_related("resultados__disciplina"),
        pk=pk,
        aluno_id__in=ids,
        periodo__publicado=True,
    )
    arquivo = gerar_pdf_boletim(boletim_obj, _config())
    nome = slugify(boletim_obj.aluno.nome) or "aluno"
    periodo = slugify(boletim_obj.periodo.nome_periodo) or "periodo"
    response = FileResponse(
        arquivo,
        as_attachment=True,
        filename=f"boletim-{nome}-{periodo}-{boletim_obj.periodo.ano}.pdf",
        content_type="application/pdf",
    )
    return aplicar_headers_privacidade(response)


@pagina_publica_required("documentos")
def documentos(request):
    contexto = _base_context()
    contexto["itens"] = DocumentoPublico.objects.filter(ativo=True)
    return render(request, "site_publico/documentos.html", contexto)


@pagina_publica_required("faq")
def faq(request):
    contexto = _base_context()
    contexto["itens"] = PerguntaFrequente.objects.filter(ativo=True)
    return render(request, "site_publico/faq.html", contexto)


@pagina_publica_required("contato")
def contato(request):
    contexto = _base_context()
    if request.method == "POST":
        # Campo armadilha simples para bots.
        if request.POST.get("website"):
            return redirect("site_publico:contato")

        nome = request.POST.get("nome", "").strip()[:160]
        email = request.POST.get("email", "").strip()[:254]
        telefone = request.POST.get("telefone", "").strip()[:40]
        assunto = request.POST.get("assunto", "").strip()[:180]
        mensagem = request.POST.get("mensagem", "").strip()[:4000]

        if not nome or not assunto or not mensagem:
            messages.error(request, "Preencha nome, assunto e mensagem.")
        else:
            MensagemContato.objects.create(
                nome=nome,
                email=email,
                telefone=telefone,
                assunto=assunto,
                mensagem=mensagem,
            )
            messages.success(request, "Mensagem enviada para a escola.")
            return redirect("site_publico:contato")
    return render(request, "site_publico/contato.html", contexto)


def media_publica(request, arquivo):
    # Só arquivos pertencentes ao site público podem ser expostos por esta rota.
    if not arquivo.startswith("site_publico/"):
        raise Http404

    raiz = Path(settings.MEDIA_ROOT).resolve()
    destino = (raiz / arquivo).resolve()
    if raiz != destino and raiz not in destino.parents:
        raise Http404
    if not destino.is_file():
        raise Http404

    permitidas = {
        ".jpg", ".jpeg", ".png", ".webp",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".odt",
    }
    if destino.suffix.lower() not in permitidas:
        raise Http404

    content_type = mimetypes.guess_type(destino.name)[0] or "application/octet-stream"
    resposta = FileResponse(destino.open("rb"), content_type=content_type)
    if destino.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        resposta["Content-Disposition"] = f'attachment; filename="{destino.name}"'
    resposta["X-Content-Type-Options"] = "nosniff"
    return resposta
