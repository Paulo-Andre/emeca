from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    CONTENT_FORMS,
    BoletimAlunoManualForm,
    BoletimImportacaoForm,
    ConfiguracaoSiteForm,
    HomePageForm,
    FotoGaleriaLoteForm,
    PaginaPublicaForm,
    PeriodoBoletimForm,
    PeriodoBoletimNovoForm,
    SecaoPaginaForm,
    get_content_form,
)
from .boletim_importacao import ImportacaoBoletimErro, ler_planilha_boletim
from .boletim_services import (
    importar_dados_boletim,
    sincronizar_perfil_por_nome_declaracao,
)

from .models import (
    AlbumGaleria,
    ArquivoPaginaPublica,
    ConfiguracaoSite,
    FotoGaleria,
    AlunoBoletim,
    BoletimAluno,
    DisciplinaBoletim,
    NotaBoletim,
    PeriodoBoletim,
    PaginaPublica,
    SecaoPagina,
)


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
        "total_secoes": SecaoPagina.objects.count(),
    })


@login_required
def gestao_inicio(request):
    config, _ = ConfiguracaoSite.objects.get_or_create(pk=1)
    form = HomePageForm(request.POST or None, instance=config)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Página inicial atualizada.")
        return redirect("site_publico:gestao_inicio")

    secoes = list(SecaoPagina.objects.filter(pagina="home"))
    tipos_home = []
    for chave in ("carrossel", "avisos", "noticias", "atividades", "projetos", "eventos", "albuns"):
        item = CONTENT_FORMS[chave]
        tipos_home.append({
            "chave": chave,
            "label": item["label"],
            "icon": item["icon"],
            "total": item["model"].objects.count(),
        })

    return render(request, "site_publico/gestao/inicio.html", {
        "form": form,
        "secoes": secoes,
        "conteudos_home": tipos_home,
    })


@login_required
def gestao_boletins(request):
    periodos = (
        PeriodoBoletim.objects
        .prefetch_related("disciplinas", "boletins")
        .all()
    )
    return render(request, "site_publico/gestao/boletins.html", {
        "periodos": periodos,
    })


@login_required
def gestao_boletim_importar(request):
    form = BoletimImportacaoForm(request.POST or None, request.FILES or None)
    resultado = None

    if request.method == "POST" and form.is_valid():
        try:
            dados = ler_planilha_boletim(form.cleaned_data["arquivo"])
            resultado = importar_dados_boletim(dados)
        except (ImportacaoBoletimErro, ValueError) as exc:
            messages.error(request, str(exc))
        except Exception:
            messages.error(
                request,
                "Não foi possível concluir a importação da planilha. Nenhum dado parcial foi mantido.",
            )
        else:
            messages.success(
                request,
                (
                    f'{resultado["importados"]} aluno(s) importado(s) para '
                    f'{resultado["periodo"].titulo}. Revise os dados antes de publicar.'
                ),
            )

    return render(request, "site_publico/gestao/boletim_importar.html", {
        "form": form,
        "resultado_importacao": resultado,
    })


@login_required
def gestao_boletim_periodo_novo(request):
    form = PeriodoBoletimNovoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            periodo = form.save()
            nomes = []
            for linha in form.cleaned_data["disciplinas"].splitlines():
                nome = " ".join(linha.split()).strip()
                if nome and nome.lower() not in {item.lower() for item in nomes}:
                    nomes.append(nome)
            for ordem, nome in enumerate(nomes):
                DisciplinaBoletim.objects.create(
                    periodo=periodo,
                    nome=nome,
                    ordem=ordem,
                )
        messages.success(request, "Período de boletim criado.")
        return redirect("site_publico:gestao_boletim_periodo", pk=periodo.pk)

    return render(request, "site_publico/gestao/form.html", {
        "form": form,
        "titulo": "Novo período de boletim",
        "descricao": "Use esta opção apenas quando não existir uma planilha para importar. Com planilha, esses dados são extraídos automaticamente.",
        "voltar": "site_publico:gestao_boletins",
    })


