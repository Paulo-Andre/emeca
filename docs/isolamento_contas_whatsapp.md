# Correção da mistura de conversas entre contas do WhatsApp

## Problema identificado

O EMECA antigo usava o `WA_AKG_SESSION_ID` fixo do arquivo `.env`
(`emeca-secretaria`). A ação `logout` do WA-AKG apaga credenciais
de autenticação, mas **não** apaga `Session`, `Message`, `Contact`
nem `Group`. Ao ler um segundo QR Code usando o mesmo `sessionId`,
mensagens dos números diferentes passam a compartilhar a mesma FK MySQL.

**Não tente apagar ou reatribuir mensagens de maneira automática.**
Se o histórico já foi misturado, nem sempre há metadados suficientes para
atribuir retrospectivamente cada mensagem à conta correta.

## Solução

- Cada troca confirmada de conta cria um ID WA-AKG exclusivo e persistente
  em `SessaoWhatsAppAtiva`; o antigo `WA_AKG_SESSION_ID` é apenas a
  identificação inicial/legada.
- A nova sessão recebe novos registros `Session`, `Contact`, `Message`
  e `Group` no WA-AKG; o histórico anterior continua intocado na sessão
  original, agora arquivada.
- Identificações manuais, agenda importada, cache LID, estados de conversa
  e leitura/não lidas são consultados somente para a sessão ativa.
- Abas de conversa antigas enviam o cabeçalho `X-EMECA-WA-SESSION`.
  Após troca do número, o servidor recusa operações com identidade antiga
  (HTTP 409). Formulários de envios e conexão também levam `wa_session_id`.
- A fila de boletins recebe o ID de sessão quando o lote é criado. O worker
  só assume lotes da sessão ativa; mídias do lote usam sempre o ID de origem.
  Portanto, boletins pendentes da conta anterior não são enviados pela nova.
- `Pausar` continua preservando o vínculo para retomar o mesmo número.
  `Desvincular` ou `Separar conta atual` realiza logout e altera a
  sessão ativa, exigindo uma nova leitura de QR Code.

## Implantação

**Antes de atualizar, evite envios no EMECA até separar a conta atual.**
Faça backup do banco do EMECA e do banco MySQL do WA-AKG.

```bash
cd /srv/projetos/emeca

# Backup SQLite do EMECA: cópia consistente pela API do próprio SQLite
mkdir -p /srv/backups/emeca
docker compose exec -T web python -c 'import sqlite3; s=sqlite3.connect("/data/emeca.sqlite3"); d=sqlite3.connect("/backups/emeca/antes-isolamento-wa.sqlite3"); s.backup(d); d.close(); s.close()'

# Backup MySQL do WA-AKG (ajuste env se necessário)
# Executar a partir da pasta emeca; usando o compose seguro e seu .env WA-AKG.
docker compose -f deploy/wa-akg/compose.secure.yaml exec -T db sh -c \
  'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction "$MYSQL_DATABASE"' \
  > "/srv/backups/emeca/wa-akg-antes-isolamento-$(date +%Y%m%d-%H%M%S).sql"

git pull origin main
docker compose up -d --build
docker compose exec -T web python manage.py migrate
docker compose exec -T web python manage.py test \
  usuarioSec.test_isolamento_contas_whatsapp \
  usuarioSec.test_whatsapp
```

Atenção: os backups anteriores são exemplos para a instalação SQLite do
EMECA e MySQL do WA-AKG. Confira que foram criados e possuem conteúdo antes
de fazer qualquer troca. O backup SQLite é salvo no volume montado em
`/srv/backups/emeca`.

### Para a conta atual que já foi misturada

1. Entre no EMECA como administrador e abra **WhatsApp da Secretaria**.
2. Clique **Separar conta atual**, leia o aviso e confirme.
3. A sessão atual será desvinculada. Os registros já misturados permanecem
   na sessão original como acervo histórico, sem exclusão.
4. Clique **Conectar WhatsApp** e leia o QR Code **com o WhatsApp que deseja
   usar na escola**.
5. Aguarde a sincronização inicial e abra **Mensagens**. As conversas devem
   vir apenas da nova sessão.
6. Atualize outras abas abertas no EMECA; as anteriores perderão a permissão
   de usar a nova sessão.

### Trocas futuras

Use **Desvincular número**, não apenas `Pausar`, antes de conectar uma
conta diferente. O sistema gera a sessão exclusiva automaticamente.

## Diagnóstico em caso de falhas

```bash
cd /srv/projetos/emeca
docker compose exec -T web python manage.py showmigrations usuarioSec
docker compose exec -T web python manage.py test usuarioSec.test_isolamento_contas_whatsapp
docker compose logs --tail=120 web whatsapp-worker
```

Não poste `.env`, arquivos de autenticação, tokens nem conteúdo de
conversas; remova números completos de capturas de logs compartilhadas.
