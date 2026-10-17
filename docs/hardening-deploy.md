# Implantação do hardening de segurança do EMECA

Este guia pressupõe o projeto em `/srv/projetos/emeca` e o WA-AKG em
`/srv/projetos/wa-akg`.

## 1. Antes da atualização

Faça uma cópia do banco e do arquivo de configuração atual antes de alterar o
serviço. Não envie o arquivo `.env` para Git, e-mail ou chat.

```bash
cd /srv/projetos/emeca
mkdir -p /srv/backups/emeca
chmod 700 /srv/backups/emeca
cp .env /srv/backups/emeca/env-pre-hardening-$(date +%Y%m%d-%H%M).bak
chmod 600 /srv/backups/emeca/env-pre-hardening-*.bak
```

Se o banco atual for SQLite, faça também uma cópia inicial antes do rebuild.

## 2. Atualizar o código

```bash
cd /srv/projetos/emeca
git pull origin main
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose ps
```

A migração cria os perfis de acesso. Para evitar bloqueio, usuários internos
já existentes recebem inicialmente o perfil **Administração**. Depois, use
**Gerenciar acessos** para aplicar o princípio do menor privilégio.

## 3. Rate limiting

Os valores seguros já possuem defaults. Eles podem ser ajustados no `.env`:

```env
DJANGO_RBAC_STRICT=1
DJANGO_RATE_LIMIT_ENABLED=1
DJANGO_LOGIN_RATE_ACCOUNT=8
DJANGO_LOGIN_RATE_IP=30
DJANGO_LOGIN_RATE_WINDOW=900
DJANGO_BOLETIM_RATE_IP=10
DJANGO_BOLETIM_RATE_WINDOW=900
DJANGO_MATRICULA_RATE_IP=30
DJANGO_MATRICULA_RATE_WINDOW=3600
DJANGO_CONTATO_RATE_IP=20
DJANGO_CONTATO_RATE_WINDOW=900
```

Ative `DJANGO_TRUST_PROXY_HEADERS=1` apenas quando o EMECA estiver atrás de
um proxy controlado, como Cloudflare/Nginx configurado por você.

## 4. HTTPS de produção

Quando houver domínio HTTPS real, ajuste:

```env
DJANGO_DEBUG=0
DJANGO_SECURE_COOKIES=1
DJANGO_SECURE_SSL_REDIRECT=1
DJANGO_HSTS_SECONDS=31536000
DJANGO_HSTS_PRELOAD=0
DJANGO_TRUST_PROXY_HEADERS=1
DJANGO_REQUIRE_SECURE_PRODUCTION=1
DJANGO_ALLOWED_HOSTS=SEU_DOMINIO
DJANGO_CSRF_TRUSTED_ORIGINS=https://SEU_DOMINIO
```

Não ative `DJANGO_REQUIRE_SECURE_PRODUCTION=1` antes do HTTPS estar
funcionando, porque o EMECA recusará inicialização com configuração insegura.

## 5. WA-AKG isolado

O EMECA cria a rede Docker `emeca_private`. Depois, no WA-AKG:

```bash
cd /srv/projetos/emeca
docker compose up -d

cd /srv/projetos/emeca/deploy/wa-akg
cp .env.example .env
chmod 600 .env
# Edite as senhas e AUTH_SECRET antes de continuar.
docker compose --env-file .env -f compose.secure.yaml up -d --build
```

No `.env` do EMECA:

```env
WA_AKG_BASE_URL=http://wa-akg-app:3000/api
```

O MySQL do WA-AKG não fica publicado no host. A interface WA-AKG fica
limitada a `127.0.0.1:3100`; publique-a externamente somente por proxy seguro
se realmente necessário.

## 6. Backup criptografado

Crie o arquivo secreto fora do repositório:

```bash
sudo mkdir -p /etc/emeca
sudo cp /srv/projetos/emeca/deploy/systemd/backup.env.example /etc/emeca/backup.env
sudo chmod 600 /etc/emeca/backup.env
sudo nano /etc/emeca/backup.env
```

Gere uma chave forte, guarde uma cópia em local seguro e coloque-a em
`EMECA_BACKUP_PASSPHRASE`.

Instale o timer:

```bash
sudo cp /srv/projetos/emeca/deploy/systemd/emeca-backup.service /etc/systemd/system/
sudo cp /srv/projetos/emeca/deploy/systemd/emeca-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now emeca-backup.timer
sudo systemctl start emeca-backup.service
sudo systemctl status emeca-backup.service --no-pager
ls -lh /srv/backups/emeca
```

Um backup não é considerado validado até que uma restauração de teste seja
realizada.

## 7. Expurgo de dados operacionais

O comando não apaga matrículas, históricos, notas ou boletins escolares. Ele
atua somente sobre dados operacionais com prazo de retenção configurado.

Teste primeiro:

```bash
cd /srv/projetos/emeca
docker compose exec web python manage.py expurgar_dados_operacionais --dry-run
```

Depois instale o timer:

```bash
sudo cp deploy/systemd/emeca-expurgo.service /etc/systemd/system/
sudo cp deploy/systemd/emeca-expurgo.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now emeca-expurgo.timer
```

## 8. PostgreSQL opcional

A instalação existente continua em SQLite por padrão. PostgreSQL pode ser
ativado posteriormente com o arquivo `compose.postgres.yaml`. Não faça a
troca do banco sem uma janela de manutenção, backup validado e teste de
restauração/migração.

## 9. Verificações após implantação

```bash
cd /srv/projetos/emeca
docker compose ps
docker compose exec web python manage.py check --deploy
docker compose exec web python manage.py showmigrations
docker compose logs --tail=100 web whatsapp-worker
```

Confirme também:
- usuário de Secretaria não acessa Histórico/Site quando esses módulos não
  estiverem concedidos;
- tentativas repetidas de login recebem HTTP 429;
- boletins continuam acessíveis apenas após validação do responsável;
- o WhatsApp permanece conectado após logout do usuário EMECA;
- uploads falsos com extensão de imagem/documento são rejeitados;
- o backup criptografado é gerado e pode ser restaurado em ambiente de teste.
