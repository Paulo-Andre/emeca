"""Edição integral dos dados utilizados nas Declarações escolares.

Não modifica documentos de impressão, matrículas ou dados de outros módulos.
"""
import re

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .access_control import usuario_tem_modulo
from .importacao_declaracoes import deduplicar_telefones, normalizar_cpf
from .models import TelefoneDeclaracao, declaracao


class EdicaoDadosDeclaracaoForm(forms.ModelForm):
    """Todos os campos existentes no cadastro de Declarações."""

    class Meta:
        model = declaracao
        fields = (
            "nomeDoAluno", "dataNascimentoAluno", "nacionaliadeAluno",
            "natularidadeAluno", "ufAluno", "sexoDoAluno", "turmaDoAluno",
            "cartaoSusDoAluno", "cpfDoAluno", "nomePai", "cpfPai",
            "nomeMae", "cpfMae", "nomeResponsavel", "cpfResponsavel",
        )
        labels = {
            "nomeDoAluno": "Nome completo do aluno",
            "dataNascimentoAluno": "Data de nascimento",
            "nacionaliadeAluno": "Nacionalidade",
            "natularidadeAluno": "Naturalidade",
            "ufAluno": "UF de nascimento",
            "sexoDoAluno": "Sexo",
            "turmaDoAluno": "Turma / Série",
            "cartaoSusDoAluno": "Cartão SUS",
            "cpfDoAluno": "CPF do aluno",
            "nomePai": "Nome do pai",
            "cpfPai": "CPF do pai",
            "nomeMae": "Nome da mãe",
            "cpfMae": "CPF da mãe",
            "nomeResponsavel": "Nome do responsável",
            "cpfResponsavel": "CPF do responsável",
        }
        widgets = {
            "dataNascimentoAluno": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo, item in self.fields.items():
            item.widget.attrs.setdefault("class", "declaracao-input")
            if campo.startswith("cpf"):
                item.widget.attrs.update({
                    "inputmode": "numeric",
                    "maxlength": "14",
                    "placeholder": "000.000.000-00",
                })
            if campo == "ufAluno":
                item.widget.attrs.update({"maxlength": "2", "placeholder": "MG"})
            if campo == "nomeDoAluno":
                item.widget.attrs["autocomplete"] = "name"

    def clean(self):
        cleaned = super().clean()
        for campo in ("cpfDoAluno", "cpfPai", "cpfMae", "cpfResponsavel"):
            valor = cleaned.get(campo)
            if valor is None:
                continue
            valor = str(valor).strip()
            if not valor:
                cleaned[campo] = ""
                continue
            digitos = re.sub(r"\D", "", valor)
            if len(digitos) == 11:
                cleaned[campo] = normalizar_cpf(valor)
            elif valor != str(getattr(self.instance, campo, "") or "").strip():
                # Dados antigos incompletos continuam visíveis até sua correção.
                self.add_error(campo, "Informe um CPF com 11 dígitos ou deixe em branco.")
        return cleaned


TIPOS_TELEFONE = (
    ("PAI", "Telefones do pai", "telefonePai"),
    ("MAE", "Telefones da mãe", "telefoneMae"),
    ("RESPONSAVEL", "Telefones do responsável", "telefoneResponsavel"),
)


def _grupos_telefone(aluno, post=None):
    agrupados = {"PAI": [], "MAE": [], "RESPONSAVEL": []}
    if post is None:
        for telefone in aluno.telefones.all():
            if telefone.tipo in agrupados:
                agrupados[telefone.tipo].append(telefone.telefone)
    grupos = []
    for tipo, titulo, campo in TIPOS_TELEFONE:
        numeros = post.getlist(campo) if post is not None else agrupados[tipo]
        numeros = list(numeros)
        numeros.extend([""] * max(0, 3 - len(numeros)))
        grupos.append({
            "tipo": tipo, "titulo": titulo, "campo": campo, "numeros": numeros,
        })
    return grupos


@login_required
@require_http_methods(["GET", "POST"])
def editar_aluno_declaracao(request, id):
    if not usuario_tem_modulo(
        request.user,
        "secretaria",
        strict=getattr(settings, "EMECA_RBAC_STRICT", True),
    ):
        return HttpResponseForbidden("Sem permissão para editar dados de declarações.")

    aluno = get_object_or_404(
        declaracao.objects.prefetch_related("telefones"), pk=id,
    )
    form = EdicaoDadosDeclaracaoForm(
        request.POST if request.method == "POST" else None,
        instance=aluno,
    )

    if request.method == "POST" and form.is_valid():
        # Dados principais e telefones são atualizados na mesma transação.
        with transaction.atomic():
            form.save()
            for tipo, _, campo in TIPOS_TELEFONE:
                numeros, _ = deduplicar_telefones(request.POST.getlist(campo))
                existentes = list(
                    TelefoneDeclaracao.objects.select_for_update().filter(
                        declaracao=aluno, tipo=tipo,
                    )
                )
                atuais = {obj.telefone: obj for obj in existentes}
                novos = set(numeros)
                ids_remover = [
                    obj.pk for obj in existentes if obj.telefone not in novos
                ]
                if ids_remover:
                    TelefoneDeclaracao.objects.filter(
                        declaracao=aluno, pk__in=ids_remover,
                    ).delete()
                TelefoneDeclaracao.objects.bulk_create(
                    [
                        TelefoneDeclaracao(
                            declaracao=aluno, tipo=tipo, telefone=numero,
                        )
                        for numero in numeros if numero not in atuais
                    ],
                    ignore_conflicts=True,
                )
        messages.success(request, "Dados completos do aluno atualizados com sucesso.")
        return redirect("editar_aluno_declaracao", id=aluno.pk)

    return render(request, "declaracoes/editar_aluno_declaracao.html", {
        "aluno": aluno,
        "form": form,
        "grupos_telefone": _grupos_telefone(
            aluno, request.POST if request.method == "POST" else None,
        ),
    })
