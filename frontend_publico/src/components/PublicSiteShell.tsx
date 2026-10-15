import { useState, type ReactNode } from "react";
import { ChevronDown, ClipboardPenLine, Ellipsis, Gamepad2, GraduationCap, Home, LockKeyhole, Menu, Newspaper, School, UsersRound, X } from "lucide-react";
import "./css/publicSiteShell.css";

export default function PublicSiteShell({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const logo = `${import.meta.env.BASE_URL}logo_escola.svg`;

  const closeMenu = () => setMenuOpen(false);

  return (
    <div className="school-public-shell">
      <header className="school-public-header">
        <div className="school-public-frame">
          <div className="school-public-header__top">
            <a className="school-public-brand" href="/" onClick={closeMenu}>
              <img src={logo} alt="" />
              <span>
                <strong>E. M. Egídio Cordeiro Aquino</strong>
                <small>Educação pública, acolhimento e aprendizagem</small>
              </span>
            </a>

            <div className="school-public-actions">
              <a className="shell-enrollment active" href="/matricula-escolar/" onClick={closeMenu}>
                <ClipboardPenLine size={20} />
                <span>Matrícula</span>
              </a>

              <span className="shell-action-divider" aria-hidden="true" />

              <a className="shell-internal-access" href="/login/" onClick={closeMenu}>
                <LockKeyhole size={20} />
                <span>Área Interna</span>
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
            </div>
          </div>

          <div className="school-public-nav-band">
            <nav
              id="matricula-menu-principal"
              className={`school-public-nav ${menuOpen ? "is-open" : ""}`}
              aria-label="Menu principal"
            >
              <a className="shell-nav-main" href="/" onClick={closeMenu}><Home /><span>Início</span></a>
              <a className="shell-nav-main" href="/a-escola/" onClick={closeMenu}><School /><span>A Escola</span></a>
              <a className="shell-nav-main" href="/vida-escolar/" onClick={closeMenu}><GraduationCap /><span>Vida Escolar</span></a>
              <a className="shell-nav-main" href="/atividades-jogos/" onClick={closeMenu}><Gamepad2 /><span>Atividades e Jogos</span></a>
              <a className="shell-nav-main" href="/projetos/" onClick={closeMenu}><UsersRound /><span>Projetos</span></a>
              <a className="shell-nav-main" href="/noticias/" onClick={closeMenu}><Newspaper /><span>Notícias</span></a>

              <details className="school-public-more">
                <summary>
                  <Ellipsis />
                  <span>Mais</span>
                  <ChevronDown size={16} />
                </summary>
                <div className="school-public-more__panel">
                  <a href="/galeria/" onClick={closeMenu}>Galeria</a>
                  <a href="/documentos/" onClick={closeMenu}>Documentos</a>
                  <a href="/perguntas-frequentes/" onClick={closeMenu}>Perguntas frequentes</a>
                  <a href="/contato/" onClick={closeMenu}>Contato</a>
                </div>
              </details>
            </nav>

            <div className="school-public-nav-accent" aria-hidden="true">
              <span />
              <span />
            </div>
          </div>
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
