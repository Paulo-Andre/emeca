import json
import time
import uuid
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.forms import modelformset_factory
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .academico import (
    indicadores_aluno,
    matriz_para_ano,
    painel_geral,
    relatorio_completo_aluno,
    relatorio_integridade,
)
from .auditoria import registrar_auditoria
from .documentos import (
    contexto_snapshot,
    emitir_documento,
    mascarar_codigo,
    mascarar_nome,
    qr_code_data_uri,
    validar_documento,
)
from .forms import (
    AlunoCadastroForm,
    ConfiguracaoAnoForm,
    ImportacaoAlunosForm,
    ImportacaoNotasPdfForm,
    UF_CHOICES,
)
from .importacao_alunos import (
    ErroImportacao,
    analisar_lista,
    aplicar_lista,
    ler_lista_alunos,
)
from .importacao_notas_pdf import (
    ErroImportacaoNotasPdf,
    analisar_notas_pdf,
    aplicar_notas_pdf,
    extrair_notas_pdf,
)
from .models import (
    Aluno,
    ConfiguracaoAno,
    DocumentoHistorico,
    Nota,
    RegistroAcademico,
)
from .services import historico_do_aluno, historico_oficial_do_aluno


COMPONENTES_EDITOR = [
    Nota.LINGUA_PORTUGUESA,
    Nota.ARTE,
    Nota.EDUCACAO_FISICA,
    Nota.LINGUA_INGLESA,
    Nota.MATEMATICA,
    Nota.CIENCIAS,
    Nota.GEOGRAFIA,
    Nota.HISTORIA,
    Nota.EDUCACAO_RELIGIOSA,
]
ROTULOS_COMPONENTES = dict(Nota.COMPONENTES)


RESULTADO_CHOICES = [
    ("", "Selecione..."),
    ("APROVADO", "Aprovado"),
    ("REPROVADO", "Reprovado"),
    ("APTO", "Apto"),
    ("APTA", "Apta"),
    ("EM CONTINUIDADE", "Em continuidade"),
    ("EM CURSO", "Em curso"),
]


def _opcoes_com_valor_atual(opcoes, atual):
    atuais = {valor for valor, _ in opcoes}
    if atual and atual not in atuais:
        return list(opcoes) + [(atual, atual)]
    return opcoes


def _registros_por_serie(aluno):
    if not aluno or not aluno.pk:
        return {}

    registros = {}
    queryset = (
        aluno.registros_academicos
        .prefetch_related("notas")
        .filter(
            serie__gte=1,
            serie__lte=5,
            ativo_no_historico=True,
        )
        .order_by("serie", "ano", "id")
    )
    for registro in queryset:
        registros[registro.serie] = registro
    return registros


def _anos_editor(aluno=None, post=None):
    registros = _registros_por_serie(aluno)
    anos = []

    for serie in range(1, 6):
        registro = registros.get(serie)
        notas_db = (
            {nota.componente: nota.valor for nota in registro.notas.all()}
            if registro
            else {}
        )
        prefixo = f"serie_{serie}_"

        def valor(campo, padrao=""):
            if post is not None:
                return str(post.get(prefixo + campo, padrao)).strip()
            if not registro:
                return padrao
            return str(getattr(registro, campo, "") or "").strip()

        notas = []
        for componente in COMPONENTES_EDITOR:
            nome_campo = f"nota_{componente}"
            nota_valor = (
                str(post.get(prefixo + nome_campo, "")).strip()
                if post is not None
                else str(notas_db.get(componente, "") or "").strip()
            )
            notas.append(
                {
                    "codigo": componente,
                    "rotulo": ROTULOS_COMPONENTES[componente],
                    "valor": nota_valor,
                }
            )

        anos.append(
            {
                "serie": serie,
                "registro": registro,
                "ano": valor("ano"),
                "turma": valor("turma"),
                "professor_responsavel": valor("professor_responsavel"),
                "faltas": valor("faltas"),
                "frequencia": valor("frequencia"),
                "carga_horaria": valor("carga_horaria"),
                "resultado": valor("resultado"),
                "escola": valor("escola"),
                "municipio": valor("municipio", "MONTES CLAROS"),
                "uf": valor("uf", "MG"),
                "uf_opcoes": _opcoes_com_valor_atual(
                    UF_CHOICES,
                    valor("uf", "MG"),
                ),
                "resultado_opcoes": _opcoes_com_valor_atual(
                    RESULTADO_CHOICES,
                    valor("resultado"),
                ),
                "observacao": valor("observacao"),
                "notas": notas,
            }
        )

    return anos


