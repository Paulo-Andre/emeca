from django.db import models

SIM_NAO = [
    ("SIM", "SIM"),
    ("NAO", "NAO"),
]

class matricula(models.Model):

    # ================= ALUNO =================
    nomeDoAluno = models.CharField(max_length=255)
    nacionaliadeAluno = models.CharField(max_length=100, blank=True, null=True)
    natularidadeAluno = models.CharField(max_length=100, blank=True, null=True)
    ufAluno = models.CharField(max_length=10, blank=True, null=True)
    dataNascimentoAluno = models.DateField(blank=True, null=True)
    sexoDoAluno = models.CharField(max_length=20, blank=True, null=True)
    racaCorDoAluno = models.CharField(max_length=50, blank=True, null=True)
    cartaoSusDoAluno = models.CharField(max_length=30, blank=True, null=True)
    cpfDoAluno = models.CharField(max_length=14, blank=True, null=True)
    rgAluno = models.CharField(max_length=20, blank=True, null=True)
    orgaoEmissorAluno = models.CharField(max_length=20, blank=True, null=True)
    dataExpedicaoAluno = models.DateField(blank=True, null=True)
    numeroNisAluno = models.CharField(max_length=30, blank=True, null=True)

    # 🔥 NOVOS CAMPOS
    cepAluno = models.CharField(max_length=15, blank=True, null=True)

    laudoAluno = models.CharField(max_length=10, choices=SIM_NAO, blank=True, null=True)
    descricaoLaudo = models.TextField(blank=True, null=True)

    recebeBeneficioAluno = models.CharField(max_length=10, choices=SIM_NAO, blank=True, null=True)
    descricaoBeneficio = models.TextField(blank=True, null=True)

    alergiaAluno = models.CharField(max_length=10, choices=SIM_NAO, blank=True, null=True)
    descricaoAlergia = models.TextField(blank=True, null=True)

    temIrmaosEscola = models.CharField(max_length=3, choices=SIM_NAO)
    nomeIrmao = models.CharField(max_length=255, blank=True, null=True)
    escolaAnteriorAluno=models.CharField(max_length=255, blank=True, null=True)

    # ================= PAI =================
    nomePai = models.CharField(max_length=255, blank=True, null=True)
    nacionalidadePai = models.CharField(max_length=100, blank=True, null=True)
    natularidadePai = models.CharField(max_length=100, blank=True, null=True)
    ufPai = models.CharField(max_length=10, blank=True, null=True)
    dataDeNascimentoPai = models.DateField(blank=True, null=True)
    cpfPai = models.CharField(max_length=14, blank=True, null=True)
    rgPai = models.CharField(max_length=20, blank=True, null=True)
    orgaoEmissorPai = models.CharField(max_length=20, blank=True, null=True)
    dataExpedicaoPai = models.DateField(blank=True, null=True)
    profissaoPai = models.CharField(max_length=100, blank=True, null=True)
    telefonePai = models.CharField(max_length=20, blank=True, null=True)
    whatsappPai = models.CharField(max_length=20, blank=True, null=True)

    # ================= MÃE =================
    nomeMae = models.CharField(max_length=255, blank=True, null=True)
    nacionalidadeMae = models.CharField(max_length=100, blank=True, null=True)
    natularidadeMae = models.CharField(max_length=100, blank=True, null=True)
    ufMae = models.CharField(max_length=10, blank=True, null=True)
    dataDeNascimentoMae = models.DateField(blank=True, null=True)
    cpfMae = models.CharField(max_length=14, blank=True, null=True)
    rgMae = models.CharField(max_length=20, blank=True, null=True)
    orgaoEmissorMae = models.CharField(max_length=20, blank=True, null=True)
    dataExpedicaoMae = models.DateField(blank=True, null=True)
    profissaoMae = models.CharField(max_length=100, blank=True, null=True)
    telefoneMae = models.CharField(max_length=20, blank=True, null=True)
    whatsappMae = models.CharField(max_length=20, blank=True, null=True)

    # ================= RESPONSÁVEL =================
    quemResponsavel = models.CharField(max_length=255, blank=True, null=True)

    # 🔥 NOVO
    tipoResponsavel = models.CharField(max_length=50, blank=True, null=True)

    nomeResponsavel = models.CharField(max_length=255, blank=True, null=True)
    parentesco = models.CharField(max_length=100, blank=True, null=True)
    cpfResponsavel = models.CharField(max_length=14, blank=True, null=True)
    rgResponsavel = models.CharField(max_length=20, blank=True, null=True)
    orgaoEmissorResponsavel = models.CharField(max_length=20, blank=True, null=True)
    dataExpedicaoResponsavel = models.DateField(blank=True, null=True)
    profissaoResponsavel = models.CharField(max_length=100, blank=True, null=True)
    telefoneResponsavel = models.CharField(max_length=20, blank=True, null=True)
    whatsappResponsavel = models.CharField(max_length=20, blank=True, null=True)

    # ================= ENDEREÇO =================
    rua = models.CharField(max_length=255, blank=True, null=True)
    bairro = models.CharField(max_length=100, blank=True, null=True)
    cidade = models.CharField(max_length=100, blank=True, null=True)
    estado = models.CharField(max_length=50, blank=True, null=True)
    cep = models.CharField(max_length=15, blank=True, null=True)
    situacaoCasa = models.CharField(max_length=100, blank=True, null=True)
    estadoCivilPais = models.CharField(max_length=50, blank=True, null=True)

    # ================= EMERGÊNCIA =================
    nomeEmergencia1 = models.CharField(max_length=255, blank=True, null=True)
    telefoneEmergencia1 = models.CharField(max_length=20, blank=True, null=True)
    nomeEmergencia2 = models.CharField(max_length=255, blank=True, null=True)
    telefoneEmergencia2 = models.CharField(max_length=20, blank=True, null=True)
    nomeEmergencia3 = models.CharField(max_length=255, blank=True, null=True)
    telefoneEmergencia3 = models.CharField(max_length=20, blank=True, null=True)

    # ================= HISTÓRICO =================
    problemaSaude = models.CharField(max_length=3, choices=SIM_NAO)
    problemaSaudeQual = models.CharField(max_length=255, blank=True, null=True)

    tratamentoSaude = models.CharField(max_length=3, choices=SIM_NAO)
    tratamentoSaudeQual = models.CharField(max_length=255, blank=True, null=True)

    necessidadeEspecial = models.CharField(max_length=3, choices=SIM_NAO)
    necessidadeEspecialQual = models.CharField(max_length=255, blank=True, null=True)

    medicamento = models.CharField(max_length=3, choices=SIM_NAO)
    medicamentoQual = models.CharField(max_length=255, blank=True, null=True)

    internado = models.CharField(max_length=3, choices=SIM_NAO)
    internadoMotivo = models.CharField(max_length=255, blank=True, null=True)

    atendimentoEspecializado = models.CharField(max_length=3, choices=SIM_NAO)
    atendimentoEspecializadoMotivo = models.CharField(max_length=255, blank=True, null=True)

    salaRecurso = models.CharField(max_length=3, choices=SIM_NAO)
    salaRecursoMotivo = models.CharField(max_length=255, blank=True, null=True)

    tipoDeParto = models.CharField(max_length=100, blank=True, null=True)

    gestacao = models.CharField(max_length=3, choices=SIM_NAO)
    gestacaoMotivo = models.CharField(max_length=255, blank=True, null=True)

    cras = models.CharField(max_length=3, choices=SIM_NAO)
    crasMotivo = models.CharField(max_length=255, blank=True, null=True)

    visitaSocial = models.CharField(max_length=3, choices=SIM_NAO)
    visitaSocialMotivo = models.CharField(max_length=255, blank=True, null=True)

    conselhoTutelar = models.CharField(max_length=3, choices=SIM_NAO)
    conselhoTutelarMotivo = models.CharField(max_length=255, blank=True, null=True)

    atendimentoDomiciliar = models.CharField(max_length=3, choices=SIM_NAO)
    atendimentoDomiciliarMotivo = models.CharField(max_length=255, blank=True, null=True)

    trasporteEscolar = models.CharField(max_length=3, choices=SIM_NAO)
    trasporteEscolarMotivo = models.CharField(max_length=255, blank=True, null=True)

    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nomeDoAluno