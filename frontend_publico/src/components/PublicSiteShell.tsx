import { useEffect, useState, type ReactNode } from "react";
import { ChevronDown, ClipboardPenLine, Ellipsis, FileText, Gamepad2, GraduationCap, Home, LockKeyhole, Menu, Newspaper, School, UsersRound, X } from "lucide-react";
import "./css/publicSiteShell.css";

type PaginasAtivas = Record<string, boolean>;

type SitePublico = {
  nome_escola: string;
  subtitulo: string;
};

const paginasPadrao: PaginasAtivas = {
  escola: true,
  vida_escolar: true,
  atividades: true,
  projetos: true,
  noticias: true,
  galeria: true,
  matricula: true,
  boletim: true,
  documentos: true,
  faq: true,
  contato: true,
};

export default function PublicSiteShell({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [paginas, setPaginas] = useState<PaginasAtivas>(paginasPadrao);
  const [site, setSite] = useState<SitePublico>({
    nome_escola: "E. M. Egídio Cordeiro Aquino",
    subtitulo: "Educação pública, acolhimento e aprendizagem",
  });
  const logo = `${import.meta.env.BASE_URL}logo_escola.svg`;

  useEffect(() => {
    let ativo = true;

    fetch("/configuracao-site-publica/", { credentials: "same-origin" })
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((data) => {
        if (ativo && data?.paginas) {
          setPaginas({ ...paginasPadrao, ...data.paginas });
        }
        if (ativo && data?.site) {
          setSite({
            nome_escola: data.site.nome_escola || "E. M. Egídio Cordeiro Aquino",
            subtitulo: data.site.subtitulo || "Educação pública, acolhimento e aprendizagem",
          });
        }
      })
      .catch(() => {
        // Mantém a navegação padrão caso a configuração ainda não esteja disponível.
      });

    return () => {
      ativo = false;
    };
  }, []);

  const closeMenu = () => setMenuOpen(false);

  return (
    <div className="school-public-shell">
      <header className="school-public-header">
        <div className="school-public-frame">
          <div className="school-public-header__top">
            <a className="school-public-brand" href="/" onClick={closeMenu}>
              <img src={logo} alt="" />
              <span>
                <strong>{site.nome_escola}</strong>
                <small>{site.subtitulo}</small>
              </span>
            </a>

            <div className="school-public-actions">
              {paginas.boletim && (
                <a className="shell-report" href="/boletim/" onClick={closeMenu}>
                  <FileText size={20} />
                  <span>Boletim</span>
                </a>
              )}

              {paginas.matricula && (
                <a className="shell-enrollment active" href="/matricula-escolar/" onClick={closeMenu}>
                  <ClipboardPenLine size={20} />
                  <span>Matrícula</span>
                </a>
              )}
            </div>
          </div>
        </div>
      </header>

      <div className="school-public-nav-band">
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
          <a className="shell-nav-main" href="/" onClick={closeMenu}><Home /><span>Início</span></a>
          {paginas.escola && <a className="shell-nav-main" href="/a-escola/" onClick={closeMenu}><School /><span>A Escola</span></a>}
          {paginas.vida_escolar && <a className="shell-nav-main" href="/vida-escolar/" onClick={closeMenu}><GraduationCap /><span>Vida Escolar</span></a>}
          {paginas.atividades && <a className="shell-nav-main" href="/atividades-jogos/" onClick={closeMenu}><Gamepad2 /><span>Atividades e Jogos</span></a>}
          {paginas.projetos && <a className="shell-nav-main" href="/projetos/" onClick={closeMenu}><UsersRound /><span>Projetos</span></a>}
          {paginas.noticias && <a className="shell-nav-main" href="/noticias/" onClick={closeMenu}><Newspaper /><span>Notícias</span></a>}

          <details className="school-public-more">
            <summary>
              <Ellipsis />
              <span>Mais</span>
              <ChevronDown size={16} />
            </summary>
            <div className="school-public-more__panel">
              {paginas.galeria && <a href="/galeria/" onClick={closeMenu}>Galeria</a>}
              {paginas.documentos && <a href="/documentos/" onClick={closeMenu}>Documentos</a>}
              {paginas.faq && <a href="/perguntas-frequentes/" onClick={closeMenu}>Perguntas frequentes</a>}
              {paginas.contato && <a href="/contato/" onClick={closeMenu}>Contato</a>}
              <a href="/login/" onClick={closeMenu}><LockKeyhole size={15} /> Área Interna</a>
            </div>
          </details>
        </nav>

        <div className="school-public-nav-accent" aria-hidden="true">
          <span />
          <span />
        </div>
      </div>

      <main className="school-public-content">{children}</main>

      <footer className="school-public-footer">
        <div className="school-public-footer__inner">
          <div className="school-public-footer__brand">
            <img src={logo} alt="" />
            <div>
              <strong>{site.nome_escola}</strong>
              <span>{site.subtitulo}</span>
            </div>
          </div>

          <div className="school-public-footer__links">
            <a href="/">Voltar ao site</a>
            {paginas.contato && <a href="/contato/">Contato</a>}
            <a href="/login/">Área Interna</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