def inicio(request):
    q = request.GET.get("q", "").strip()[:120]
    alunos = []
    if q:
        filtro = Q(nome__icontains=q)
        if q.isdigit():
            filtro |= Q(codigo=int(q))
        alunos = Aluno.objects.filter(filtro, ativo=True).order_by("nome")[:50]

    return render(
        request,
        "historico/inicio.html",
        {
            "q": q,
            "alunos": alunos,
            "total": Aluno.objects.count(),
            "registros": RegistroAcademico.objects.count(),
            "painel": painel_geral(),
        },
    )


def _diretorio_importacoes():
    diretorio = Path(settings.DATA_DIR) / "importacoes_alunos"
    diretorio.mkdir(parents=True, exist_ok=True)
    try:
        diretorio.chmod(0o700)
    except OSError:
        pass

    limite = time.time() - (24 * 60 * 60)
    for arquivo in diretorio.glob("*"):
        try:
            if arquivo.is_file() and arquivo.stat().st_mtime < limite:
                arquivo.unlink()
        except OSError:
            pass

    return diretorio


def _arquivo_importacao_da_sessao(request):
    token = request.session.get("importacao_alunos_token")
    extensao = request.session.get("importacao_alunos_extensao")
    if not token or extensao not in {".xls", ".xlsx"}:
        return None

    try:
        uuid.UUID(token)
    except (ValueError, TypeError):
        return None

    caminho = _diretorio_importacoes() / f"{token}{extensao}"
    return caminho if caminho.exists() else None


def _limpar_importacao_da_sessao(request):
    caminho = _arquivo_importacao_da_sessao(request)
    if caminho:
        try:
            caminho.unlink()
        except OSError:
            pass

    for chave in (
        "importacao_alunos_token",
        "importacao_alunos_extensao",
        "importacao_alunos_nome",
    ):
        request.session.pop(chave, None)


def _diretorio_importacoes_notas():
    diretorio = Path(settings.DATA_DIR) / "importacoes_notas_pdf"
    diretorio.mkdir(parents=True, exist_ok=True)
    try:
        diretorio.chmod(0o700)
    except OSError:
        pass

    limite = time.time() - (24 * 60 * 60)
    for arquivo in diretorio.glob("*.pdf"):
        try:
            if arquivo.is_file() and arquivo.stat().st_mtime < limite:
                arquivo.unlink()
        except OSError:
            pass

    return diretorio


def _arquivo_notas_da_sessao(request):
    token = request.session.get("importacao_notas_pdf_token")
    if not token:
        return None

    try:
        uuid.UUID(token)
    except (ValueError, TypeError):
        return None

    caminho = _diretorio_importacoes_notas() / f"{token}.pdf"
    return caminho if caminho.exists() else None


def _limpar_importacao_notas(request):
    caminho = _arquivo_notas_da_sessao(request)
    if caminho:
        try:
            caminho.unlink()
        except OSError:
            pass

    request.session.pop("importacao_notas_pdf_token", None)
    request.session.pop("importacao_notas_pdf_nome", None)