@login_required
def gestao_boletim_periodo_editar(request, pk):
    periodo = get_object_or_404(
        PeriodoBoletim.objects.prefetch_related("disciplinas"),
        pk=pk,
    )
    form = PeriodoBoletimForm(request.POST or None, instance=periodo)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Dados gerais do boletim atualizados.")
        return redirect("site_publico:gestao_boletim_periodo_editar", pk=periodo.pk)

    return render(request, "site_publico/gestao/boletim_configurar.html", {
        "form": form,
        "periodo": periodo,
        "disciplinas": periodo.disciplinas.order_by("ordem", "id"),
    })


@require_POST
@login_required
def gestao_boletim_disciplina_adicionar(request, periodo_pk):
    periodo = get_object_or_404(PeriodoBoletim, pk=periodo_pk)
    nome = " ".join((request.POST.get("nome") or "").split()).strip()
    if not nome:
        messages.error(request, "Informe o nome da disciplina.")
        return redirect("site_publico:gestao_boletim_periodo_editar", pk=periodo.pk)

    if periodo.disciplinas.filter(nome__iexact=nome).exists():
        messages.error(request, "Essa disciplina já está cadastrada neste período.")
        return redirect("site_publico:gestao_boletim_periodo_editar", pk=periodo.pk)

    proxima_ordem = (periodo.disciplinas.aggregate(maior=Max("ordem")).get("maior") or -1) + 1
    DisciplinaBoletim.objects.create(
        periodo=periodo,
        nome=nome,
        ordem=proxima_ordem,
    )
    messages.success(request, f'Disciplina "{nome}" adicionada.')
    return redirect("site_publico:gestao_boletim_periodo_editar", pk=periodo.pk)


@require_POST
@login_required
def gestao_boletim_disciplina_editar(request, periodo_pk, disciplina_pk):
    periodo = get_object_or_404(PeriodoBoletim, pk=periodo_pk)
    disciplina = get_object_or_404(
        DisciplinaBoletim,
        pk=disciplina_pk,
        periodo=periodo,
    )
    nome = " ".join((request.POST.get("nome") or "").split()).strip()
    if not nome:
        messages.error(request, "O nome da disciplina não pode ficar vazio.")
        return redirect("site_publico:gestao_boletim_periodo_editar", pk=periodo.pk)

    if (
        periodo.disciplinas
        .filter(nome__iexact=nome)
        .exclude(pk=disciplina.pk)
        .exists()
    ):
        messages.error(request, "Já existe outra disciplina com esse nome.")
        return redirect("site_publico:gestao_boletim_periodo_editar", pk=periodo.pk)

    disciplina.nome = nome
    disciplina.save(update_fields=["nome"])
    messages.success(request, "Nome da disciplina atualizado sem alterar as notas vinculadas.")
    return redirect("site_publico:gestao_boletim_periodo_editar", pk=periodo.pk)


@require_POST
@login_required
def gestao_boletim_disciplina_excluir(request, periodo_pk, disciplina_pk):
    periodo = get_object_or_404(PeriodoBoletim, pk=periodo_pk)
    disciplina = get_object_or_404(
        DisciplinaBoletim,
        pk=disciplina_pk,
        periodo=periodo,
    )
    nome = disciplina.nome
    disciplina.delete()
    messages.success(
        request,
        f'Disciplina "{nome}" removida. As notas vinculadas a ela também foram removidas.',
    )
    return redirect("site_publico:gestao_boletim_periodo_editar", pk=periodo.pk)


