import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, FileCheck2, School } from "lucide-react";
import "../components/css/publico.css";

function DuvidasMatricula() {
  const [confirmado, setConfirmado] = useState(false);

  return (
    <div className="public-page public-page--matricula">
      <main className="matricula-hero">
        <section className="matricula-info matricula-info--intro">
          <div className="matricula-intro-icon" aria-hidden="true">
            <School size={30} />
          </div>

          <span className="matricula-kicker">Matrícula 2026</span>
          <h1>Preenchimento online</h1>

          <p className="matricula-lead">
            Organize as informações do estudante e dos responsáveis com calma.
            O formulário é dividido em etapas e pode ser preenchido pelo celular.
          </p>

          <div className="matricula-alert">
            <strong>Importante:</strong> o preenchimento online agiliza o atendimento,
            mas <strong>não confirma a vaga automaticamente</strong>. A matrícula será
            concluída após a conferência dos documentos e a assinatura presencial.
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
                  <li>Histórico ou declaração de transferência</li>
                </ul>
              </div>
            </article>
          </div>

          <label className="confirmacao-container">
            <input
              type="checkbox"
              checked={confirmado}
              onChange={() => setConfirmado((valor) => !valor)}
            />
            <span>
              Estou ciente de que o preenchimento online não garante a vaga e que
              a matrícula precisa ser concluída presencialmente.
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
                <CheckCircle2 size={18} />
                Marque a confirmação para continuar
              </div>
            )}

            <a href="/matricula-escolar/" className="matricula-btn-secondary">
              Voltar às orientações
            </a>
          </div>
        </section>
      </main>
    </div>
  );
}

export default DuvidasMatricula;