def importar_notas_pdf(request):
    formulario = ImportacaoNotasPdfForm()
    previa = None
    leitura = None
    erro = ""
    resultado = None

    if request.method == "POST":
        acao = request.POST.get("acao", "previsualizar")

        if acao == "cancelar":
            _limpar_importacao_notas(request)
            return redirect("historico:importar_notas_pdf")

        if acao == "aplicar":
            caminho = _arquivo_notas_da_sessao(request)
            if not caminho:
                erro = "A prévia expirou. Envie o PDF novamente."
            else:
                try:
                    leitura = extrair_notas_pdf(caminho)
                    resultado = aplicar_notas_pdf(leitura)
                    registrar_auditoria(
                        request,
                        "IMPORTACAO_NOTAS",
                        entidade="ImportacaoNotasPDF",
                        objeto_id=request.session.get("importacao_notas_pdf_token", ""),
                        detalhes={
                            "total": resultado.get("total", 0),
                            "processados": resultado.get("processados", 0),
                            "alunos_criados": resultado.get("alunos_criados", 0),
                            "notas_adicionadas": resultado.get("notas_adicionadas", 0),
                            "notas_preservadas": resultado.get("notas_preservadas", 0),
                            "conflitos": len(resultado.get("conflitos", [])),
                        },
                    )
                    _limpar_importacao_notas(request)
                except ErroImportacaoNotasPdf as exc:
                    erro = str(exc)
                except Exception:
                    erro = (
                        "Não foi possível aplicar as notas. "
                        "Nenhum aluno ou nota foi removido."
                    )
        else:
            formulario = ImportacaoNotasPdfForm(request.POST, request.FILES)
            if formulario.is_valid():
                arquivo = formulario.cleaned_data["arquivo"]
                token = str(uuid.uuid4())
                caminho = _diretorio_importacoes_notas() / f"{token}.pdf"

                _limpar_importacao_notas(request)

                with caminho.open("wb") as destino:
                    for bloco in arquivo.chunks():
                        destino.write(bloco)
                try:
                    caminho.chmod(0o600)
                except OSError:
                    pass

                try:
                    leitura = extrair_notas_pdf(caminho)
                    previa = analisar_notas_pdf(leitura)
                except ErroImportacaoNotasPdf as exc:
                    erro = str(exc)
                    try:
                        caminho.unlink()
                    except OSError:
                        pass
                except Exception:
                    erro = (
                        "Não foi possível ler este PDF. "
                        "Confirme se ele possui texto selecionável e dados de notas."
                    )
                    try:
                        caminho.unlink()
                    except OSError:
                        pass
                else:
                    request.session["importacao_notas_pdf_token"] = token
                    request.session["importacao_notas_pdf_nome"] = arquivo.name

    if previa is None and resultado is None and not erro:
        caminho = _arquivo_notas_da_sessao(request)
        if caminho:
            try:
                leitura = extrair_notas_pdf(caminho)
                previa = analisar_notas_pdf(leitura)
            except Exception:
                _limpar_importacao_notas(request)

    return render(
        request,
        "historico/importar_notas_pdf.html",
        {
            "formulario": formulario,
            "previa": previa,
            "leitura": leitura,
            "erro": erro,
            "resultado": resultado,
            "arquivo_nome": request.session.get(
                "importacao_notas_pdf_nome",
                "",
            ),
        },
    )


