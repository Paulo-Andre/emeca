
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

function DuvidasMatricula() {
  

  const styles = `
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap');

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      font-family: 'Poppins', sans-serif;
    }

    /* HEADER */
    .matricula-header {
      background: rgba(255, 255, 255, 0.95);
      padding: 16px 30px;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
      position: sticky;
      top: 0;
      z-index: 100;
    }

    .matricula-header-container {
      max-width: 1200px;
      margin: 0 auto;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: relative;
    }

    .matricula-logo {
      height: 80px;
      width: auto;
      position: absolute;
      left: 50%;
      transform: translate(-50%, 0);
      transition: transform 0.3s ease;
    }

    .matricula-logo:hover {
      transform: translate(-50%, 0) scale(1.1);
    }

    .matricula-nav {
      margin-left: auto;
    }

    .matricula-btn-nav {
      background: linear-gradient(135deg, #2ecc71, #27ae60);
      color: #07452e;
      padding: 10px 18px;
      border-radius: 8px;
      text-decoration: none;
      font-weight: 600;
    }

    /* HERO */
    .matricula-hero {
      background: linear-gradient(135deg, #0d5e3f, #094033);
      min-height: 100vh;
      display: flex;
      justify-content: center;
      align-items: center;
      padding: 40px 20px;
    }

    /* CARD */
    .matricula-info {
      max-width: 850px;
      width: 100%;
      background: rgba(255, 255, 255, 0.08);
      backdrop-filter: blur(12px);
      padding: 40px;
      border-radius: 16px;
      border: 1px solid rgba(255,255,255,0.15);
      color: white;
      line-height: 1.6;
      box-shadow: 0 10px 40px rgba(0,0,0,0.3);
    }

    .matricula-info h2 {
      color: #2ecc71;
    }

    .matricula-info h3 {
      margin-top: 25px;
      border-bottom: 1px solid rgba(255,255,255,0.2);
      padding-bottom: 6px;
    }

    .matricula-info ul {
      padding-left: 20px;
    }

    /* CHECKBOX */
    .confirmacao-container {
      background: rgba(46,204,113,0.12);
      padding: 18px;
      border-radius: 12px;
      margin-top: 30px;
      display: flex;
      gap: 10px;
      border: 1px solid rgba(46,204,113,0.4);
      cursor: pointer;
      transition: 0.3s;
      align-items: center;
    }

    .confirmacao-container:hover {
      background: rgba(46,204,113,0.2);
    }

    .confirmacao-container input {
      width: 20px;
      height: 20px;
    }

    /* BOTÕES */
    .matricula-cta-group {
      margin-top: 30px;
    }

    .matricula-btn-primary {
      background: linear-gradient(135deg, #2ecc71, #27ae60);
      color: #07452e;
      padding: 16px 32px;
      border-radius: 10px;
      text-decoration: none;
      font-weight: 700;
      display: inline-flex;
      align-items: center;
      gap: 10px;
      transition: 0.3s;
    }

    .matricula-btn-primary:hover {
      transform: translateY(-3px);
      box-shadow: 0 10px 25px rgba(46,204,113,0.4);
    }

    .matricula-btn-primary.disabled {
      background: #555;
      color: #999;
      pointer-events: none;
      opacity: 0.6;
    }

    /* RESPONSIVO */
    @media (max-width: 600px) {
      .matricula-header-container {
        flex-direction: column;
        gap: 10px;
      }

      .matricula-logo {
        position: relative;
        left: auto;
        transform: none;
      }

      .matricula-info {
        padding: 25px;
      }
    }
  `;

  return (
    <>
      <style>{styles}</style>

      {/* HEADER */}
      <header className="matricula-header">
        <div className="matricula-header-container">
          <img src="/logo1.png" alt="Logo" className="matricula-logo" />

          <nav className="matricula-nav">
           <nav className="matricula-nav">
            
              <a href="https://emeca.pythonanywhere.com/"className="matricula-btn-nav">  Login</a>
          </nav>
          </nav>
        </div>
      </header>

      {/* CONTEÚDO */}
      <main className="matricula-hero">
        <div className="matricula-info">
          <h2>📢 Importante – Matrícula Online</h2>

          <p>
            A matrícula online <strong>não garante a vaga de imediato</strong>.
            Este sistema serve para agilizar o atendimento.
          </p>

          

          <p>
            ⚠️ Para confirmar a vaga, é necessário comparecer à escola com os documentos exigidos para conferência e realizar a assinatura presencial.
          </p>

          <h3>📄 Documentação</h3>

          <p><strong>Responsáveis (Xerox):</strong></p>
          <ul>
            <li>RG e CPF</li>
            <li>Comprovante de residência</li>
          </ul>

          <p><strong>Aluno (Xerox):</strong></p>
          <ul>
            <li>Certidão de nascimento</li>
            <li>RG e CPF (se possuir)</li>
            <li>Cartão do SUS</li>
          </ul>

          <p><strong>Originais:</strong></p>
          <ul>
            <li>Histórico ou declaração de transferência</li>
          </ul>

          
          

          {/* BOTÃO */}
          <div className="matricula-cta-group">
           
              <Link to="/Matricula" className="matricula-btn-primary">
                Voltar ao Início
                <ArrowRight size={20} />
              </Link>
            
          </div>
        </div>
      </main>
    </>
  );
}

export default DuvidasMatricula;