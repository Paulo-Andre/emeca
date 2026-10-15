import { Link } from "react-router-dom";
import { ArrowRight, Check } from "lucide-react";
import "../components/css/publico.css";

function MatriculaFim() {
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
          <div className="public-success-badge" aria-hidden="true">
            <Check size={28} />
          </div>
          <span className="matricula-kicker">Dados enviados</span>
          <h1>Preenchimento concluído</h1>

          <p>
            As informações foram enviadas para a escola. A matrícula ainda precisa
            ser concluída presencialmente após a conferência da documentação.
          </p>

          <div className="matricula-alert">
            Leve os documentos exigidos à secretaria. A vaga só será confirmada
            depois da conferência e da assinatura presencial.
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

          <div className="matricula-cta-group">
            <Link to="/Matricula" className="matricula-btn-primary">
              Voltar ao início
              <ArrowRight size={18} />
            </Link>
          </div>
        </section>
      </main>
    </div>
  );
}

export default MatriculaFim;
