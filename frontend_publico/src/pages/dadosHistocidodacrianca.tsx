import "../components/css/formulario.css";
import { useNavigate } from "react-router-dom";
import ProgressBar from "./progressBar";
import { enviarMatricula } from "../components/services/api";
import type { SetDados } from "../components/useState_SalvandoDados/salvandoDadosUseState";
import { salvaDados } from "../components/useState_SalvandoDados/salvandoDadosUseState";

type Props = {
  dado: SetDados;
  setDados: React.Dispatch<React.SetStateAction<SetDados>>;
};

/* 🔥 COMPONENTE FORA (CORREÇÃO DO FOCO) */
type PerguntaProps = {
  label: string;
  name: keyof SetDados;
  nameExtra: keyof SetDados;
  placeholderExtra: string;
  dado: SetDados;
  setDados: React.Dispatch<React.SetStateAction<SetDados>>;
};

function Pergunta({
  label,
  name,
  nameExtra,
  placeholderExtra,
  dado,
  setDados,
}: PerguntaProps){
  return (
    <div className="field">
      <label>{label}</label>

      <select
        name={name}
        value={dado[name] || ""}
        onChange={(e) => salvaDados(e, setDados)}
      >
        <option value="">Selecione</option>
        <option value="sim">Sim</option>
        <option value="nao">Não</option>
      </select>

      {dado[name] === "sim" && (
        <div style={{ marginTop: "10px", gridColumn: "1 / -1" }}>
          <label style={{ fontSize: "12px" }}>
            {placeholderExtra}
          </label>

          <input
            type="text"
            name={nameExtra}
            value={dado[nameExtra] || ""}
            onChange={(e) => salvaDados(e, setDados)}
          />
        </div>
      )}
    </div>
  );
}

export default function DadosHistoricoCrianca({ dado, setDados }: Props) {
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
   
    const form = e.currentTarget;
    

    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    } 
    
    
    try {
      console.log("enviado:", dado);
      const resposta = await enviarMatricula(dado);
      console.log("SALVO:", resposta);
      navigate("/sucesso");
    } catch (erro) {
      console.log("ERRO:", erro);
    }
  };

  return (
    <div className="formulario-page">
      <div className="formulario-container">

        {/* HEADER */}
       
         
                <header className="formulario-header">
                          <div className="header-brand">
                            <img src="logo_escola.svg" alt="Logo" className="header-logo" />
                            <div className="header-text">
                             <h1>Ficha de Matrícula</h1>
              <p>Histórico da Criança</p>
                              
                            </div>
                          </div>
                
                          <ProgressBar etapaAtual={6} />
                        </header>

        {/* FORM */}
        <div className="form-card">
          <form onSubmit={handleSubmit}>

            {/* A. SAÚDE */}
            <div className="section-title">A. Saúde</div>

            <div className="form-grid">
              <Pergunta label="Possui problema de saúde?" name="problemaSaude" nameExtra="problemaSaudeQual" placeholderExtra="Qual problema de saúde?" dado={dado} setDados={setDados} />
              <Pergunta label="Faz tratamento?" name="tratamentoSaude" nameExtra="tratamentoSaudeQual" placeholderExtra="Qual tratamento?" dado={dado} setDados={setDados} />
              <Pergunta label="Possui necessidade especial?" name="necessidadeEspecial" nameExtra="necessidadeEspecialQual" placeholderExtra="Qual necessidade?" dado={dado} setDados={setDados} />
              <Pergunta label="Toma medicamento?" name="medicamento" nameExtra="medicamentoQual" placeholderExtra="Qual medicamento?" dado={dado} setDados={setDados} />
              <Pergunta label="Já foi internado?" name="internado" nameExtra="internadoMotivo" placeholderExtra="Motivo da internação" dado={dado} setDados={setDados} />
            </div>

            {/* B. SOCIAL */}
            <div className="section-title">B. Social</div>

            <div className="form-grid">
              <Pergunta label="Atendimento especializado?" name="atendimentoEspecializado" nameExtra="atendimentoEspecializadoMotivo" placeholderExtra="Qual atendimento?" dado={dado} setDados={setDados} />
              <Pergunta label="Usa sala de recursos?" name="salaRecurso" nameExtra="salaRecursoMotivo" placeholderExtra="Motivo" dado={dado} setDados={setDados} />
              <Pergunta label="Acompanhado pelo CRAS?" name="cras" nameExtra="crasMotivo" placeholderExtra="Motivo" dado={dado} setDados={setDados} />
              <Pergunta label="Recebe visita social?" name="visitaSocial" nameExtra="visitaSocialMotivo" placeholderExtra="Observação" dado={dado} setDados={setDados} />
              <Pergunta label="Conselho tutelar?" name="conselhoTutelar" nameExtra="conselhoTutelarMotivo" placeholderExtra="Observação" dado={dado} setDados={setDados} />
              <Pergunta label="Atendimento domiciliar?" name="atendimentoDomiciliar" nameExtra="atendimentoDomiciliarMotivo" placeholderExtra="Observação" dado={dado} setDados={setDados} />
            </div>

            {/* C. NASCIMENTO */}
            <div className="section-title">C. Nascimento</div>

            <div className="form-grid">

              <div className="field">
                <label>Tipo de parto *</label>
                <select
                  name="tipoDeParto"
                  required
                  onChange={(e) => salvaDados(e, setDados)}
                >
                  <option value="">Selecione</option>
                  <option value="NATURAL">Natural</option>
                  <option value="CESAREA">Cesárea</option>
                  <option value="OUTRO">Outro</option>
                </select>
              </div>

              <Pergunta
                label="Gestação teve complicação?"
                name="gestacao"
                nameExtra="gestacaoMotivo"
                placeholderExtra="Descreva a complicação"
                dado={dado}
                setDados={setDados}
              />

            </div>

            {/* D. TRANSPORTE */}
            <div className="section-title">D. Transporte</div>

            <div className="form-grid">
              <Pergunta
                label="Usa transporte escolar?"
                name="transporteEscolar"
                nameExtra="transporteEscolarMotivo"
                placeholderExtra="Informe detalhes do transporte"
                dado={dado}
                setDados={setDados}
              />
            </div>

            {/* BOTÕES */}
            <div className="form-actions">

              <button
                type="button"
                className="btn-next"
                onClick={() => navigate(-1)}
                style={{ background: "#64748b" }}
              >
                Voltar
              </button>

              <button type="submit" className="btn-next">
                Finalizar
              </button>

            </div>

          </form>
        </div>
      </div>
    </div>
  );
}