@login_required
def gestao_boletim_periodo(request, pk):
    periodo = get_object_or_404(
        PeriodoBoletim.objects.prefetch_related(
            "disciplinas",
            "boletins__aluno",
            "boletins__resultados",
        ),
        pk=pk,
    )
    boletins = list(
        periodo.boletins.select_related("aluno").order_by(
            "numero_chamada",
            "aluno__nome",
        )
    )
    linhas = []
    for boletim_obj in boletins:
        aluno = boletim_obj.aluno
        acesso_pronto = bool(
            aluno.data_nascimento
            and ((aluno.cpf_mae or "").strip() or (aluno.cpf_responsavel or "").strip())
        )
        linhas.append({
            "boletim": boletim_obj,
            "acesso_pronto": acesso_pronto,
        })

    return render(request, "site_publico/gestao/boletim_periodo.html", {
        "periodo": periodo,
        "linhas": linhas,
        "disciplinas": periodo.disciplinas.all(),
    })


@require_POST
@login_required
def gestao_boletim_publicar(request, pk):
    periodo = get_object_or_404(PeriodoBoletim, pk=pk)
    periodo.publicado = not periodo.publicado
    periodo.save(update_fields=["publicado", "atualizado_em"])
    messages.success(
        request,
        "Boletim publicado para os responsáveis."
        if periodo.publicado
        else "Boletim retirado da consulta pública.",
    )
    return redirect("site_publico:gestao_boletim_periodo", pk=periodo.pk)


@require_POST
@login_required
def gestao_boletim_periodo_excluir(request, pk):
    periodo = get_object_or_404(PeriodoBoletim, pk=pk)
    titulo = periodo.titulo
    periodo.delete()
    messages.success(request, f'Período "{titulo}" removido.')
    return redirect("site_publico:gestao_boletins")


def _decimal_post(valor):
    valor = (valor or "").strip().replace(",", ".")
    if not valor:
        return None
    try:
        numero = Decimal(valor)
    except InvalidOperation as exc:
        raise ValueError("Nota inválida.") from exc
    if numero < 0:
        raise ValueError("A nota não pode ser negativa.")
    return numero.quantize(Decimal("0.01"))


def _inteiro_post(valor):
    valor = (valor or "").strip()
    if not valor:
        return None
    try:
        numero = int(valor)
    except ValueError as exc:
        raise ValueError("Faltas devem ser um número inteiro.") from exc
    if numero < 0:
        raise ValueError("Faltas não podem ser negativas.")
    return numero


