import base64
import hashlib
import hmac
import io
import json

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.urls import reverse

from .auditoria import registrar_auditoria
from .models import DocumentoHistorico
from .services import historico_oficial_do_aluno


ALUNO_SNAPSHOT_FIELDS = (
    "codigo",
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
)


def _registro_snapshot(registro):
    if registro is None:
        return None
    return {
        "id": registro.id,
        "ano": registro.ano,
        "serie": registro.serie,
        "turma": registro.turma,
        "faltas": registro.faltas,
        "frequencia": registro.frequencia,
        "carga_horaria": registro.carga_horaria,
        "resultado": registro.resultado,
        "escola": registro.escola,
        "municipio": registro.municipio,
        "uf": registro.uf,
        "observacao": registro.observacao,
        "matriz_curricular_id": registro.matriz_curricular_id,
    }


def criar_snapshot_historico(aluno):
    oficial = historico_oficial_do_aluno(aluno)
    anos = []
    for item in oficial["anos"]:
        anos.append(
            {
                **{
                    chave: valor
                    for chave, valor in item.items()
                    if chave != "registro"
                },
                "registro": _registro_snapshot(item.get("registro")),
            }
        )

    return {
        "schema_version": 1,
        "aluno": {
            campo: getattr(aluno, campo, "")
            for campo in ALUNO_SNAPSHOT_FIELDS
        },
        "oficial": {
            "anos": anos,
            "tem_2020": oficial["tem_2020"],
            "nascimento": oficial["nascimento"],
            "data_expedicao": oficial["data_expedicao"],
            "data_conclusao": oficial["data_conclusao"],
            "ultima_serie": oficial["ultima_serie"],
            "serie_conclusao": oficial["serie_conclusao"],
            "observacao_historico": oficial["observacao_historico"],
        },
    }


def snapshot_canonico(snapshot):
    return json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def hash_snapshot(snapshot):
    return hashlib.sha256(snapshot_canonico(snapshot)).hexdigest()


def assinatura_snapshot(hash_sha256):
    return hmac.new(
        settings.DOCUMENT_SIGNING_KEY.encode("utf-8"),
        hash_sha256.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def emitir_documento(aluno, usuario, request=None):
    snapshot = criar_snapshot_historico(aluno)
    hash_sha256 = hash_snapshot(snapshot)
    assinatura = assinatura_snapshot(hash_sha256)

    documento = DocumentoHistorico.objects.create(
        aluno=aluno,
        emitido_por=usuario,
        hash_sha256=hash_sha256,
        assinatura_hmac=assinatura,
        snapshot=snapshot,
    )

    if request is not None:
        registrar_auditoria(
            request,
            "HISTORICO_EMITIDO",
            entidade="DocumentoHistorico",
            objeto_id=documento.id,
            objeto_repr=aluno.nome,
            detalhes={
                "aluno_codigo": aluno.codigo,
                "hash_prefixo": hash_sha256[:16],
            },
        )

    return documento


def validar_documento(documento):
    hash_atual = hash_snapshot(documento.snapshot)
    assinatura_atual = assinatura_snapshot(hash_atual)

    integridade = hmac.compare_digest(
        hash_atual,
        documento.hash_sha256,
    ) and hmac.compare_digest(
        assinatura_atual,
        documento.assinatura_hmac,
    )

    return {
        "integro": integridade,
        "valido": bool(integridade and not documento.revogado),
        "revogado": documento.revogado,
        "hash_calculado": hash_atual,
    }


def url_validacao(request, documento):
    caminho = reverse(
        "historico:validar_documento",
        args=[documento.id],
    )
    return request.build_absolute_uri(caminho)


def qr_code_data_uri(request, documento):
    conteudo = url_validacao(request, documento)
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=5,
        border=2,
    )
    qr.add_data(conteudo)
    qr.make(fit=True)
    imagem = qr.make_image(
        image_factory=qrcode.image.svg.SvgPathImage,
    )
    buffer = io.BytesIO()
    imagem.save(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def contexto_snapshot(documento):
    snapshot = documento.snapshot
    oficial = snapshot["oficial"]
    ultima_serie = oficial.get("ultima_serie", "")
    serie_conclusao = oficial.get("serie_conclusao", "")
    if not serie_conclusao and ultima_serie:
        serie_conclusao = f"{ultima_serie}º"

    return {
        "aluno": snapshot["aluno"],
        "historico": oficial["anos"],
        "tem_2020": oficial["tem_2020"],
        "nascimento": oficial["nascimento"],
        "data_conclusao": oficial["data_conclusao"],
        "ultima_serie": ultima_serie,
        "serie_conclusao": serie_conclusao,
        "data_expedicao": oficial["data_expedicao"],
        "observacao_historico": oficial["observacao_historico"],
    }


def mascarar_nome(nome):
    partes = [p for p in str(nome or "").split() if p]
    if not partes:
        return ""
    mascaradas = []
    for parte in partes:
        if len(parte) <= 2:
            mascaradas.append(parte[0] + "*" * max(0, len(parte) - 1))
        else:
            mascaradas.append(parte[0] + "*" * (len(parte) - 2) + parte[-1])
    return " ".join(mascaradas)


def mascarar_codigo(codigo):
    texto = str(codigo or "")
    if len(texto) <= 2:
        return "*" * len(texto)
    return "*" * (len(texto) - 2) + texto[-2:]
