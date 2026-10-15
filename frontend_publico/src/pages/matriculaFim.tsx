import { Link } from "react-router-dom";
import { ArrowRight, Check, FileCheck2 } from "lucide-react";
import "../components/css/publico.css";

function MatriculaFim() {
  return (
    <div className="public-page public-page--matricula">
      <main className="matricula-hero">
        <section className="matricula-info matricula-info--success">
          <div className="public-success-badge" aria-hidden="true">
            <Check size={28} />
          </div>

          <span className="matricula-kicker">Dados enviados</span>
          <h1>Preenchimento concluído</h1>

          <p className="matricula-lead">
            As informações foram enviadas para a escola. A equipe fará a conferência
            e poderá entrar em contato caso seja necessário complementar algum dado.
          </p>

          <div className="matricula-alert">
            <strong>Próxima etapa:</strong> leve os documentos exigidos à secretaria.
            A vaga só será confirmada depois da conferência e da assinatura presencial.
          </div>

          <div className="matricula-doc-grid">
            <article>
              <span><FileCheck2 size={18} /></span>
              <div>
                <h3>Responsável</h3>
                <ul>
                  <li>RG e CPF</li>
                  <li>Comprovante de residência</li>
                </ul>
              </div>
            </article>
            <article>
              <span><FileCheck2 size={18} /></span>
              <div>
                <h3>Aluno</h3>
                <ul>
                  <li>Certidão de nascimento</li>
                  <li>RG e CPF, caso possua</li>
                  <li>Cartão do SUS</li>
                  <li>Histórico escolar ou declaração de transferência</li>
                </ul>
              </div>
            </article>
          </div>

          <div className="matricula-cta-group">
            <a href="/" className="matricula-btn-primary">
              Voltar ao site
              <ArrowRight size={18} />
            </a>
            <Link to="/" className="matricula-btn-secondary">
              Nova matrícula
            </Link>
          </div>
        </section>
      </main>
    </div>
  );
}

export default MatriculaFim;