def importar_lista_alunos(request):
    formulario = ImportacaoAlunosForm()
    previa = None
    leitura = None
    erro = ""
    resultado = None

    if request.method == "POST":
        acao = request.POST.get("acao", "previsualizar")

        if acao == "cancelar":
            _limpar_importacao_da_sessao(request)
            return redirect("historico:importar_lista_alunos")

        if acao == "aplicar":
            caminho = _arquivo_importacao_da_sessao(request)
            if not caminho:
                erro = "A prévia expirou. Envie a lista novamente."
            else:
                try:
                    leitura = ler_lista_alunos(caminho)
                    resultado = aplicar_lista(leitura)
                    registrar_auditoria(
                        request,
                        "IMPORTACAO_ALUNOS",
                        entidade="ImportacaoAlunos",
                        objeto_id=request.session.get("importacao_alunos_token", ""),
                        detalhes={
                            "total": resultado.get("total", 0),
                            "criados": resultado.get("criados", 0),
                            "atualizados": resultado.get("atualizados", 0),
                            "conflitos": len(resultado.get("conflitos", [])),
                        },
                    )
                    _limpar_importacao_da_sessao(request)
                except ErroImportacao as exc:
                    erro = str(exc)
                except Exception:
                    erro = (
                        "Não foi possível aplicar a atualização. "
                        "Nenhum aluno foi removido."
                    )
        else:
            formulario = ImportacaoAlunosForm(request.POST, request.FILES)
            if formulario.is_valid():
                arquivo = formulario.cleaned_data["arquivo"]
                extensao = Path(arquivo.name).suffix.lower()
                token = str(uuid.uuid4())
                caminho = _diretorio_importacoes() / f"{token}{extensao}"

                _limpar_importacao_da_sessao(request)

                with caminho.open("wb") as destino:
                    for bloco in arquivo.chunks():
                        destino.write(bloco)
                try:
                    caminho.chmod(0o600)
                except OSError:
                    pass

                try:
                    leitura = ler_lista_alunos(caminho)
                    previa = analisar_lista(leitura)
                except ErroImportacao as exc:
                    erro = str(exc)
                    try:
                        caminho.unlink()
                    except OSError:
                        pass
                except Exception:
                    erro = (
                        "Não foi possível ler esta planilha. "
                        "Confirme se o arquivo é um XLS/XLSX válido."
                    )
                    try:
                        caminho.unlink()
                    except OSError:
                        pass
                else:
                    request.session["importacao_alunos_token"] = token
                    request.session["importacao_alunos_extensao"] = extensao
                    request.session["importacao_alunos_nome"] = arquivo.name

    if previa is None and resultado is None and not erro:
        caminho = _arquivo_importacao_da_sessao(request)
        if caminho:
            try:
                leitura = ler_lista_alunos(caminho)
                previa = analisar_lista(leitura)
            except Exception:
                _limpar_importacao_da_sessao(request)

    return render(
        request,
        "historico/importar_lista_alunos.html",
        {
            "formulario": formulario,
            "previa": previa,
            "leitura": leitura,
            "erro": erro,
            "resultado": resultado,
            "arquivo_nome": request.session.get("importacao_alunos_nome", ""),
        },
    )


def integridade_dados(request):
    return render(
        request,
        "historico/integridade_dados.html",
        {"relatorio": relatorio_integridade()},
    )


def dados_extras_anuais(request):
    FormSet = modelformset_factory(
        ConfiguracaoAno,
        form=ConfiguracaoAnoForm,
        extra=1,
        can_delete=False,
    )

    queryset = ConfiguracaoAno.objects.all().order_by("-ano")

    if request.method == "POST":
        formset = FormSet(request.POST, queryset=queryset, prefix="anos")
        if formset.is_valid():
            objetos = formset.save()
            registrar_auditoria(
                request,
                "REQUEST_SENSIVEL",
                entidade="ConfiguracaoAno",
                objeto_id="lote",
                objeto_repr="Configurações anuais",
                detalhes={
                    "quantidade_alterada": len(objetos),
                    "anos": sorted(
                        [obj.ano for obj in objetos if getattr(obj, "ano", None)]
                    ),
                },
            )
            return redirect(
                f'{reverse("historico:dados_extras_anuais")}?salvo=1'
            )
    else:
        formset = FormSet(queryset=queryset, prefix="anos")

    return render(
        request,
        "historico/dados_extras_anuais.html",
        {
            "formset": formset,
            "salvo": request.GET.get("salvo") == "1",
        },
    )


