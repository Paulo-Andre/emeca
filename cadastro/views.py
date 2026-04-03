import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import matricula  


@csrf_exempt
def cadastrar(request):
    if request.method == 'POST':
        try:
            dados = json.loads(request.body.decode('utf-8'))
            

            nova_matricula = matricula(

                # ================= ALUNO =================
                nomeDoAluno=dados.get('nomeDoAluno', '').strip().upper(),
                nacionaliadeAluno=dados.get('nacionalidadeAluno', '').strip().upper(),
                natularidadeAluno=dados.get('naturalidadeAluno', '').strip().upper(),
                ufAluno=dados.get('ufAluno', '').strip().upper(),
                dataNascimentoAluno=dados.get('dataNascimentoAluno') or None,
                sexoDoAluno=dados.get('sexoDoAluno', '').strip().upper(),
                racaCorDoAluno=dados.get('racaCorDoAluno', '').upper(),
                cartaoSusDoAluno=dados.get('cartaoSusDoAluno'),
                cpfDoAluno=dados.get('cpfDoAluno'),
                rgAluno=dados.get('rgAluno'),
                orgaoEmissorAluno=dados.get('orgaoEmissorAluno', '').strip().upper(),
                dataExpedicaoAluno=dados.get('dataExpedicaoAluno') or None,
                numeroNisAluno=dados.get('numeroNisAluno'),

                cepAluno=dados.get('cepAluno'),

                laudoAluno=dados.get('possuiLaudoAluno', '').upper(),
                recebeBeneficioAluno=dados.get('recebeBeneficioAluno').upper(),
                alergiaAluno=dados.get('alergiaAluno', '').upper(),
                temIrmaosEscola=dados.get('temIrmaosEscola', '').upper(),
                nomeIrmao=dados.get('nomeIrmao', '').strip().upper(),

                descricaoLaudo=dados.get('descricaoLaudo', '').strip().upper(),
                descricaoBeneficio=dados.get('descricaoBeneficio', '').strip().upper(),
                descricaoAlergia=dados.get('descricaoAlergia', '').strip().upper(),

                # ================= PAI =================
                nomePai=dados.get('nomePai', '').strip().upper(),
                nacionalidadePai=dados.get('nacionalidadePai', '').strip().upper(),
                natularidadePai=dados.get('naturalidadePai', '').strip().upper(),
                ufPai=dados.get('ufPai', '').strip().upper(),
                dataDeNascimentoPai=dados.get('dataDeNascimentoPai') or None,
                cpfPai=dados.get('cpfPai'),
                rgPai=dados.get('rgPai'),
                orgaoEmissorPai=dados.get('orgaoEmissorPai', '').strip().upper(),
                dataExpedicaoPai=dados.get('dataExpedicaoPai') or None,
                profissaoPai=dados.get('profissaoPai', '').strip().upper(),
                telefonePai=dados.get('telefonePai'),
                whatsappPai=dados.get('whatsappPai'),

                # ================= MÃE =================
                nomeMae=dados.get('nomeMae', '').strip().upper(),
                nacionalidadeMae=dados.get('nacionalidadeMae', '').strip().upper(),
                natularidadeMae=dados.get('naturalidadeMae', '').strip().upper(),
                ufMae=dados.get('ufMae', '').strip().upper(),
                dataDeNascimentoMae=dados.get('dataDeNascimentoMae') or None,
                cpfMae=dados.get('cpfMae'),
                rgMae=dados.get('rgMae'),
                orgaoEmissorMae=dados.get('orgaoEmissorMae', '').strip().upper(),
                dataExpedicaoMae=dados.get('dataExpedicaoMae') or None,
                profissaoMae=dados.get('profissaoMae', '').strip().upper(),
                telefoneMae=dados.get('telefoneMae'),
                whatsappMae=dados.get('whatsappMae'),

                # ================= RESPONSÁVEL =================
                tipoResponsavel=dados.get('tipoResponsavel', '').upper(),
                nomeResponsavel=dados.get('nomeResponsavel', '').strip().upper(),
                parentesco=dados.get('parentesco', '').strip().upper(),
                cpfResponsavel=dados.get('cpfResponsavel'),
                rgResponsavel=dados.get('rgResponsavel'),
                orgaoEmissorResponsavel=dados.get('orgaoEmissorResponsavel', '').strip().upper(),
                dataExpedicaoResponsavel=dados.get('dataExpedicaoResponsavel') or None,
                profissaoResponsavel=dados.get('profissaoResponsavel', '').strip().upper(),
                telefoneResponsavel=dados.get('telefoneResponsavel'),
                whatsappResponsavel=dados.get('whatsappResponsavel'),

                # ================= ENDEREÇO =================
                rua=dados.get('rua', '').strip().upper(),
                bairro=dados.get('bairro', '').strip().upper(),
                cidade=dados.get('cidade', '').strip().upper(),
                estado=dados.get('estado', '').strip().upper(),
                cep=dados.get('cep'),
                situacaoCasa=dados.get('situacaoCasa', '').upper(),
                estadoCivilPais=dados.get('estadoCivilPais', '').upper(),

                # ================= EMERGÊNCIA =================
                nomeEmergencia1=dados.get('nomeEmergencia1', '').strip().upper(),
                telefoneEmergencia1=dados.get('telefoneEmergencia1'),
                nomeEmergencia2=dados.get('nomeEmergencia2', '').strip().upper(),
                telefoneEmergencia2=dados.get('telefoneEmergencia2'),
                nomeEmergencia3=dados.get('nomeEmergencia3', '').strip().upper(),
                telefoneEmergencia3=dados.get('telefoneEmergencia3'),

                # ================= HISTÓRICO =================
                problemaSaude=dados.get('problemaSaude', '').upper(),
                problemaSaudeQual=dados.get('problemaSaudeQual', '').strip().upper(),
                tratamentoSaude=dados.get('tratamentoSaude', '').upper(),
                tratamentoSaudeQual=dados.get('tratamentoSaudeQual', '').strip().upper(),
                necessidadeEspecial=dados.get('necessidadeEspecial', '').upper(),
                necessidadeEspecialQual=dados.get('necessidadeEspecialQual', '').strip().upper(),
                medicamento=dados.get('medicamento', '').upper(),
                medicamentoQual=dados.get('medicamentoQual', '').strip().upper(),
                internado=dados.get('internado', '').upper(),
                internadoMotivo=dados.get('internadoMotivo', '').strip().upper(),
                atendimentoEspecializado=dados.get('atendimentoEspecializado', '').upper(),
                atendimentoEspecializadoMotivo=dados.get('atendimentoEspecializadoMotivo', '').strip().upper(),
                salaRecurso=dados.get('salaRecurso', '').upper(),
                salaRecursoMotivo=dados.get('salaRecursoMotivo', '').strip().upper(),
                tipoDeParto=dados.get('tipoDeParto', '').strip().upper(),
                gestacao=dados.get('gestacao', '').upper(),
                gestacaoMotivo=dados.get('gestacaoMotivo', '').strip().upper(),
                cras=dados.get('cras', '').upper(),
                crasMotivo=dados.get('crasMotivo', '').strip().upper(),
                visitaSocial=dados.get('visitaSocial', '').upper(),
                visitaSocialMotivo=dados.get('visitaSocialMotivo', '').strip().upper(),
                conselhoTutelar=dados.get('conselhoTutelar', '').upper(),
                conselhoTutelarMotivo=dados.get('conselhoTutelarMotivo', '').strip().upper(),
                atendimentoDomiciliar=dados.get('atendimentoDomiciliar', '').upper(),
                atendimentoDomiciliarMotivo=dados.get('atendimentoDomiciliarMotivo', '').strip().upper(),
                trasporteEscolar=dados.get('transporteEscolar', '').upper(),
                trasporteEscolarMotivo=dados.get('transporteEscolarMotivo', '').strip().upper(),
            )
            print("📦 RECEBIDO:", dados)
            nova_matricula.save()

            return JsonResponse({"status": "sucesso"}, status=201)

        except Exception as e:
            return JsonResponse({"status": "erro", "mensagem": str(e)}, status=400)

    return JsonResponse({"status": "erro"}, status=405)

