from django.db import models

# Create your models here.

class declaracao(models.Model):

    # ================= ALUNO =================

    nomeDoAluno = models.CharField(max_length=255)
    nacionaliadeAluno = models.CharField(max_length=100, blank=True, null=True)
    natularidadeAluno = models.CharField(max_length=100, blank=True, null=True)
    ufAluno = models.CharField(max_length=10, blank=True, null=True)
    dataNascimentoAluno = models.DateField(blank=True, null=True)
    sexoDoAluno = models.CharField(max_length=20, blank=True, null=True)
    turmaDoAluno = models.CharField(max_length=50, blank=True, null=True)
    cartaoSusDoAluno = models.CharField(max_length=30, blank=True, null=True)
    cpfDoAluno = models.CharField(max_length=14, blank=True, null=True)
    nomePai = models.CharField(max_length=255, blank=True, null=True)
    nomeMae = models.CharField(max_length=255, blank=True, null=True)
    nomeResponsavel = models.CharField(max_length=255, blank=True, null=True)
    
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nomeDoAluno


class TelefoneDeclaracao(models.Model):
    TIPOS = [
        ("PAI", "Pai"),
        ("MAE", "Mãe"),
        ("RESPONSAVEL", "Responsável"),
    ]

    declaracao = models.ForeignKey(
        declaracao,
        on_delete=models.CASCADE,
        related_name="telefones",
    )
    tipo = models.CharField(max_length=20, choices=TIPOS)
    telefone = models.CharField(max_length=20)

    class Meta:
        ordering = ["tipo", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["declaracao", "tipo", "telefone"],
                name="uniq_telefone_por_responsavel_declaracao",
            )
        ]
        verbose_name = "Telefone da declaração"
        verbose_name_plural = "Telefones da declaração"

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.telefone}"
