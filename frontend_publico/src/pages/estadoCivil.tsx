import "../components/css/formulario.css";
import { useNavigate } from "react-router-dom";
import ProgressBar from "./progressBar";
import type { SetDados } from "../components/useState_SalvandoDados/salvandoDadosUseState";
import { salvaDados } from "../components/useState_SalvandoDados/salvandoDadosUseState";

type Props = {
  dado: SetDados;
  setDados: React.Dispatch<React.SetStateAction<SetDados>>;
};

export default function EstadoCivil({ dado, setDados }: Props) {
  const navigate = useNavigate();

  // 🔹 MÁSCARA TELEFONE
  const mascaraTelefone = (valor: string) => {
    return valor
      .replace(/\D/g, "")
      .replace(/(\d{2})(\d)/, "($1) $2")
      .replace(/(\d{5})(\d)/, "$1-$2")
      .slice(0, 15);
  };

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    const form = e.currentTarget;

    if (form.checkValidity()) {
      navigate("/DadosResponsavel");
    } else {
      form.reportValidity();
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
              <p>Estado Civil e Contatos</p>
                                      
                                    </div>
                                  </div>
                        
                                  <ProgressBar etapaAtual={4} />
                                </header>

        {/* FORM */}
        <div className="form-card">
          <form onSubmit={handleSubmit}>

            {/* A. ESTADO CIVIL */}
            <div className="section-title">A. Estado Civil dos Pais</div>

            <div className="form-grid">

              <div className="field">
                <label>Estado civil *</label>
                <select
                  name="estadoCivilPais"
                  required
                  onChange={(e) => salvaDados(e, setDados)}
                >
                  <option value="">Selecione</option>
                  <option value="SOLTEIRO(A)">Solteiro(a)</option>
                  <option value="CASADO(A)">Casado(a)</option>
                  <option value="DIVORCIADO(A)">Divorciado(a)</option>
                  <option value="VIUVO(A)">Viúvo(a)</option>
                  <option value="UNIAOESTAVEL">União Estável</option>
                  <option value="OUTRO">Outro</option>
                </select>
              </div>

            </div>

            {/* B. CONTATOS */}
            <div className="section-title">B. Contatos de Emergência</div>

            <div className="form-grid">

              {/* CONTATO 1 */}
              <div className="field">
                <label>Telefone 1 *</label>
                <input
                  name="telefoneEmergencia1"
                  required
                  onChange={(e) => {
                    e.target.value = mascaraTelefone(e.target.value);
                    salvaDados(e, setDados);
                  }}
                />
              </div>

              <div className="field">
                <label>Falar com *</label>
                <input
                  name="nomeEmergencia1"
                  required
                  onChange={(e) => salvaDados(e, setDados)}
                />
              </div>

              {/* CONTATO 2 */}
              <div className="field">
                <label>Telefone 2 *</label>
                <input
                  name="telefoneEmergencia2"
                  required
                  onChange={(e) => {
                    e.target.value = mascaraTelefone(e.target.value);
                    salvaDados(e, setDados);
                  }}
                />
              </div>

              <div className="field">
                <label>Falar com *</label>
                <input
                  name="nomeEmergencia2"
                  required
                  onChange={(e) => salvaDados(e, setDados)}
                />
              </div>

              {/* CONTATO 3 */}
              <div className="field">
                <label>Telefone 3 *</label>
                <input
                  name="telefoneEmergencia3"
                  required
                  onChange={(e) => {
                    e.target.value = mascaraTelefone(e.target.value);
                    salvaDados(e, setDados);
                  }}
                />
              </div>

              <div className="field">
                <label>Falar com *</label>
                <input
                  name="nomeEmergencia3"
                  required
                  onChange={(e) => salvaDados(e, setDados)}
                />
              </div>

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
                Próximo
              </button>

            </div>

          </form>
        </div>
      </div>
    </div>
  );
}