@login_required
def gestao_boletim_aluno(request, periodo_pk, boletim_pk=None):
    periodo = get_object_or_404(
        PeriodoBoletim.objects.prefetch_related("disciplinas"),
        pk=periodo_pk,
    )
    boletim_obj = None
    perfil_fixo = None
    resultados_atuais = {}

    if boletim_pk is not None:
        boletim_obj = get_object_or_404(
            BoletimAluno.objects.select_related("aluno"),
            pk=boletim_pk,
            periodo=periodo,
        )
        perfil_fixo = boletim_obj.aluno
        resultados_atuais = {
            item.disciplina_id: item
            for item in boletim_obj.resultados.select_related("disciplina")
        }

    initial = {
        "numero_chamada": boletim_obj.numero_chamada if boletim_obj else None,
        "faltas_totais": boletim_obj.faltas_totais if boletim_obj else None,
    }

    form = BoletimAlunoManualForm(
        request.POST or None,
        perfil_fixo=perfil_fixo,
        initial=initial,
    )

    if request.method == "POST" and form.is_valid():
        status_declaracao = None
        try:
            with transaction.atomic():
                nome = form.cleaned_data["nome_aluno"]

                if boletim_obj is not None:
                    perfil = boletim_obj.aluno
                else:
                    # Reutiliza um perfil inequívoco do mesmo aluno quando já
                    # houver boletins de outros períodos; em caso de duplicidade,
                    # cria um perfil novo e não escolhe silenciosamente.
                    candidatos_perfil = list(
                        AlunoBoletim.objects.filter(nome__iexact=nome).order_by("pk")[:2]
                    )
                    perfil = (
                        candidatos_perfil[0]
                        if len(candidatos_perfil) == 1
                        else AlunoBoletim.objects.create(nome=nome)
                    )

                if perfil.nome != nome:
                    perfil.nome = nome
                    perfil.save(update_fields=["nome", "atualizado_em"])

                # CPF e data de nascimento não são editados no boletim.
                # A identidade é sincronizada automaticamente com Declarações,
                # usando o mesmo nome da criança.
                perfil, status_declaracao = sincronizar_perfil_por_nome_declaracao(
                    perfil,
                    nome,
                )

                if boletim_obj is None:
                    boletim_obj, criado = BoletimAluno.objects.get_or_create(
                        periodo=periodo,
                        aluno=perfil,
                        defaults={
                            "numero_chamada": form.cleaned_data["numero_chamada"],
                            "faltas_totais": form.cleaned_data.get("faltas_totais"),
                        },
                    )
                    if not criado:
                        boletim_obj.numero_chamada = form.cleaned_data["numero_chamada"]
                        boletim_obj.faltas_totais = form.cleaned_data.get("faltas_totais")
                        boletim_obj.save(
                            update_fields=[
                                "numero_chamada",
                                "faltas_totais",
                                "atualizado_em",
                            ]
                        )
                else:
                    boletim_obj.numero_chamada = form.cleaned_data["numero_chamada"]
                    boletim_obj.faltas_totais = form.cleaned_data.get("faltas_totais")
                    boletim_obj.save(
                        update_fields=[
                            "numero_chamada",
                            "faltas_totais",
                            "atualizado_em",
                        ]
                    )

                for disciplina in periodo.disciplinas.all():
                    nota = _decimal_post(request.POST.get(f"nota_{disciplina.pk}"))
                    NotaBoletim.objects.update_or_create(
                        boletim=boletim_obj,
                        disciplina=disciplina,
                        defaults={"nota": nota, "faltas": None},
                    )
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                "Nome do aluno, notas e faltas totais foram salvos.",
            )
            if status_declaracao == "nao_encontrado":
                messages.warning(
                    request,
                    "Não foi encontrada uma declaração com esse mesmo nome. "
                    "CPF e data de nascimento não foram vinculados ao boletim.",
                )
            elif status_declaracao == "ambiguo":
                messages.warning(
                    request,
                    "Há mais de uma declaração com esse mesmo nome. "
                    "CPF e data de nascimento não foram vinculados para evitar associação incorreta.",
                )
            return redirect("site_publico:gestao_boletim_periodo", pk=periodo.pk)

    linhas_notas = []
    for disciplina in periodo.disciplinas.all():
        atual = resultados_atuais.get(disciplina.pk)
        linhas_notas.append({
            "disciplina": disciplina,
            "nota": (
                request.POST.get(f"nota_{disciplina.pk}")
                if request.method == "POST"
                else (atual.nota if atual else "")
            ),
        })

    return render(request, "site_publico/gestao/boletim_aluno.html", {
        "periodo": periodo,
        "boletim_obj": boletim_obj,
        "form": form,
        "linhas_notas": linhas_notas,
    })


@login_required
def gestao_secoes(request):
    grupos = []
    for chave_pagina, nome_pagina in SecaoPagina.PAGINAS:
        secoes = list(SecaoPagina.objects.filter(pagina=chave_pagina))
        if secoes:
            grupos.append({
                "chave": chave_pagina,
                "nome": nome_pagina,
                "secoes": secoes,
            })
    return render(request, "site_publico/gestao/secoes.html", {
        "grupos": grupos,
    })


