# Auditoria técnica — boletins PDF pelo WhatsApp EMECA
Data: 19/10/2026

## Evidências do histórico e da execução

- O EMECA informou duas tentativas individuais (1 PDF cada) com **0 aceitos e 1 falha**, exibidas em 19/10 às 19h37. O motivo registrado no banco foi `Failed to send media`.
- O WA-AKG voltou a `CONNECTED` após a correção de reconexão e o usuário confirmou **envio e recebimento de mensagens comuns**. Portanto, autenticação e envio de texto funcionam; não prova envio de arquivos.
- Registros antigos de `P2002/P2003` no Prisma se referem à persistência/sincronização de mensagens, tratada em patch próprio. Logs antigos de `Failed to download encrypted media` descrevem **download** de mídias históricas, não o envio dos PDFs. Não podem ser usados como causa comprovada deste problema.
- NÃO foi disponibilizado o stack trace do WA-AKG referente ao envio de PDF das 19h37. A causa definitiva do `sendMessage(document)` ainda não está comprovada.
- Sem SSH no mini PC, não é possível confirmar quais linhas o contêiner produziu naquela tentativa, rodar testes reais ou declarar que o problema está resolvido na produção.

## Caminho revisado no código

1. `usuarioSec/whatsapp_views.py`: cria lote individual preservando a sessão e só aceita status conectado.
2. `usuarioSec/management/commands/processar_envios_whatsapp.py`: reconfirma o vínculo do destinatário, gera PDF ReportLab em memória, envia uma vez, marca `ENVIADO` apenas quando o gateway confirma; em falha/timeout não reenvia automaticamente.
3. `usuarioSec/whatsapp_gateway.py`: `enviar_documento` constrói multipart com `file`, `type=document`, `caption`, MIME `application/pdf`, endpoint `messages/{sessionId}/{jid}/media`. Compatível com a rota analisada do WA-AKG.
4. `src/app/api/messages/[sessionId]/[jid]/media/route.ts` no WA-AKG: aceita FormData, chama `ChatService.sendMediaMessage` e antes devolvia o objeto `sent` inteiro com `NextResponse.json`. Qualquer exceção, inclusive eventual erro de serialização após sucesso do envio, retornava HTTP 500 com `Failed to send media`.
5. `src/modules/whatsapp/chat.service.ts`: usa `instance.socket.sendMessage(jid, { document: buffer, mimetype, fileName, caption })`. Não foi encontrada conversão indevida do PDF para string nesse caminho.

## Correções preparadas e versionadas

- `deploy/wa-akg/aplicar_correcoes.py`: modifica a rota de mídia para retornar somente `data.messageId`, que é JSON seguro, sem devolver o protobuf do Baileys. Evita falso HTTP 500 de confirmação após envio.
- Adiciona identificação de fase (`AUTH`, `MULTIPART`, `BUFFER`, `SEND`, `ACK`) e código de falha sanitizado, sem imprimir anexos, nomes, telefones, números de documento ou chave API.
- Se houver exceção na chamada ao Baileys, o worker continuará SEM qualquer reenvio automático: a Secretaria precisará verificar se o destinatário recebeu antes de uma nova tentativa.
- `deploy/wa-akg/test_corrigir_midia.py`: testes de idempotência, proteção a versões desconhecidas, marcador de uma única chamada ao serviço de envio e erros/etapas.
- `usuarioSec/test_gateway_media_qa.py`: testes sintéticos de multipart, URL, MIME, resposta positiva e tratamento de 500 sem reenvio.
- Workflow `.github/workflows/integracao-ci.yml` foi alterado para executar os testes de patch. O resultado final da execução de CI ainda precisa ser verificado.

## Limites e próximos passos

Os patches **estão no GitHub, não instalados no mini PC**, a menos que alguém faça o deploy depois deste relatório. O envio de PDF ainda NÃO foi validado em dispositivo real.

Ao retornar:

```bash
cd /srv/projetos/emeca
git pull --ff-only origin main
python3 -m unittest discover -s deploy/wa-akg -p 'test_*.py' -v
python3 deploy/wa-akg/aplicar_correcoes.py --dry-run
```

Inspecionar o diff e o retorno dos testes antes de alterar o WA-AKG ativo. Para instalação, aplicar patch, compilar o serviço `app` e substituir apenas o contêiner `wa-akg-app`; **não alterar o banco, volumes ou credenciais, nem excluir histórico**. O restart da aplicação implica desconexão temporária e merece horário com baixo tráfego. O `docker compose` do WA-AKG **não exige migração** para esse patch.

Após instalação, verificar status `CONNECTED`, escolher **um único boletim de teste e destinatário autorizado**, checar recepção e inspecionar o campo de estágio caso haja nova falha. Não emitir para turma/todos antes de teste individual recebido. Verificar eventual duplicidade antes de enviar nova tentativa.
