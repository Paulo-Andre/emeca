# Arquitetura unificada — EMECA

O repositório `Paulo-Andre/emeca` passa a ser a base do sistema único.

- **Pais/responsáveis:** frontend público incorporado de `matriculaemeca`, usando a API `/matricula/`.
- **Equipe escolar:** área interna existente do EMECA, protegida por login.
- **Histórico Escolar:** módulo incorporado de `historico_egidio` em `/historico/`, protegido por login.
- **Validação pública:** somente `/historico/validar/<uuid>/` fica acessível sem autenticação.

## Segurança

A integração remove a SECRET_KEY fixa, desativa DEBUG por padrão, elimina
ALLOWED_HOSTS='*' e CORS aberto, adiciona configuração de HTTPS/cookies por
ambiente, mantém auditoria do Histórico e exige senha mínima de 12 caracteres.

## Produção

```env
DJANGO_SECRET_KEY=uma-chave-forte-e-exclusiva
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=seu-dominio.com
DJANGO_SECURE_COOKIES=1
DJANGO_SECURE_SSL_REDIRECT=1
DJANGO_HSTS_SECONDS=31536000
DJANGO_CSRF_TRUSTED_ORIGINS=https://seu-dominio.com
```

Não apague os repositórios antigos até finalizar migração de dados e testes.