def relatorios(request):
    q = (request.GET.get("q") or "").strip()[:120]
    ano_texto = (request.GET.get("ano") or "").strip()
    serie_texto = (request.GET.get("serie") or "").strip()
    turma = (request.GET.get("turma") or "").strip()[:120]
    status = (request.GET.get("status") or "").strip().lower()
    pesquisa_realizada = any(
        [q, ano_texto, serie_texto, turma, status]
    )

    alunos = []
    total_resultados = 0

    if pesquisa_realizada:
        alunos_qs = Aluno.objects.all()
        if q:
            filtro = Q(nome__icontains=q) | Q(matricula__icontains=q)
            if q.isdigit():
                filtro |= Q(codigo=int(q))
            alunos_qs = alunos_qs.filter(filtro)

        filtros_relacao = {}
        if ano_texto.isdigit():
            filtros_relacao["registros_academicos__ano"] = int(ano_texto)
        if serie_texto.isdigit() and 1 <= int(serie_texto) <= 5:
            filtros_relacao["registros_academicos__serie"] = int(serie_texto)
        if turma:
            filtros_relacao["registros_academicos__turma__icontains"] = turma
        if status == "ativa":
            filtros_relacao["registros_academicos__ativo_no_historico"] = True
        elif status == "inativa":
            filtros_relacao["registros_academicos__ativo_no_historico"] = False

        if filtros_relacao:
            alunos_qs = alunos_qs.filter(**filtros_relacao)

        alunos_qs = (
            alunos_qs
            .annotate(
                total_relacoes=Count(
                    "registros_academicos",
                    distinct=True,
                ),
                relacoes_ativas=Count(
                    "registros_academicos",
                    filter=Q(
                        registros_academicos__ativo_no_historico=True
                    ),
                    distinct=True,
                ),
            )
            .distinct()
            .order_by("nome")
        )

        total_resultados = alunos_qs.count()
        alunos = list(alunos_qs[:100])

    anos_disponiveis = list(
        RegistroAcademico.objects
        .values_list("ano", flat=True)
        .distinct()
        .order_by("-ano")
    )

    return render(
        request,
        "historico/relatorios.html",
        {
            "alunos": alunos,
            "total_resultados": total_resultados,
            "pesquisa_realizada": pesquisa_realizada,
            "q": q,
            "ano": ano_texto,
            "serie": serie_texto,
            "turma": turma,
            "status": status,
            "anos_disponiveis": anos_disponiveis,
        },
    )


def relatorio_aluno(request, codigo):
    aluno = get_object_or_404(Aluno, codigo=codigo)
    dados = relatorio_completo_aluno(aluno)

    registrar_auditoria(
        request,
        "REQUEST_SENSIVEL",
        entidade="Aluno",
        objeto_id=aluno.codigo,
        objeto_repr=aluno.nome,
        detalhes={
            "operacao": "relatorio_completo_visualizado",
            "relacoes": dados["total_relacoes"],
        },
    )

    return render(
        request,
        "historico/relatorio_aluno.html",
        {
            "aluno": aluno,
            "relatorio": dados,
        },
    )


def aluno_detalhe(request, codigo):
    aluno = get_object_or_404(Aluno, codigo=codigo)
    return render(
        request,
        "historico/aluno.html",
        {
            "aluno": aluno,
            "historico": historico_do_aluno(aluno),
            "indicadores": indicadores_aluno(aluno),
        },
    )


@require_POST
def alternar_relacao_academica(request, codigo, registro_id):
    aluno = get_object_or_404(Aluno, codigo=codigo)

    with transaction.atomic():
        registro = get_object_or_404(
            RegistroAcademico.objects.select_for_update(),
            pk=registro_id,
            aluno=aluno,
        )
        acao = (request.POST.get("acao") or "").strip().lower()

        desativadas = []
        if acao == "ativar":
            if registro.serie is not None:
                concorrentes = (
                    aluno.registros_academicos
                    .select_for_update()
                    .filter(
                        serie=registro.serie,
                        ativo_no_historico=True,
                    )
                    .exclude(pk=registro.pk)
                )
                desativadas = list(
                    concorrentes.values_list("id", flat=True)
                )
                concorrentes.update(ativo_no_historico=False)

            registro.ativo_no_historico = True
            registro.save(update_fields=["ativo_no_historico"])
            status = "ativada"
        elif acao == "desativar":
            registro.ativo_no_historico = False
            registro.save(update_fields=["ativo_no_historico"])
            status = "desativada"
        else:
            return JsonResponse(
                {"ok": False, "erro": "Ação inválida."},
                status=400,
            )

    registrar_auditoria(
        request,
        "REQUEST_SENSIVEL",
        entidade="RegistroAcademico",
        objeto_id=registro.id,
        objeto_repr=str(registro),
        detalhes={
            "operacao": f"relacao_{status}",
            "aluno_codigo": aluno.codigo,
            "ano": registro.ano,
            "serie": registro.serie,
            "turma": registro.turma,
            "relacoes_desativadas_automaticamente": desativadas,
            "notas_preservadas": registro.notas.count(),
        },
    )

    destino = reverse("historico:aluno", args=[aluno.codigo])
    return redirect(f"{destino}?relacao={status}")


