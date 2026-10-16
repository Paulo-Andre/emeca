# Integração do EMECA com WhatsApp via WA-AKG

Esta integração mantém o **EMECA (Django)** e o **WA-AKG (Next.js/Baileys)** como serviços separados.

## Arquitetura

- EMECA continua na porta 8000.
- WA-AKG pode ser publicado no host na porta 3100.
- O banco do WA-AKG é próprio (MySQL/PostgreSQL) e não se mistura ao banco escolar.
- O EMECA conversa com o WA-AKG apenas pela API HTTP autenticada com `X-API-Key`.
- A chave da API fica somente no `.env` do servidor.

## 1. Instalar o WA-AKG em uma pasta separada

Exemplo:

```bash
cd /srv/projetos
git clone https://github.com/mrifqidaffaaditya/WA-AKG.git wa-akg
cd wa-akg
cp .env.example .env
```

Configure no `.env` do WA-AKG pelo menos:

- `MYSQL_ROOT_PASSWORD`
- `MYSQL_DATABASE=wa_akg`
- `AUTH_SECRET`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`
- `TZ=America/Sao_Paulo`
- `LOCALE=pt-BR`

## 2. Publicar o WA-AKG em uma porta própria

No `docker-compose.yml` do WA-AKG, prefira não expor o MySQL para a rede externa e publique somente a aplicação:

```yaml
services:
  db:
    # mantenha 3306 apenas dentro da rede Docker;
    # remova o bloco ports se não precisar acessar o MySQL pelo host.

  app:
    ports:
      - "3100:3000"
```

Depois:

```bash
docker compose up -d --build
docker compose ps
```

## 3. Criar a chave da API

Entre no painel do WA-AKG com a conta administrativa criada na instalação.

Em **Settings → API Keys**, gere uma chave de API. Não coloque essa chave em HTML, JavaScript ou repositório Git.

## 4. Configurar o EMECA

No `.env` do EMECA:

```env
WA_AKG_BASE_URL=http://host.docker.internal:3100/api
WA_AKG_API_KEY=COLE_AQUI_A_CHAVE_GERADA_NO_WA_AKG
WA_AKG_SESSION_ID=emeca-secretaria
WA_AKG_TIMEOUT_SECONDS=8
WA_AKG_BROADCAST_DELAY_MS=10000
```

O `docker-compose.yml` do EMECA já inclui:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

Isso permite que o container Django alcance o WA-AKG publicado no próprio servidor.

Recrie o EMECA:

```bash
cd /srv/projetos/emeca
docker compose up -d --build
```

## 5. Vincular o número institucional

No EMECA:

1. entre com um usuário autenticado da Secretaria;
2. abra **WhatsApp**;
3. clique em **Iniciar conexão**;
4. clique em **Exibir QR**;
5. no celular institucional, abra **WhatsApp → Aparelhos conectados → Conectar aparelho**;
6. leia o QR Code.

Quando o status ficar **CONNECTED**, os disparos são habilitados.

## Destinatários disponíveis

A tela do EMECA usa os telefones já importados em `TelefoneDeclaracao` e os vínculos existentes com `declaracao`:

- **Todos**: reúne Pai, Mãe e/ou Responsável de todos os alunos;
- **Por turma**: filtra por `turmaDoAluno`;
- **Individual**: pesquisa aluno/responsável e permite escolher um telefone específico.

O sistema:

- remove números duplicados;
- aceita números brasileiros com DDD, com ou sem `+55`;
- ignora números sem DDD ou inválidos;
- mostra a quantidade antes do envio;
- exige confirmação antes de disparos;
- envia conversas individuais (os pais não veem os demais destinatários).

## Segurança e uso responsável

O WA-AKG usa **Baileys**, uma integração não oficial do WhatsApp. Não existe garantia contra bloqueios ou mudanças no protocolo do WhatsApp.

Para uso escolar:

- use um número institucional dedicado;
- mantenha intervalos conservadores entre mensagens;
- evite disparos promocionais ou excessivos;
- envie somente informações necessárias aos responsáveis;
- não inclua dados sensíveis de alunos em mensagens em massa;
- restrinja a chave da API e o painel do WA-AKG aos administradores.
