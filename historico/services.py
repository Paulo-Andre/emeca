from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from .models import ConfiguracaoAno, Nota


ORDEM_COMPONENTES = [
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

MESES_PT = {
    1: "JANEIRO",
    2: "FEVEREIRO",
    3: "MARÇO",
    4: "ABRIL",
    5: "MAIO",
    6: "JUNHO",
    7: "JULHO",
    8: "AGOSTO",
    9: "SETEMBRO",
    10: "OUTUBRO",
    11: "NOVEMBRO",
    12: "DEZEMBRO",
}


def _numero(valor):
    if valor in (None, "", "-", "*"):
        return None
    texto = str(valor).replace("%", "").replace(",", ".").strip()
    try:
        return Decimal(texto)
    except (InvalidOperation, ValueError):
        return None


def _texto_numero(valor):
    if valor in (None, ""):
        return ""
    numero = _numero(valor)
    if numero is None:
        return str(valor).strip()
    if numero == numero.to_integral():
        return str(int(numero))
    return format(numero.normalize(), "f").replace(".", ",")


def _carga_horaria_display(valor):
    if valor in (None, "", "*"):
        return "*" if valor == "*" else ""
    texto = str(valor).strip()
    if ":" in texto:
        return texto
    numero = _numero(texto)
    if numero is None:
        return texto
    horas = int(numero)
    minutos = int(round((numero - Decimal(horas)) * 60))
    if minutos == 60:
        horas += 1
        minutos = 0
    return f"{horas}:{minutos:02d}"


def _percentual_display(valor):
    if valor in (None, "", "*"):
        return "*" if valor == "*" else ""
    numero = _numero(valor)
    if numero is None:
        return str(valor).strip()
    if numero <= 1:
        numero *= 100
    if numero == numero.to_integral():
        return f"{int(numero)}%"
    return f"{str(numero.normalize()).replace('.', ',')}%"


def media_minima_percentual(config):
    if not config or not config.media_minima:
        return None
    numero = _numero(config.media_minima)
    if numero is None:
        return None
    return numero * 100 if numero <= 1 else numero


def situacao_apta(resultado):
    resultado_normalizado = (resultado or "").strip().upper()
    return resultado_normalizado in {
        "APROVADO",
        "EM CONTINUIDADE",
        "EM CURSO",
        "APTO",
        "APTA",
    }


def faltas_em_horas(registro):
    if registro.ano == 2020:
        return "*"
    numero = _numero(registro.faltas)
    if numero is None:
        return str(registro.faltas or "")
    return f"{int(numero * 4)}:00"


def avaliar_media(registro, config):
    media = media_minima_percentual(config)
    if media is None:
        return ""

    valores = []
    for nota in registro.notas.all():
        numero = _numero(nota.valor)
        if numero is not None:
            valores.append(numero)

    if not valores:
        return ""

    # Escalas históricas qualitativas não são comparadas como nota numérica.
    if max(valores) <= 5:
        return ""

    return (
        "ALUNO DENTRO DA MÉDIA"
        if all(valor >= media for valor in valores)
        else "ALUNO ABAIXO DA MÉDIA"
    )


def _data_partes(valor):
    texto = str(valor or "").strip()
    if not texto:
        return {"dia": "", "mes": "", "ano": "", "texto": ""}

    formatos = (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%y",
    )
    for formato in formatos:
        try:
            data = datetime.strptime(texto, formato)
            return {
                "dia": f"{data.day:02d}",
                "mes": MESES_PT[data.month],
                "ano": str(data.year),
                "texto": f"{data.day:02d}/{data.month:02d}/{data.year}",
            }
        except ValueError:
            pass

    return {"dia": "", "mes": texto.upper(), "ano": "", "texto": texto}


def historico_do_aluno(aluno):
    registros = (
        aluno.registros_academicos
        .prefetch_related("notas")
        .order_by("ano", "serie", "id")
    )

    saida = []
    for registro in registros:
        config = ConfiguracaoAno.objects.filter(ano=registro.ano).first()
        notas_qs = list(registro.notas.all())
        notas = {nota.componente: nota.valor for nota in notas_qs}
        cargas_componentes = {
            nota.componente: nota.carga_horaria for nota in notas_qs
        }
        media_minima = media_minima_percentual(config)

        saida.append(
            {
                "registro": registro,
                "config": config,
                "notas": notas,
                "cargas_componentes": cargas_componentes,
                "notas_ordenadas": [
                    (componente, notas.get(componente, ""))
                    for componente in ORDEM_COMPONENTES
                ],
                "apto": situacao_apta(registro.resultado),
                "faltas_horas": faltas_em_horas(registro),
                "frequencia": registro.frequencia,
                "carga_horaria": (
                    registro.carga_horaria
                    or (config.ch_anual if config else "")
                ),
                "media_minima_num": (
                    str(media_minima) if media_minima is not None else ""
                ),
                "avaliacao_media": avaliar_media(registro, config),
            }
        )

    return saida


def historico_oficial_do_aluno(aluno):
    registros = list(
        aluno.registros_academicos
        .prefetch_related("notas")
        .filter(
            serie__gte=1,
            serie__lte=5,
            ativo_no_historico=True,
        )
        .order_by("serie", "ano", "id")
    )

    por_serie = {}
    for registro in registros:
        # Por regra de negócio existe no máximo uma relação ativa por série.
        # O fallback mantém comportamento seguro caso exista dado legado.
        por_serie[registro.serie] = registro

    anos = []
    for serie in range(1, 6):
        registro = por_serie.get(serie)

        if not registro:
            anos.append(
                {
                    "serie": serie,
                    "vazio": True,
                    "registro": None,
                    "ano": "",
                    "notas": {componente: "" for componente in ORDEM_COMPONENTES},
                    "carga_horaria": "",
                    "faltas_horas": "",
                    "escola": "",
                    "municipio": "",
                    "uf": "",
                    "dias_letivos": "",
                    "media_minima": "",
                    "media_minima_num": "",
                    "situacao": "",
                    "apto": False,
                }
            )
            continue

        config = ConfiguracaoAno.objects.filter(ano=registro.ano).first()
        notas_db = {nota.componente: nota.valor for nota in registro.notas.all()}
        media_minima = media_minima_percentual(config)
        carga = registro.carga_horaria or (config.ch_anual if config else "")

        anos.append(
            {
                "serie": serie,
                "vazio": False,
                "registro": registro,
                "ano": registro.ano,
                "notas": {
                    componente: _texto_numero(notas_db.get(componente, ""))
                    for componente in ORDEM_COMPONENTES
                },
                "carga_horaria": _carga_horaria_display(carga),
                "faltas_horas": faltas_em_horas(registro),
                "escola": registro.escola
                or (config.escola if config else ""),
                "municipio": registro.municipio
                or (config.municipio if config else "MONTES CLAROS"),
                "uf": registro.uf or (config.uf if config else "MG"),
                "dias_letivos": (
                    _texto_numero(config.dias_letivos) if config else ""
                ),
                "media_minima": (
                    _percentual_display(config.media_minima) if config else ""
                ),
                "media_minima_num": (
                    str(media_minima) if media_minima is not None else ""
                ),
                "situacao": (
                    "APTO" if situacao_apta(registro.resultado)
                    else (registro.resultado or "")
                ),
                "apto": situacao_apta(registro.resultado),
            }
        )

    nascimento = _data_partes(aluno.nascimento)

    data_expedicao = aluno.data_expedicao.strip()
    if not data_expedicao:
        hoje = timezone.localdate()
        data_expedicao = f"{hoje.day:02d}/{hoje.month:02d}/{hoje.year}"

    ultimo_registro = max(
        registros,
        key=lambda registro: (registro.ano, registro.id),
        default=None,
    )

    ultima_serie = ultimo_registro.serie if ultimo_registro else ""

    # O valor preenchido diretamente no aluno é uma substituição manual
    # para o certificado. Só usamos a configuração anual como fallback.
    data_conclusao = aluno.data_conclusao.strip()
    if not data_conclusao and ultimo_registro:
        config_ultimo_ano = ConfiguracaoAno.objects.filter(
            ano=ultimo_registro.ano
        ).first()
        if config_ultimo_ano and config_ultimo_ano.data_conclusao.strip():
            data_conclusao = config_ultimo_ano.data_conclusao.strip()

    serie_conclusao = aluno.serie_conclusao.strip()
    if not serie_conclusao and ultima_serie:
        serie_conclusao = f"{ultima_serie}º"

    return {
        "anos": anos,
        "tem_2020": any(
            item["registro"] is not None and item["registro"].ano == 2020
            for item in anos
        ),
        "nascimento": nascimento,
        "data_expedicao": data_expedicao,
        "data_conclusao": data_conclusao,
        "ultima_serie": ultima_serie,
        "serie_conclusao": serie_conclusao,
        "observacao_historico": aluno.observacao_historico,
    }