def historico_impressao(request, codigo):
    aluno = get_object_or_404(Aluno, codigo=codigo)
    documento = None
    documento_id = request.GET.get("documento", "").strip()

    if documento_id:
        documento = get_object_or_404(
            DocumentoHistorico,
            pk=documento_id,
            aluno=aluno,
        )
        contexto = contexto_snapshot(documento)
        contexto.update(
            {
                "documento": documento,
                "validacao_documento": validar_documento(documento),
                "qr_code_data_uri": qr_code_data_uri(request, documento),
                "can_edit": False,
            }
        )
        registrar_auditoria(
            request,
            "HISTORICO_VISUALIZADO",
            entidade="DocumentoHistorico",
            objeto_id=documento.id,
            objeto_repr=aluno.nome,
            detalhes={"modo": "documento_emitido"},
        )
    else:
        oficial = historico_oficial_do_aluno(aluno)
        contexto = {
            "aluno": aluno,
            "historico": oficial["anos"],
            "tem_2020": oficial["tem_2020"],
            "nascimento": oficial["nascimento"],
            "data_conclusao": oficial["data_conclusao"],
            "ultima_serie": oficial["ultima_serie"],
            "serie_conclusao": oficial["serie_conclusao"],
            "data_expedicao": oficial["data_expedicao"],
            "observacao_historico": oficial["observacao_historico"],
            "documento": None,
            "validacao_documento": None,
            "qr_code_data_uri": "",
            "can_edit": True,
        }

    return render(
        request,
        "historico/historico.html",
        contexto,
    )


@require_POST
def emitir_historico(request, codigo):
    aluno = get_object_or_404(Aluno, codigo=codigo)
    usuario = (
        request.user
        if getattr(request.user, "is_authenticated", False)
        else None
    )
    documento = emitir_documento(
        aluno,
        usuario,
        request=request,
    )
    destino = reverse("historico:historico", args=[aluno.codigo])
    return redirect(f"{destino}?documento={documento.id}")


def validar_documento_publico(request, documento_id):
    documento = get_object_or_404(
        DocumentoHistorico.objects.select_related("aluno"),
        pk=documento_id,
    )
    validacao = validar_documento(documento)
    snapshot_aluno = documento.snapshot.get("aluno", {})
    oficial = documento.snapshot.get("oficial", {})

    return render(
        request,
        "historico/validar_documento.html",
        {
            "documento": documento,
            "validacao": validacao,
            "nome_mascarado": mascarar_nome(snapshot_aluno.get("nome", "")),
            "codigo_mascarado": mascarar_codigo(snapshot_aluno.get("codigo", "")),
            "ultima_serie": oficial.get("ultima_serie", ""),
            "data_conclusao": oficial.get("data_conclusao", ""),
        },
    )


