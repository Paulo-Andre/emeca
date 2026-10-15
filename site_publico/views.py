import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

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


def _slides_home(agora):
    """Monta o carrossel com destaques, notícias e fotos da galeria."""
    slides = []

    for item in _visiveis_no_periodo(DestaqueHome.objects.all())[:5]:
        slides.append({
            "rotulo": item.get_categoria_display(),
            "titulo": item.titulo,
            "descricao": item.descricao,
            "imagem": item.imagem.url if item.imagem else "",
            "link": item.link,
            "texto_botao": item.texto_botao or "Saiba mais",
        })

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

    albuns = (
        AlbumGaleria.objects
        .filter(ativo=True)
        .prefetch_related("fotos")
        .order_by("-data_evento", "-id")
    )
    for item in albuns[:5]:
        if len(slides) >= 8:
            break
        fotos = list(item.fotos.all())
        imagem = item.capa.url if item.capa else (fotos[0].imagem.url if fotos else "")
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


def home(request):
    agora = timezone.now()
    contexto = _base_context()
    contexto.update({
        "slides_home": _slides_home(agora),
        "avisos": _visiveis_no_periodo(Aviso.objects.all())[:4],
        "noticias": Noticia.objects.filter(ativo=True, publicado_em__lte=agora)[:3],
        "atividades": AtividadeJogo.objects.filter(ativo=True, destaque=True)[:4],
        "projetos": Projeto.objects.filter(ativo=True, destaque=True)[:3],
        "eventos": Evento.objects.filter(ativo=True, inicio__gte=agora)[:4],
        "albuns": AlbumGaleria.objects.filter(ativo=True).prefetch_related("fotos")[:4],
    })
    return render(request, "site_publico/home.html", contexto)


def escola(request):
    return render(request, "site_publico/escola.html", _base_context())


def vida_escolar(request):
    return render(request, "site_publico/vida_escolar.html", _base_context())


def atividades(request):
    qs = AtividadeJogo.objects.filter(ativo=True)
    tipo = request.GET.get("tipo", "").strip().upper()
    if tipo:
        qs = qs.filter(tipo=tipo)
    contexto = _base_context()
    contexto.update({"itens": qs, "tipo_atual": tipo, "tipos": AtividadeJogo.TIPOS})
    return render(request, "site_publico/atividades.html", contexto)


def atividade(request, slug):
    item = get_object_or_404(AtividadeJogo, slug=slug, ativo=True)
    contexto = _base_context()
    contexto["item"] = item
    return render(request, "site_publico/atividade.html", contexto)


def projetos(request):
    contexto = _base_context()
    contexto["itens"] = Projeto.objects.filter(ativo=True)
    return render(request, "site_publico/projetos.html", contexto)


def projeto(request, slug):
    item = get_object_or_404(Projeto, slug=slug, ativo=True)
    contexto = _base_context()
    contexto["item"] = item
    return render(request, "site_publico/projeto.html", contexto)


def noticias(request):
    agora = timezone.now()
    contexto = _base_context()
    contexto["itens"] = Noticia.objects.filter(ativo=True, publicado_em__lte=agora)
    return render(request, "site_publico/noticias.html", contexto)


def noticia(request, slug):
    item = get_object_or_404(Noticia, slug=slug, ativo=True, publicado_em__lte=timezone.now())
    contexto = _base_context()
    contexto["item"] = item
    return render(request, "site_publico/noticia.html", contexto)


def galeria(request):
    contexto = _base_context()
    contexto["itens"] = AlbumGaleria.objects.filter(ativo=True).prefetch_related("fotos")
    return render(request, "site_publico/galeria.html", contexto)


def album(request, slug):
    item = get_object_or_404(
        AlbumGaleria.objects.prefetch_related("fotos"),
        slug=slug,
        ativo=True,
    )
    contexto = _base_context()
    contexto["item"] = item
    return render(request, "site_publico/album.html", contexto)


def matricula_landing(request):
    return render(request, "site_publico/matricula.html", _base_context())


def boletim(request):
    return render(request, "site_publico/boletim.html", _base_context())


def documentos(request):
    contexto = _base_context()
    contexto["itens"] = DocumentoPublico.objects.filter(ativo=True)
    return render(request, "site_publico/documentos.html", contexto)


def faq(request):
    contexto = _base_context()
    contexto["itens"] = PerguntaFrequente.objects.filter(ativo=True)
    return render(request, "site_publico/faq.html", contexto)


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
