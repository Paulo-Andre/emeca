import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import "../components/css/publico.css";

function DuvidasMatricula() {
  const [confirmado, setConfirmado] = useState(false);
  const logo = `${import.meta.env.BASE_URL}logo_escola.svg`;

  return (
    <div className="public-page">
      <header className="matricula-header">
        <div className="matricula-header-container">
          <div className="matricula-brand">
            <img src={logo} alt="" className="matricula-logo" />
            <span className="matricula-brand-copy">
              <strong>E. M. Egídio Cordeiro Aquino</strong>
              <span>Matrícula online</span>
            </span>
          </div>

          <a href="/login/" className="matricula-btn-nav">
            Área da secretaria
          </a>
        </div>
      </header>

      <main className="matricula-hero">
        <section className="matricula-info">
          <span className="matricula-kicker">Antes de começar</span>
          <h1>Matrícula Online</h1>

          <p>
            Este formulário agiliza o atendimento da escola, mas o preenchimento
            online <strong>não confirma a vaga automaticamente</strong>.
          </p>

          <div className="matricula-alert">
            Preencha somente após a confirmação de vaga pela escola ou após o
            encaminhamento do Cadastro Escolar. A matrícula será concluída após
            a conferência dos documentos e a assinatura presencial.
          </div>

          <h3>Documentos do responsável</h3>
          <ul>
            <li>RG e CPF (cópias)</li>
            <li>Comprovante de residência</li>
          </ul>

          <h3>Documentos do aluno</h3>
          <ul>
            <li>Certidão de nascimento</li>
            <li>RG e CPF, caso possua</li>
            <li>Cartão do SUS</li>
            <li>Histórico escolar ou declaração de transferência (original)</li>
          </ul>

          <label className="confirmacao-container">
            <input
              type="checkbox"
              checked={confirmado}
              onChange={() => setConfirmado((valor) => !valor)}
            />
            <span>
              Estou ciente de que o preenchimento online não garante a vaga e
              que a matrícula precisa ser concluída presencialmente.
            </span>
          </label>

          <div className="matricula-cta-group">
            {confirmado ? (
              <Link to="/Matricula" className="matricula-btn-primary">
                Iniciar preenchimento
                <ArrowRight size={18} />
              </Link>
            ) : (
              <div className="matricula-btn-primary disabled" aria-disabled="true">
                Marque a confirmação para continuar
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

export default DuvidasMatricula;