@login_required
def gestao_secao_editar(request, chave):
    secao = get_object_or_404(SecaoPagina, chave=chave)
    form = SecaoPaginaForm(request.POST or None, request.FILES or None, instance=secao)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f'Bloco "{secao.nome}" atualizado.')
        return redirect("site_publico:gestao_secoes")
    voltar_href = ""
    if secao.pagina == "home" and request.GET.get("origem") == "home":
        voltar_href = reverse("site_publico:gestao_inicio") + "#blocos"

    return render(request, "site_publico/gestao/form.html", {
        "form": form,
        "titulo": secao.nome,
        "descricao": "Edite o conteúdo visual deste bloco. Menus e textos de botões permanecem protegidos.",
        "objeto": secao,
        "imagem_atual": secao.imagem,
        "voltar_href": voltar_href,
        "voltar": "site_publico:gestao_inicio" if secao.pagina == "home" else "site_publico:gestao_secoes",
    })


@login_required
def gestao_configuracao(request):
    config, _ = ConfiguracaoSite.objects.get_or_create(pk=1)
    form = ConfiguracaoSiteForm(request.POST or None, request.FILES or None, instance=config)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Informações institucionais atualizadas.")
        return redirect("site_publico:gestao_configuracao")
    return render(request, "site_publico/gestao/form.html", {
        "form": form,
        "titulo": "Informações institucionais",
        "descricao": "Edite os textos institucionais, canais de atendimento e a logo exibida no site.",
        "imagem_atual": config.logo_site,
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
    visibilidade_alterada = False

    if request.method == "POST":
        nova_ativa = request.POST.get("ativa") == "on"
        if pagina.ativa != nova_ativa:
            pagina.ativa = nova_ativa
            pagina.save(update_fields=["ativa", "atualizado_em"])
            visibilidade_alterada = True

    form = PaginaPublicaForm(request.POST or None, request.FILES or None, instance=pagina)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f'Página "{pagina.nome}" atualizada.')
        return redirect("site_publico:gestao_paginas")

    if request.method == "POST" and visibilidade_alterada:
        estado = "ativada" if pagina.ativa else "desativada"
        messages.warning(
            request,
            f'A página "{pagina.nome}" foi {estado}, mas há outro campo que precisa ser corrigido antes de salvar o restante.',
        )

    return render(request, "site_publico/gestao/form.html", {
        "form": form,
        "titulo": f"Editar página: {pagina.nome}",
        "descricao": "Altere os textos, imagem/PDF principal e disponibilidade pública desta página.",
        "objeto": pagina,
        "imagem_atual": pagina.imagem_capa,
        "imagem_atual_e_pdf": pagina.capa_e_pdf,
        "pagina_arquivos": pagina.arquivos.all(),
        "permitir_documentos": True,
        "voltar": "site_publico:gestao_paginas",
    })


@require_POST
@login_required
def gestao_pagina_documentos_adicionar(request, chave):
    pagina = get_object_or_404(PaginaPublica, chave=chave)
    arquivos = request.FILES.getlist("documentos")

    if not arquivos:
        messages.error(request, "Selecione pelo menos um documento.")
        return redirect("site_publico:gestao_pagina_editar", chave=pagina.chave)

    candidatos = []
    try:
        for enviado in arquivos:
            candidato = ArquivoPaginaPublica(
                pagina=pagina,
                titulo=enviado.name.rsplit("/", 1)[-1][:180],
                arquivo=enviado,
            )
            candidato.full_clean()
            candidatos.append(candidato)
    except ValidationError as exc:
        mensagens = []
        for erros in exc.message_dict.values():
            mensagens.extend(erros)
        messages.error(request, " ".join(mensagens) or "Um dos arquivos não é permitido.")
        return redirect("site_publico:gestao_pagina_editar", chave=pagina.chave)

    for candidato in candidatos:
        candidato.save()

    total = len(candidatos)
    messages.success(
        request,
        f"{total} documento{'s' if total != 1 else ''} adicionado{'s' if total != 1 else ''} à página.",
    )
    return redirect("site_publico:gestao_pagina_editar", chave=pagina.chave)


@require_POST
@login_required
def gestao_pagina_documento_excluir(request, chave, pk):
    pagina = get_object_or_404(PaginaPublica, chave=chave)
    documento = get_object_or_404(ArquivoPaginaPublica, pk=pk, pagina=pagina)
    documento.arquivo.delete(save=False)
    documento.delete()
    messages.success(request, "Documento removido da página.")
    return redirect("site_publico:gestao_pagina_editar", chave=pagina.chave)


@require_POST
@login_required
def gestao_pagina_toggle(request, chave):
    pagina = get_object_or_404(PaginaPublica, chave=chave)
    pagina.ativa = not pagina.ativa
    pagina.save(update_fields=["ativa", "atualizado_em"])
    estado = "ativada" if pagina.ativa else "desativada"
    messages.success(request, f'Página "{pagina.nome}" {estado}.')
    destino = (request.POST.get("next") or "").strip()
    if destino and url_has_allowed_host_and_scheme(
        destino,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(destino)
    return redirect("site_publico:gestao_paginas")


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

    if tipo == "fotos":
        initial = {}
        if request.method == "GET" and request.GET.get("album"):
            initial["album_existente"] = request.GET.get("album")
        form = FotoGaleriaLoteForm(
            request.POST or None,
            request.FILES or None,
            initial=initial,
        )
        if request.method == "POST" and form.is_valid():
            with transaction.atomic():
                album = form.cleaned_data["album_existente"]
                if album is None:
                    album = AlbumGaleria.objects.create(
                        titulo=form.cleaned_data["novo_album"].strip(),
                        descricao=form.cleaned_data.get("descricao_album", ""),
                        data_evento=form.cleaned_data.get("data_evento"),
                        ativo=True,
                    )

                ultima_ordem = (
                    album.fotos.aggregate(maior=Max("ordem")).get("maior")
                    or 0
                )
                fotos = form.cleaned_data["fotos"]
                for indice, imagem in enumerate(fotos, start=1):
                    FotoGaleria.objects.create(
                        album=album,
                        imagem=imagem,
                        ordem=ultima_ordem + indice,
                    )

                if not album.foto_capa_id:
                    primeira_foto = album.fotos.first()
                    if primeira_foto:
                        album.foto_capa = primeira_foto
                        album.save(update_fields=["foto_capa"])

            total = len(form.cleaned_data["fotos"])
            messages.success(
                request,
                f'{total} foto{"s" if total != 1 else ""} adicionada{"s" if total != 1 else ""} ao álbum "{album.titulo}".',
            )
            return redirect("site_publico:gestao_conteudo_lista", tipo="fotos")

        return render(request, "site_publico/gestao/fotos_lote.html", {
            "form": form,
            "config": config,
        })

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
    album_fotos = None
    if tipo == "albuns":
        album_fotos = obj.fotos.all()
        if obj.foto_capa_id:
            imagem = obj.foto_capa.imagem

    return render(request, "site_publico/gestao/form.html", {
        "form": form,
        "titulo": f'Editar {config["singular"]}',
        "descricao": str(obj),
        "objeto": obj,
        "imagem_atual": imagem,
        "album_fotos": album_fotos,
        "mostrar_seletor_capa_album": tipo == "albuns",
        "voltar_url": "site_publico:gestao_conteudo_lista",
        "voltar_tipo": tipo,
    })


@require_POST
@login_required
def gestao_album_definir_capa(request, album_pk, foto_pk):
    album = get_object_or_404(AlbumGaleria, pk=album_pk)
    foto = get_object_or_404(FotoGaleria, pk=foto_pk, album=album)
    album.foto_capa = foto
    album.save(update_fields=["foto_capa"])
    messages.success(request, "Foto definida como capa do álbum.")
    return redirect("site_publico:gestao_conteudo_editar", tipo="albuns", pk=album.pk)


@require_POST
@login_required
def gestao_conteudo_excluir(request, tipo, pk):
    config = _tipo_config(tipo)
    obj = get_object_or_404(config["model"], pk=pk)
    nome = str(obj)
    obj.delete()
    messages.success(request, f'"{nome}" removido.')
    return redirect("site_publico:gestao_conteudo_lista", tipo=tipo)