def gerenciar_aluno(request, codigo=None):
    aluno = None
    if codigo is not None:
        aluno = get_object_or_404(Aluno, codigo=codigo)

    if request.method == "POST":
        form = AlunoCadastroForm(request.POST, instance=aluno)
        anos = _anos_editor(aluno, request.POST)
        erros_anos = []

        anos_validos = {}
        for item in anos:
            texto_ano = item["ano"]
            if not texto_ano:
                continue
            try:
                ano = int(texto_ano)
            except ValueError:
                erros_anos.append(
                    f'{item["serie"]}º ano: informe um ano letivo válido.'
                )
                continue
            if ano < 1000 or ano > 9999:
                erros_anos.append(
                    f'{item["serie"]}º ano: informe o ano com 4 dígitos.'
                )
                continue
            anos_validos[item["serie"]] = ano

        if form.is_valid() and not erros_anos:
            with transaction.atomic():
                aluno_salvo = form.save()
                registros = _registros_por_serie(aluno_salvo)

                for item in anos:
                    serie = item["serie"]
                    if serie not in anos_validos:
                        continue

                    registro = registros.get(serie)
                    novo_ano = anos_validos[serie]
                    config_ano = (
                        ConfiguracaoAno.objects
                        .select_related("matriz_curricular")
                        .filter(ano=novo_ano)
                        .first()
                    )
                    matriz = (
                        config_ano.matriz_curricular
                        if config_ano and config_ano.matriz_curricular_id
                        else matriz_para_ano(novo_ano)
                    )

                    if registro is None:
                        registro = RegistroAcademico(
                            aluno=aluno_salvo,
                            nome_original=aluno_salvo.nome,
                            serie=serie,
                            ano=novo_ano,
                            matriz_curricular=matriz,
                        )
                    else:
                        if registro.ano != novo_ano:
                            # Ao alterar manualmente o ano, a referência de linha
                            # da importação deixa de representar a origem exata.
                            registro.linha_origem = None
                        registro.ano = novo_ano
                        if not registro.matriz_curricular_id and matriz:
                            registro.matriz_curricular = matriz

                    for campo in (
                        "turma",
                        "professor_responsavel",
                        "faltas",
                        "frequencia",
                        "carga_horaria",
                        "resultado",
                        "escola",
                        "municipio",
                        "uf",
                        "observacao",
                    ):
                        setattr(
                            registro,
                            campo,
                            _texto_limitado(
                                RegistroAcademico,
                                campo,
                                item[campo],
                            ),
                        )

                    registro.nome_original = aluno_salvo.nome
                    registro.save()

                    for nota_item in item["notas"]:
                        Nota.objects.update_or_create(
                            registro=registro,
                            componente=nota_item["codigo"],
                            defaults={
                                "valor": _texto_limitado(
                                    Nota,
                                    "valor",
                                    nota_item["valor"],
                                )
                            },
                        )

            registrar_auditoria(
                request,
                "ALUNO_CRIADO" if aluno is None else "ALUNO_ALTERADO",
                entidade="Aluno",
                objeto_id=aluno_salvo.codigo,
                objeto_repr=aluno_salvo.nome,
                detalhes={"series_editadas": sorted(anos_validos)},
            )

            parametro = "criado=1" if aluno is None else "salvo=1"
            return redirect(
                f'{reverse("historico:aluno_editar", args=[aluno_salvo.codigo])}?{parametro}'
            )
    else:
        if aluno is None:
            ultimo_codigo = (
                Aluno.objects.order_by("-codigo")
                .values_list("codigo", flat=True)
                .first()
                or 0
            )
            form = AlunoCadastroForm(
                initial={
                    "codigo": ultimo_codigo + 1,
                    "curso": "ENSINO FUNDAMENTAL",
                    "ativo": True,
                }
            )
        else:
            form = AlunoCadastroForm(instance=aluno)
        anos = _anos_editor(aluno)
        erros_anos = []

    return render(
        request,
        "historico/aluno_form.html",
        {
            "aluno": aluno,
            "form": form,
            "anos": anos,
            "erros_anos": erros_anos,
            "salvo": request.GET.get("salvo") == "1",
            "criado": request.GET.get("criado") == "1",
        },
    )


def _texto_limitado(model, campo, valor):
    field = model._meta.get_field(campo)
    texto = "" if valor is None else str(valor).strip()
    if field.max_length:
        texto = texto[: field.max_length]
    return texto


