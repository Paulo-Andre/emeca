# EMECA — sistema unificado

Este repositório reúne:

- sistema interno da secretaria;
- matrícula pública para pais/responsáveis;
- Histórico Escolar.

## Rotas principais

- `/login/` — acesso da equipe;
- `/dashboard/` — secretaria;
- `/historico/` — Histórico Escolar autenticado;
- `/matricula-online/` — formulário público;
- `/matricula/` — API pública usada pelo formulário;
- `/historico/validar/<uuid>/` — validação pública de documento.

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
