# Correções WA-AKG para integração EMECA

Este pacote corrige a integração sobre o **WA-AKG já instalado** em
`/srv/projetos/wa-akg`. Não reinstala o WhatsApp, não altera o esquema Prisma,
não modifica as chaves e não apaga sessões/arquivos de mídia.

## Principais alterações

- Captura os pares **LID ↔ telefone (PN)** enviados em contatos, histórico,
  mensagens com `remoteJidAlt` e, quando efetivamente emitido, evento de
  `lid-mapping.update`. Um LID sem PN **não vira um número inventado**.
- Consulta também `sock.signalRepository.lidMapping.getPNForLID`, isto é,
  os mapeamentos já armazenados pelo Baileys na sessão existente. Ao conectar,
  tenta reconciliar os LIDs antigos de contatos e mensagens em lotes limitados,
  sem desconectar nem pedir QR novamente. O resultado aparece nos logs do
  `wa-akg-app`: `LID mappings recovered from existing Signal store`.
- Persiste `phoneNumber`, `lid`, `notify`, `name` e `verifiedName` no banco
  MySQL já utilizado pelo WA-AKG.
- Não usa `pushName` para sobrescrever o nome salvo de um contato.
- Normaliza a lista de conversas com `phoneJid`, `aliases`, `name`,
  `notify`, `profilePic` e última mensagem; une JIDs somente quando
  houver associação explícita. Contatos diferentes nunca são unidos pela foto.
- Habilita `?limit=N&before=ISO_TIMESTAMP` na API de conversas, com
  `meta.nextBefore`; o conector EMECA busca as páginas subsequentes.
- Disponibiliza histórico de mensagens paginado e contatos com
  `displayName`, `aliases` e `phoneJid` normalizados. A interface do EMECA
  ainda exibe inicialmente as mensagens mais recentes; o histórico antigo
  passa a estar disponível para carregamento em páginas.

O WhatsApp/Baileys não garante telefone e lista de contatos para todos os LIDs
nem entrega, necessariamente, todo o histórico anterior à sincronização.

## Implantação no Ubuntu (sem apagar a sessão)

No SSH, a partir da pasta do EMECA:

```bash
cd /srv/projetos/emeca
git pull origin main

# Backup do banco WA-AKG antes do primeiro upgrade de código
mkdir -p /srv/backups/wa-akg
docker compose -f deploy/wa-akg/compose.secure.yaml exec -T db \
  sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction "$MYSQL_DATABASE"' \
  > "/srv/backups/wa-akg/wa-akg-$(date +%Y%m%d-%H%M%S).sql"

# Verificar antes de aplicar (não muda arquivos)
python3 deploy/wa-akg/aplicar_correcoes.py --dry-run

# Backup dos arquivos de código originais + aplicação idempotente
python3 deploy/wa-akg/aplicar_correcoes.py

# Compilar antes de recriar o container em produção
docker compose -f deploy/wa-akg/compose.secure.yaml build app

# Apenas o serviço app do WA-AKG é substituído; db e volumes permanecem
docker compose -f deploy/wa-akg/compose.secure.yaml up -d --no-deps app

# Atualizar conector e testes do EMECA
docker compose up -d --build
docker compose exec -T web python manage.py migrate
docker compose exec -T web python manage.py test usuarioSec.test_whatsapp
docker compose exec -T web python manage.py diagnosticar_contatos_whatsapp

# Consultar somente estatísticas da reconciliação de LIDs (sem expor telefones)
docker logs --tail=250 wa-akg-app 2>&1 | grep 'LID mappings recovered' || true
```

**Atenção:** valide se os contêineres são os esperados antes de implantar. Se
o código-fonte do WA-AKG instalado divergir do repositório analisado, o
aplicador interromperá a execução informando quais marcadores mudaram. Não
force substituição manual sem revisar o diff.

## Desfazer o código

O aplicador cria `/srv/projetos/wa-akg/.emeca-backups/<data>/` com os
arquivos preexistentes que precisaram de alteração. Em caso de falha de build,
o contêiner ativo permanece rodando. Para rollback, restaure os arquivos do
backup mais recente, remova o módulo `emeca-identity.ts` adicionado pelo pacote
e refaça o build somente do serviço `app`. Não restaure credenciais nem
substitua volumes por engano.

## Contrato de API de conversas

`GET /api/chat/{sessionId}?limit=500&before=<ISO>` retorna:
- `data[]`: `jid`, `aliases[]`, `phoneJid` (vazio se não confirmado),
  `name`, `notify`, `profilePic`, `lastMessage`;
- `meta.limit` e `meta.nextBefore` para buscar os itens anteriores.

O endpoint de mensagens aceita `?limit=500&before=<ISO>` e retorna
`meta.hasMore` e `meta.nextBefore`.

O endpoint de contatos continua aceitando `limit=all`. Ele disponibiliza
os dados que o WhatsApp efetivamente sincronizou, não uma lista privada que
não tenha sido compartilhada com o Baileys.
