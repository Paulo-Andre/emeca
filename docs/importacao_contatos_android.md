# Importação em massa da agenda Android — EMECA

## Objetivo

Importar, com segurança, os contatos da agenda do celular institucional
(Android) para a lista de conversas da Secretaria Escolar.

O EMECA não faz upload do arquivo VCF para o WA-AKG, não envia contatos ao
WhatsApp e não altera qualquer mensagem. Os contatos ficam em uma tabela
própria do banco do EMECA, relacionados à sessão do WhatsApp pelo número
completo com DDD.

## Como exportar do Android

1. Abra o aplicativo **Contatos** do celular institucional.
2. Procure **Corrigir e gerenciar** ou **Organizar > Exportar**, conforme o
   aplicativo e a marca do aparelho.
3. Exporte os contatos para um arquivo **.vcf** (vCard).
4. Transfira esse arquivo para o computador que acessa o EMECA.
5. No EMECA, entre com usuário **administrador**, abra **WhatsApp >
   Gerenciamento > Importar contatos**.
6. Selecione o VCF (até 8 MB), clique em **Conferir arquivo** e revise a
   contagem de telefones, a amostra e os conflitos.
7. Clique em **Confirmar importação**. A operação é repetível com
   segurança: números já importados não serão duplicados nem sobrescritos.
8. Retorne a **Mensagens** e atualize o navegador (Ctrl+Shift+R).

## O que acontece

- Somente números brasileiros com DDD e tamanho plausível são aceitos;
  o código 55 é normalizado automaticamente se ausente.
- Um contato com dois números gera dois registros, cada um com o mesmo nome.
- Números duplicados com o **mesmo nome** são gravados uma única vez.
- Se o arquivo atribuir nomes **diferentes** ao mesmo número, esse número
  é ignorado, e a contagem de conflitos aparece na prévia.
- Nomes já presentes na agenda EMECA são preservados na reimportação.
- Na lista de chats, um nome definido manualmente no EMECA tem prioridade;
  depois vem o nome da agenda Android importada, seguido dos dados do
  WhatsApp e do cadastro escolar existente.
- Um identificador `@lid` só recebe o nome da agenda quando o WA-AKG
  confirmou o telefone associado. O VCF, isoladamente, não descobre um PN
  desconhecido nem deve mesclar conversas por nome/foto.

## Privacidade e segurança

- A página e a API de importação só aceitam usuários `is_staff`.
- Arquivos VCF não são armazenados como anexos; são processados durante a
  requisição HTTPS/HTTP autenticada.
- A própria agenda importada contém dados pessoais: mantenha os backups
  do EMECA e o computador protegidos. Prefira HTTPS quando houver acesso
  fora da rede local.
- A importação é somente aditiva. Não apaga registros anteriores, não
  envia mensagens e não modifica sessão, mídia ou mensagens do WA-AKG.
- Se o WhatsApp institucional usar outra sessão no futuro, a agenda
  permanecerá isolada na sessão original.

## Implantação / testes

```bash
cd /srv/projetos/emeca
git pull origin main
docker compose up -d --build
docker compose exec -T web python manage.py migrate
docker compose exec -T web python manage.py test usuarioSec.test_agenda_android usuarioSec.test_whatsapp
```

A rota da página é `/whatsapp/importar-contatos/`.

O VCF não atualiza automaticamente a agenda do Android: se novos contatos
forem salvos depois, será necessário exportar/importar novamente. Contatos
com apenas LID continuam dependendo de um vínculo real LID↔telefone
oferecido pelo WhatsApp/Baileys ou de confirmação manual do operador.
