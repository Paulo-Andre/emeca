# EMECA — sistema unificado

Este repositório reúne:

- site público da escola;
- sistema interno da secretaria;
- matrícula pública para pais/responsáveis;
- Histórico Escolar.

## Rotas principais

### Site público

- `/` — página inicial;
- `/a-escola/` — apresentação institucional;
- `/vida-escolar/` — orientações às famílias e estudantes;
- `/atividades-jogos/` — atividades, jogos, quizzes e materiais;
- `/projetos/` — projetos da escola;
- `/noticias/` — notícias;
- `/galeria/` — álbuns de fotos;
- `/matricula-escolar/` — orientações e acesso à matrícula online;
- `/documentos/` — documentos e downloads;
- `/perguntas-frequentes/` — FAQ;
- `/contato/` — contato público.

### Serviços e área interna

- `/login/` — acesso da equipe;
- `/dashboard/` — secretaria;
- `/historico/` — Histórico Escolar autenticado;
- `/matricula-online/` — formulário público;
- `/matricula/` — API pública usada pelo formulário;
- `/historico/validar/<uuid>/` — validação pública de documento;
- `/admin/` — administração de notícias, avisos, carrossel, projetos, atividades, galeria e demais conteúdos.

Fotos e documentos enviados pelo site público ficam persistidos em `/data/media`, no mesmo volume persistente usado pelo container.

## Subir com Docker

```bash
cp .env.example .env
# Edite .env e troque obrigatoriamente as duas chaves.
docker compose up -d --build
```

O banco SQLite fica persistido no volume Docker `emeca_data`.

## Atualizar

```bash
git pull
docker compose up -d --build
```

O container executa automaticamente as migrações e o `collectstatic` antes
de iniciar o Gunicorn.
