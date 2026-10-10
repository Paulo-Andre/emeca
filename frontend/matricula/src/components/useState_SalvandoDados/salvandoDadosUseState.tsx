// ================================
// 🔥 TIPAGEM COMPLETA
// ================================
export type SetDados = {
  // ALUNO
  nomeDoAluno: string;
  nacionalidadeAluno: string;
  naturalidadeAluno: string;
  ufAluno: string;
  dataNascimentoAluno: string;
  sexoDoAluno: string;
  racaCorDoAluno: string;
  cartaoSusDoAluno: string;
  cpfDoAluno: string;
 
  cepAluno: string;
  rgAluno: string;
  orgaoEmissorAluno: string;
  dataExpedicaoAluno: string;
  numeroNisAluno: string;

  possuiLaudoAluno: "sim" | "nao";
  descricaoLaudo: string;
  recebeBeneficioAluno: "sim" | "nao";
  descricaoBeneficio: string;
  alergiaAluno: "sim" | "nao";
  descricaoAlergia: string;
  temIrmaosEscola: "sim" | "nao";
  nomeIrmao: string;
  escolaAnteriorAluno:string;

  // PAI
  nomePai: string;
  nacionalidadePai: string;
  naturalidadePai: string;
  ufPai: string;
  dataDeNascimentoPai: string;
  profissaoPai: string;
  cpfPai: string;
  rgPai: string;
  orgaoEmissorPai: string;
  dataExpedicaoPai: string;
  telefonePai: string;
  whatsappPai: string;

  // MAE
  nomeMae: string;
  nacionalidadeMae: string;
  naturalidadeMae: string;
  ufMae: string;
  dataDeNascimentoMae: string;
  profissaoMae: string;
  cpfMae: string;
  rgMae: string;
  orgaoEmissorMae: string;
  dataExpedicaoMae: string;
  telefoneMae: string;
  whatsappMae: string;

  // RESPONSAVEL
  tipoResponsavel: string;
  nomeResponsavel: string;
  parentesco: string;
  cpfResponsavel: string;
  rgResponsavel: string;
  orgaoEmissorResponsavel: string;
  dataExpedicaoResponsavel: string;
  profissaoResponsavel: string;
  telefoneResponsavel: string;
  whatsappResponsavel: string;

  // ESTADO CIVIL
  estadoCivilPais: string;
  telefoneEmergencia1: string;
  nomeEmergencia1: string;
  telefoneEmergencia2: string;
  nomeEmergencia2: string;
  telefoneEmergencia3: string;
  nomeEmergencia3: string;

  // ENDEREÇO
  rua: string;
  bairro: string;
  cidade: string;
  estado: string;
  cep: string;
  situacaoCasa: string;

  // HISTÓRICO
  problemaSaude: "sim" | "nao";
  problemaSaudeQual: string;

  tratamentoSaude: "sim" | "nao";
  tratamentoSaudeQual: string;

  necessidadeEspecial: "sim" | "nao";
  necessidadeEspecialQual: string;

  medicamento: "sim" | "nao";
  medicamentoQual: string;

  internado: "sim" | "nao";
  internadoMotivo: string;

  atendimentoEspecializado: "sim" | "nao";
  atendimentoEspecializadoMotivo: string;

  salaRecurso: "sim" | "nao";
  salaRecursoMotivo: string;

  cras: "sim" | "nao";
  crasMotivo: string;

  visitaSocial: "sim" | "nao";
  visitaSocialMotivo: string;

  conselhoTutelar: "sim" | "nao";
  conselhoTutelarMotivo: string;

  atendimentoDomiciliar: "sim" | "nao";
  atendimentoDomiciliarMotivo: string;

  tipoDeParto: string;

  gestacao: "sim" | "nao";
  gestacaoMotivo: string;

  transporteEscolar: "sim" | "nao";
  transporteEscolarMotivo: string;
};

// ================================
// 🔥 ESTADO INICIAL
// ================================
export const estadoInicial: SetDados = {
  nomeDoAluno: "",
  nacionalidadeAluno: "",
  naturalidadeAluno: "",
  ufAluno: "",
  dataNascimentoAluno: "",
  sexoDoAluno: "",
  racaCorDoAluno: "",
  cartaoSusDoAluno: "",
  cpfDoAluno: "",
  
  cepAluno: "",
  rgAluno: "",
  orgaoEmissorAluno: "",
  dataExpedicaoAluno: "",
  numeroNisAluno: "",

  possuiLaudoAluno: "nao",
  descricaoLaudo: "",
  recebeBeneficioAluno: "nao",
  descricaoBeneficio: "",
  alergiaAluno: "nao",
  descricaoAlergia: "",
  temIrmaosEscola: "nao",
  nomeIrmao: "",
  escolaAnteriorAluno:"",

  nomePai: "",
  nacionalidadePai: "",
  naturalidadePai: "",
  ufPai: "",
  dataDeNascimentoPai: "",
  profissaoPai: "",
  cpfPai: "",
  rgPai: "",
  orgaoEmissorPai: "",
  dataExpedicaoPai: "",
  telefonePai: "",
  whatsappPai: "",

  nomeMae: "",
  nacionalidadeMae: "",
  naturalidadeMae: "",
  ufMae: "",
  dataDeNascimentoMae: "",
  profissaoMae: "",
  cpfMae: "",
  rgMae: "",
  orgaoEmissorMae: "",
  dataExpedicaoMae: "",
  telefoneMae: "",
  whatsappMae: "",

  tipoResponsavel: "",
  nomeResponsavel: "",
  parentesco: "",
  cpfResponsavel: "",
  rgResponsavel: "",
  orgaoEmissorResponsavel: "",
  dataExpedicaoResponsavel: "",
  profissaoResponsavel: "",
  telefoneResponsavel: "",
  whatsappResponsavel: "",

  estadoCivilPais: "",
  telefoneEmergencia1: "",
  nomeEmergencia1: "",
  telefoneEmergencia2: "",
  nomeEmergencia2: "",
  telefoneEmergencia3: "",
  nomeEmergencia3: "",

  rua: "",
  bairro: "",
  cidade: "",
  estado: "",
  cep: "",
  situacaoCasa: "",

  problemaSaude: "nao",
  problemaSaudeQual: "",
  tratamentoSaude: "nao",
  tratamentoSaudeQual: "",
  necessidadeEspecial: "nao",
  necessidadeEspecialQual: "",
  medicamento: "nao",
  medicamentoQual: "",
  internado: "nao",
  internadoMotivo: "",
  atendimentoEspecializado: "nao",
  atendimentoEspecializadoMotivo: "",
  salaRecurso: "nao",
  salaRecursoMotivo: "",
  cras: "nao",
  crasMotivo: "",
  visitaSocial: "nao",
  visitaSocialMotivo: "",
  conselhoTutelar: "nao",
  conselhoTutelarMotivo: "",
  atendimentoDomiciliar: "nao",
  atendimentoDomiciliarMotivo: "",
  tipoDeParto: "",
  gestacao: "nao",
  gestacaoMotivo: "",
  transporteEscolar: "nao",
  transporteEscolarMotivo: "",
};

// ================================
// 🔥 FUNÇÃO GENÉRICA
// ================================
export function salvaDados<D>(
  e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>,
  setState: React.Dispatch<React.SetStateAction<D>>
) {
  const { name, value } = e.target;

  setState((prev) => ({
    ...prev,
    [name]: value,
  }));
}