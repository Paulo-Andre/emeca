import { useState, type ReactNode } from "react";
import { ChevronDown, ClipboardPenLine, LockKeyhole, Menu, X } from "lucide-react";
import "./css/publicSiteShell.css";

export default function PublicSiteShell({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const logo = `${import.meta.env.BASE_URL}logo_escola.svg`;

  const closeMenu = () => setMenuOpen(false);

  return (
    <div className="school-public-shell">
      <header className="school-public-header">
        <div className="school-public-colors" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>

        <div className="school-public-header__inner">
          <a className="school-public-brand" href="/" onClick={closeMenu}>
            <img src={logo} alt="" />
            <span>
              <strong>E. M. Egídio Cordeiro Aquino</strong>
              <small>Educação pública, acolhimento e aprendizagem</small>
            </span>
          </a>

          <button
            type="button"
            className="shell-menu-button"
            aria-expanded={menuOpen}
            aria-controls="matricula-menu-principal"
            onClick={() => setMenuOpen((value) => !value)}
          >
            {menuOpen ? <X size={19} /> : <Menu size={19} />}
            <span>Menu</span>
          </button>

          <nav
            id="matricula-menu-principal"
            className={`school-public-nav ${menuOpen ? "is-open" : ""}`}
            aria-label="Menu principal"
          >
            <a className="shell-nav-color shell-nav-color--green" href="/" onClick={closeMenu}>Início</a>
            <a className="shell-nav-color shell-nav-color--gold" href="/a-escola/" onClick={closeMenu}>A Escola</a>
            <a className="shell-nav-color shell-nav-color--green-soft" href="/vida-escolar/" onClick={closeMenu}>Vida Escolar</a>
            <a className="shell-nav-color shell-nav-color--gold" href="/atividades-jogos/" onClick={closeMenu}>Atividades e Jogos</a>
            <a className="shell-nav-color shell-nav-color--green" href="/projetos/" onClick={closeMenu}>Projetos</a>
            <a className="shell-nav-color shell-nav-color--red" href="/noticias/" onClick={closeMenu}>Notícias</a>

            <details className="school-public-more">
              <summary>
                Mais
                <ChevronDown size={14} />
              </summary>
              <div className="school-public-more__panel">
                <a href="/galeria/" onClick={closeMenu}>Galeria</a>
                <a href="/documentos/" onClick={closeMenu}>Documentos</a>
                <a href="/perguntas-frequentes/" onClick={closeMenu}>Perguntas frequentes</a>
                <a href="/contato/" onClick={closeMenu}>Contato</a>
              </div>
            </details>

            <a className="shell-enrollment active" href="/matricula-escolar/" onClick={closeMenu}>
              <ClipboardPenLine size={15} />
              Matrícula
            </a>

            <a className="shell-internal-access" href="/login/" onClick={closeMenu}>
              <LockKeyhole size={15} />
              Área Interna
            </a>
          </nav>
        </div>
      </header>

      <main className="school-public-content">{children}</main>

      <footer className="school-public-footer">
        <div className="school-public-footer__inner">
          <div className="school-public-footer__brand">
            <img src={logo} alt="" />
            <div>
              <strong>E. M. Egídio Cordeiro Aquino</strong>
              <span>Secretaria escolar e matrícula online</span>
            </div>
          </div>

          <div className="school-public-footer__links">
            <a href="/">Voltar ao site</a>
            <a href="/contato/">Contato</a>
            <a href="/login/">Área Interna</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
