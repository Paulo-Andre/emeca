from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic.edit import CreateView
from django.urls import reverse_lazy
from django.contrib.auth.hashers import make_password
from django.contrib import messages
from django.contrib.auth import get_user_model
from .forms import AccountSignupForm
from cadastro.models import matricula
from django.contrib.auth import logout
import re
import pandas as pd
from datetime import datetime
from .models import declaracao
from django.http import JsonResponse
import json
from django.utils import timezone
from django.db import connection
from django.http import HttpResponseForbidden
from functools import wraps
from django.utils.decorators import method_decorator

User = get_user_model()

def apenas_paulo(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.username != "Paulo":
            return HttpResponseForbidden("Acesso negado")
        return view_func(request, *args, **kwargs)
    return _wrapped_view
@method_decorator(apenas_paulo, name='dispatch') 
class AccountCreateView(CreateView):
    model = User
    template_name = 'registration/signup_form.html'
    form_class = AccountSignupForm
    success_url = reverse_lazy('login')
    success_message = 'Funcionário cadastrado com sucesso!'

    def form_valid(self, form) -> HttpResponse:
        form.instance.password = make_password(form.instance.password)
        messages.success(self.request, self.success_message)
        return super().form_valid(form)
    
def dashboard(request):
    return render(request, 'dashboard.html')


def buscar_cadrasto(request):
    valor = request.POST.get("busca")
    tipo = request.POST.get("tipo")

    resultados = None

    if valor:
        if tipo == "nome":
            resultados = matricula.objects.filter(
                nomeDoAluno__icontains=valor
            )

        elif tipo == "cpf":
            valor = re.sub(r'\D', '', valor)
            resultados = matricula.objects.filter(
                cpfDoAluno__icontains=valor
            )

        elif tipo == "cpf_mae":
            valor = re.sub(r'\D', '', valor)
            resultados = matricula.objects.filter(
                cpfMae__icontains=valor
            )

    contexto = {
        "alunos": resultados
    }
    # fallback normal
    return render(request, "dashboard.html", contexto)

def edit_aluno(request, id):

    aluno = get_object_or_404(matricula, id=id)
    if request.method == "POST":
        
      
               # ================= ALUNO =================
        aluno.nomeDoAluno = request.POST.get('nomeDoAluno', '').strip().upper()
        aluno.nacionaliadeAluno = request.POST.get('nacionaliadeAluno', '').strip().upper()
        aluno.natularidadeAluno = request.POST.get('natularidadeAluno', '').strip().upper()
        aluno.ufAluno = request.POST.get('ufAluno', '').strip().upper()
        aluno.dataNascimentoAluno = request.POST.get('dataNascimentoAluno') or None
        aluno.sexoDoAluno = request.POST.get('sexoDoAluno', '').strip().upper()
        aluno.racaCorDoAluno = request.POST.get('racaCorDoAluno', '').strip().upper()
        aluno.cartaoSusDoAluno = request.POST.get('cartaoSusDoAluno')
        aluno.cpfDoAluno = request.POST.get('cpfDoAluno')
        aluno.laudoAluno = request.POST.get('laudoAluno', '').strip().upper()
        aluno.rgAluno = request.POST.get('rgAluno')
        aluno.orgaoEmissorAluno = request.POST.get('orgaoEmissorAluno', '').strip().upper()
        aluno.dataExpedicaoAluno = request.POST.get('dataExpedicaoAluno') or None
        aluno.recebeBeneficioAluno = request.POST.get('recebeBeneficioAluno').strip().upper()
        aluno.numeroNisAluno = request.POST.get('numeroNisAluno')
        aluno.alergiaAluno = request.POST.get('alergiaAluno', '').strip().upper()
        aluno.temIrmaosEscola = request.POST.get('temIrmaosEscola', '').strip().upper()
        aluno.nomeIrmao = request.POST.get('nomeIrmao', '').strip().upper()
        aluno.escolaAnteriorAluno = request.POST.get('escolaAnteriorAluno', '').strip().upper()

        # ================= PAI =================
        aluno.nomePai = request.POST.get('nomePai', '').strip().upper()
        aluno.nacionalidadePai = request.POST.get('nacionalidadePai', '').strip().upper()
        aluno.natularidadePai = request.POST.get('natularidadePai', '').strip().upper()
        aluno.ufPai = request.POST.get('ufPai', '').strip().upper()
        aluno.dataDeNascimentoPai = request.POST.get('dataDeNascimentoPai') or None
        aluno.cpfPai = request.POST.get('cpfPai')
        aluno.rgPai = request.POST.get('rgPai')
        aluno.orgaoEmissorPai = request.POST.get('orgaoEmissorPai', '').strip().upper()
        aluno.dataExpedicaoPai = request.POST.get('dataExpedicaoPai') or None
        aluno.profissaoPai = request.POST.get('profissaoPai', '').strip().upper()
        aluno.telefonePai = request.POST.get('telefonePai')
        aluno.whatsappPai = request.POST.get('whatsappPai')

        # ================= MÃE =================
        aluno.nomeMae = request.POST.get('nomeMae', '').strip().upper()
        aluno.nacionalidadeMae = request.POST.get('nacionalidadeMae', '').strip().upper()
        aluno.natularidadeMae = request.POST.get('natularidadeMae', '').strip().upper()
        aluno.ufMae = request.POST.get('ufMae', '').strip().upper()
        aluno.dataDeNascimentoMae = request.POST.get('dataDeNascimentoMae') or None
        aluno.cpfMae = request.POST.get('cpfMae')
        aluno.rgMae = request.POST.get('rgMae')
        aluno.orgaoEmissorMae = request.POST.get('orgaoEmissorMae', '').strip().upper()
        aluno.dataExpedicaoMae = request.POST.get('dataExpedicaoMae') or None
        aluno.profissaoMae = request.POST.get('profissaoMae', '').strip().upper()
        aluno.telefoneMae = request.POST.get('telefoneMae')
        aluno.whatsappMae = request.POST.get('whatsappMae')

        # ================= RESPONSÁVEL =================
        aluno.quemResponsavel= request.POST.get('responsavel', '').strip().upper()
        aluno.nomeResponsavel = request.POST.get('nomeResponsavel', '').strip().upper()
        aluno.parentesco = request.POST.get('parentesco', '').strip().upper()
        aluno.cpfResponsavel = request.POST.get('cpfResponsavel')
        aluno.rgResponsavel = request.POST.get('rgResponsavel')
        aluno.orgaoEmissorResponsavel = request.POST.get('orgaoEmissorResponsavel', '').strip().upper()
        aluno.dataExpedicaoResponsavel = request.POST.get('dataExpedicaoResponsavel') or None
        aluno.profissaoResponsavel = request.POST.get('profissaoResponsavel', '').strip().upper()
        aluno.telefoneResponsavel = request.POST.get('telefoneResponsavel')
        aluno.whatsappResponsavel = request.POST.get('whatsappResponsavel')

        # ================= ENDEREÇO =================
        aluno.rua = request.POST.get('rua', '').strip().upper()
        aluno.bairro = request.POST.get('bairro', '').strip().upper()
        aluno.cidade = request.POST.get('cidade', '').strip().upper()
        aluno.estado = request.POST.get('estado', '').strip().upper()
        aluno.cep = request.POST.get('cep')
        aluno.situacaoCasa = request.POST.get('situacaoCasa', '').strip().upper()
        aluno.estadoCivilPais = request.POST.get('estadoCivilPais', '').strip().upper()

        # ================= EMERGÊNCIA =================
        aluno.nomeEmergencia1 = request.POST.get('nomeEmergencia1', '').strip().upper()
        aluno.telefoneEmergencia1 = request.POST.get('telefoneEmergencia1')
        aluno.nomeEmergencia2 = request.POST.get('nomeEmergencia2', '').strip().upper()
        aluno.telefoneEmergencia2 = request.POST.get('telefoneEmergencia2')
        aluno.nomeEmergencia3 = request.POST.get('nomeEmergencia3', '').strip().upper()
        aluno.telefoneEmergencia3 = request.POST.get('telefoneEmergencia3')

        # ================= SAÚDE =================
        aluno.problemaSaude = request.POST.get('problemaSaude', '').strip().upper()
        aluno.problemaSaudeQual = request.POST.get('problemaSaudeQual', '').strip().upper()
        aluno.tratamentoSaude = request.POST.get('tratamentoSaude', '').strip().upper()
        aluno.tratamentoSaudeQual = request.POST.get('tratamentoSaudeQual', '').strip().upper()
        aluno.necessidadeEspecial = request.POST.get('necessidadeEspecial', '').strip().upper()
        aluno.necessidadeEspecialQual = request.POST.get('necessidadeEspecialQual', '').strip().upper()
        aluno.medicamento = request.POST.get('medicamento', '').strip().upper()
        aluno.medicamentoQual = request.POST.get('medicamentoQual', '').strip().upper()
        aluno.internado = request.POST.get('internado', '').strip().upper()
        aluno.internadoMotivo = request.POST.get('internadoMotivo', '').strip().upper()
        aluno.atendimentoEspecializado = request.POST.get('atendimentoEspecializado', '').strip().upper()
        aluno.atendimentoEspecializadoMotivo = request.POST.get('atendimentoEspecializadoMotivo', '').strip().upper()
        aluno.salaRecurso = request.POST.get('salaRecurso', '').strip().upper()
        aluno.salaRecursoMotivo = request.POST.get('salaRecursoMotivo', '').strip().upper()
        aluno.tipoDeParto = request.POST.get('tipoDeParto', '').strip().upper()
        aluno.gestacao = request.POST.get('gestacao', '').strip().upper()
        aluno.gestacaoMotivo = request.POST.get('gestacaoMotivo', '').strip().upper()
        aluno.cras = request.POST.get('cras', '').strip().upper()
        aluno.crasMotivo = request.POST.get('crasMotivo', '').strip().upper()
        aluno.visitaSocial = request.POST.get('visitaSocial', '').strip().upper()
        aluno.visitaSocialMotivo = request.POST.get('visitaSocialMotivo', '').strip().upper()
        aluno.conselhoTutelar = request.POST.get('conselhoTutelar', '').strip().upper()
        aluno.conselhoTutelarMotivo = request.POST.get('conselhoTutelarMotivo', '').strip().upper()
        aluno.atendimentoDomiciliar = request.POST.get('atendimentoDomiciliar', '').strip().upper()
        aluno.atendimentoDomiciliarMotivo = request.POST.get('atendimentoDomiciliarMotivo', '').strip().upper()
        aluno.trasporteEscolar = request.POST.get('trasporteEscolar', '').strip().upper()
        aluno.trasporteEscolarMotivo = request.POST.get('trasporteEscolarMotivo', '').strip().upper()
                
        aluno.save()
        messages.success(request,"Dados atualizados com sucesso!")
        return redirect('dashboard')
        

    contexto = {
        "aluno": aluno
    }

    return render(request, "edit_aluno.html", contexto)
def deletar_aluno(request, id):

    aluno = get_object_or_404(matricula, id=id)

    if request.method == "POST":
        aluno.delete()
        messages.success(request, "Aluno removido do sistema com sucesso!")
        return redirect('dashboard')

    return redirect('dashboard')

def matriculaimpressao(request,  id):
    aluno = get_object_or_404(matricula, id=id) 
    contexto = {
        "aluno": aluno
    }

    return render(request, "matriculaimpressao.html", contexto)

def sair(request):
    logout(request)
    return redirect('login')  

def declaracoes(request):
    return render(request, "declaracoes.html")


def historico(request):
    return render(request, "historico.html")


def transferencia(request):
    
    return render(request, "declaracoes/transferencia.html")
def escolaridade(request):
    return render(request, "declaracoes/escolaridade.html")
def bolsaFamilia(request):
    return render(request, "declaracoes/bolsaFamilia.html")
def comparecimento(request):
    return render(request, "declaracoes/comparecimento.html")
def telaDeclaracao(request):
    return render(request, "declaracoes/telaDeclaracao.html")
@apenas_paulo 
def importar_alunos(request):

    if request.method == "POST":
        arquivo = request.FILES.get("arquivo")

        if arquivo:
            df = pd.read_excel(arquivo)

            for _, row in df.iterrows():

                # Converter data
                data_nascimento = None
                if pd.notna(row["NASCIMENTO"]):
                    data_nascimento = datetime.strptime(
                        str(row["NASCIMENTO"]), "%d/%m/%Y"
                    ).date()

                declaracao.objects.create(
                    nomeDoAluno=row["NOME"],
                    ufAluno=row["UF"],
                    nomePai=row["PAI"],
                    nomeMae=row["MÃE"],
                    dataNascimentoAluno=data_nascimento,
                    natularidadeAluno=row["NATURALIDADE"],
                    nacionaliadeAluno=row["NACIONALIDADE"],
                    sexoDoAluno=row["SEXO"],
                    turmaDoAluno=row["TURMA"],
                )
            messages.success(request, "Dados importados com sucesso!")
        else:
            messages.error(request, "Selecione um arquivo!")
        return redirect("importar_alunos")
        

    return render(request, "declaracoes/importardados.html")

def buscar_dados_declaracao(request):
    valor = request.POST.get("busca")
    tipo = request.POST.get("tipo")

    resultados = None

    if valor:
        if tipo == "nome":
            resultados = declaracao.objects.filter(
                nomeDoAluno__icontains=valor
            )

        elif tipo == "cpf":
            valor = re.sub(r'\D', '', valor)
            resultados = declaracao.objects.filter(
                cpfDoAluno__icontains=valor
            )

        elif tipo == "cpf_mae":
            valor = re.sub(r'\D', '', valor)
            resultados = declaracao.objects.filter(
                cpfMae__icontains=valor
            )

    contexto = {
        "alunos": resultados
    }
    
    # fallback normal
    return render(request, "declaracoes/telaDeclaracao.html", contexto)
def salvar_declaracao(request, id):
    if request.method == "POST":
        data = json.loads(request.body)

        aluno = declaracao.objects.get(id=id)

        aluno.nomeDoAluno = data.get("nome")
        aluno.dataNascimentoAluno = data.get("nasc")
        aluno.natularidadeAluno = data.get("naturalidade")
        aluno.turmaDoAluno = data.get("serie")
        aluno.nomeMae = data.get("mae")
        aluno.nomePai = data.get("pai")

        aluno.save()

        return JsonResponse({"status": "ok"})
def imprimirDeclaracao(request, id):
    data = json.loads(request.body)
    tipo = data.get("tipo")
    nasc_str = data.get("nasc")

    try:
        nasc_formatado = datetime.strptime(nasc_str, "%Y-%m-%d").strftime("%d / %m / %Y")
    except:
        nasc_formatado = ""
    
   
    
    contexto = {
        "nome": data.get("nome"),
        "nasc": nasc_formatado,
        "naturalidade": data.get("naturalidade"),
        "serie": data.get("serie")[0],
        "mae": data.get("mae"),
        "pai": data.get("pai"),
        "anoCursa": data.get("anoCursa"),
        "responsavel": data.get("responsavel"),
        "ano":data.get("ano"),
        "data_atual": timezone.now(),
        "mostrar_assinatura": str(data.get("assinatura")).lower() == "true",
        "mostrar_carimbo": str(data.get("carimbo")).lower() == "true",
        "horarioin": data.get("horarioin"),
        "horariofim": data.get("horariofim"),
        "datareuniao": data.get("datareuniao"),
    }
    mapa_templates = {
    "Escolaridade": "declaracoes/escolaridade.html",
    "Transferência": "declaracoes/transferencia.html",
    "Bolsa Família": "declaracoes/bolsaFamilia.html",
    "Empresa": "declaracoes/empresa.html",
    "Comparecimento": "declaracoes/comparecimento.html",
    }

    template = mapa_templates.get(tipo)

    return render(request, template, contexto)
def deletar_aluno_declaracao(request, id):

    aluno = get_object_or_404(declaracao, id=id)

    if request.method == "POST":
        aluno.delete()
        messages.success(request, "Aluno removido do sistema com sucesso!")
        return redirect('telaDeclaracao')

    return redirect('telaDeclaracao')
def cadastrar_aluno(request):
    if request.method == "POST":
        declaracao.objects.create(
            nomeDoAluno=request.POST.get("nomeDoAluno"),
            nacionaliadeAluno=request.POST.get("nacionaliadeAluno"),
            natularidadeAluno=request.POST.get("natularidadeAluno"),
            ufAluno=request.POST.get("ufAluno"),
            dataNascimentoAluno=request.POST.get("dataNascimentoAluno"),
            sexoDoAluno=request.POST.get("sexoDoAluno"),
            turmaDoAluno=request.POST.get("turmaDoAluno"),
            cartaoSusDoAluno=request.POST.get("cartaoSusDoAluno"),
            cpfDoAluno=request.POST.get("cpfDoAluno"),
            nomePai=request.POST.get("nomePai"),
            nomeMae=request.POST.get("nomeMae"),
        )
        return redirect('telaDeclaracao')  
@apenas_paulo   
def apagar_todos_alunos(request):
        if request.user.is_superuser:

            tabela = declaracao._meta.db_table  
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM {tabela};")
                cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{tabela}';")
                messages.success(request, "Todos os alunos foram apagados com sucesso!")

        return redirect('dashboard')
@apenas_paulo    
def apagar_todos_alunos_matricula(request):
        if request.user.is_superuser:

            tabela = matricula._meta.db_table  
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM {tabela};")
                cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{tabela}';")
                messages.success(request, "Todos os alunos foram apagados com sucesso!")

        return redirect('dashboard')
    