@require_POST
def salvar_historico(request, codigo):
    aluno = get_object_or_404(Aluno, codigo=codigo)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "erro": "JSON inválido."}, status=400)

    campos_aluno = {
        "nome",
        "matricula",
        "cpf",
        "curso",
        "identidade",
        "orgao_expedidor",
        "data_conclusao",
        "serie_conclusao",
        "data_expedicao",
        "observacao_historico",
        "uf",
        "pai",
        "mae",
        "nascimento",
        "naturalidade",
        "nacionalidade",
        "sexo",
    }
    campos_registro = {
        "ano",
        "faltas",
        "frequencia",
        "carga_horaria",
        "professor_responsavel",
        "resultado",
        "escola",
        "municipio",
        "uf",
        "observacao",
    }
    componentes_validos = {codigo for codigo, _ in Nota.COMPONENTES}

    novos_criados = 0

    with transaction.atomic():
        dados_aluno = payload.get("aluno") or {}
        alterados = []
        for campo in campos_aluno:
            if campo not in dados_aluno:
                continue
            setattr(
                aluno,
                campo,
                _texto_limitado(Aluno, campo, dados_aluno[campo]),
            )
            alterados.append(campo)

        if alterados:
            aluno.save(update_fields=alterados)

        for item in payload.get("registros") or []:
            try:
                registro_id = int(item.get("id"))
            except (TypeError, ValueError):
                continue

            registro = (
                aluno.registros_academicos
                .select_for_update()
                .filter(pk=registro_id)
                .first()
            )
            if not registro:
                return JsonResponse(
                    {"ok": False, "erro": "Registro não pertence ao aluno."},
                    status=400,
                )

            dados_registro = item.get("campos") or {}
            campos_alterados = []
            for campo in campos_registro:
                if campo not in dados_registro:
                    continue

                if campo == "ano":
                    try:
                        valor_ano = int(str(dados_registro[campo]).strip())
                    except (TypeError, ValueError):
                        return JsonResponse(
                            {"ok": False, "erro": "Ano letivo inválido."},
                            status=400,
                        )
                    if valor_ano < 1000 or valor_ano > 9999:
                        return JsonResponse(
                            {"ok": False, "erro": "Informe o ano com 4 dígitos."},
                            status=400,
                        )
                    registro.ano = valor_ano
                else:
                    setattr(
                        registro,
                        campo,
                        _texto_limitado(
                            RegistroAcademico,
                            campo,
                            dados_registro[campo],
                        ),
                    )
                campos_alterados.append(campo)

            if campos_alterados:
                registro.save(update_fields=campos_alterados)

            notas = item.get("notas") or {}
            for componente, dados_nota in notas.items():
                if componente not in componentes_validos:
                    continue

                if isinstance(dados_nota, dict):
                    valor = dados_nota.get("valor", "")
                    carga_horaria = dados_nota.get("carga_horaria", "")
                else:
                    valor = dados_nota
                    carga_horaria = ""

                Nota.objects.update_or_create(
                    registro=registro,
                    componente=componente,
                    defaults={
                        "valor": _texto_limitado(Nota, "valor", valor),
                        "carga_horaria": _texto_limitado(
                            Nota,
                            "carga_horaria",
                            carga_horaria,
                        ),
                    },
                )

        for item in payload.get("novos_registros") or []:
            try:
                serie = int(item.get("serie"))
                ano = int(str(item.get("ano", "")).strip())
            except (TypeError, ValueError):
                continue

            if serie < 1 or serie > 5 or ano < 1000 or ano > 9999:
                continue

            ja_existe = (
                aluno.registros_academicos
                .select_for_update()
                .filter(
                    serie=serie,
                    ativo_no_historico=True,
                )
                .exists()
            )
            if ja_existe:
                continue

            RegistroAcademico.objects.create(
                aluno=aluno,
                nome_original=aluno.nome,
                ano=ano,
                serie=serie,
                professor_responsavel=_texto_limitado(
                    RegistroAcademico,
                    "professor_responsavel",
                    item.get("professor_responsavel", ""),
                ),
                ativo_no_historico=True,
            )
            novos_criados += 1

    registrar_auditoria(
        request,
        "NOTAS_ALTERADAS",
        entidade="Aluno",
        objeto_id=aluno.codigo,
        objeto_repr=aluno.nome,
        detalhes={
            "registros_recebidos": len(payload.get("registros") or []),
            "novos_registros": novos_criados,
        },
    )

    return JsonResponse({"ok": True, "recarregar": novos_criados > 0})
