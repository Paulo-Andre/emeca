"""Atualiza dados de identificação dos boletins ligados a Declarações.

Os lançamentos de notas, Matrículas e Histórico não são modificados.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from usuarioSec.models import declaracao
from .models import AlunoBoletim


@receiver(post_save, sender=declaracao, dispatch_uid="emeca_boletim_declaracao_sync")
def atualizar_identificacao_boletim_declaracao(sender, instance, **kwargs):
    # Update direto evita cascatas de save() e preserva nome/notas históricas.
    AlunoBoletim.objects.filter(declaracao_id=instance.pk).update(
        data_nascimento=instance.dataNascimentoAluno,
        cpf_mae=instance.cpfMae or "",
        cpf_responsavel=instance.cpfResponsavel or "",
    )
