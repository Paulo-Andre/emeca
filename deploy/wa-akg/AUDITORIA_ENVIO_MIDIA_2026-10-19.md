# Auditoria técnica de mídia WhatsApp EMECA / WA-AKG

Data: 19/10/2026. Escopo: análise estática do fluxo de envio e histórico de logs fornecido pelo administrador, sem acesso SSH ao servidor de produção, sem executar disparos reais.

## Resultado objetivo

**Não há confirmação de correção do envio.** A conta permaneceu `CONNECTED`, mensagens de texto funcionam, mas imagens e PDFs falham em `SEND` com `MEDIA_UPLOAD_ALL_HOSTS` e HTTP 500. A geração de PDF, controle de autorização do EMECA e o transporte multipart não explicam sozinhos essa falha: o código chega a `ChatService.sendMediaMessage()`, que delega a `socket.sendMessage` do Baileys.

## Evidência cronológica fornecida na conversa

1. WA-AKG conectado e mensagens de texto de entrada/saída funcionais, após ajustes de instância/reconexão. Existem logs separados de downloads de mídia criptografada falhos e ocasionais sucessos; **download não comprova a causa de upload**.
2. Boletins individuais: campanhas de 2º trimestre de 2026 registradas como `COM_ERROS`, `0 aceitos`, `1 falha`. PDFs não são retransmitidos automaticamente para evitar duplicidade.
3. API atualizada para retornar `MEDIA_SEND_FAILED, etapa SEND`, eliminando a mensagem genérica `Failed to send media`.
4. Diagnóstico retornou `MEDIA_UPLOAD_ALL_HOSTS, etapa SEND` e **seis** avisos `UNEXPECTED_UPLOAD_RESPONSE` do Baileys.
5. O contêiner resolveu `mmg.whatsapp.net` (IPv4 + IPv6) e recebeu HTTP 404 para um HEAD na raiz. Isso confirma DNS e TLS básicos, mas **não confirma upload autenticado**.
6. Após inserir `HttpsAgent` personalizado para observar respostas, a mesma operação mudou para seis `UNKNOWN_UPLOAD_ERROR`, `resultKind: EMPTY_OR_NON_JSON`, `responseStatus: null`, `hasError: false`, e **nenhum** `WA-MEDIA-HTTP-DIAG`.
7. O último `docker compose` compilou e instalou o observador personalizado, com a sessão `CONNECTED`. A falta de códigos HTTP motivou a retirada desse agente invasivo.

## Varredura do caminho de envio

| Camada | Arquivo/função verificados | Diagnóstico |
| --- | --- | --- |
| Interface EMECA | `usuarioSec/templates/whatsapp.html`, `whatsapp_mensagens.html` | Incluem seletores de PDF/imagem. O erro aparece depois do envio ao gateway. |
| Django | `usuarioSec/whatsapp_views.py` | Valida autorização e anexos; campanhas e boletins têm tratamento distinto. |
| Cliente HTTP | `usuarioSec/whatsapp_gateway.py`: `_request_multipart`, `enviar_documento`, `enviar_midia`, `enviar_broadcast_midia` | Faz POST multipart para WA-AKG; recebeu resposta codificada de erro enviada pelo gateway. |
| Rota WA-AKG | `src/app/api/messages/[sessionId]/[jid]/media/route.ts` | Autentica, lê `formData`, constrói `Buffer`, delega a `ChatService.sendMediaMessage`. O marcador `SEND` comprova o estágio. |
| Serviço WA-AKG | `src/modules/whatsapp/chat.service.ts`: `sendMediaMessage` | Trata `document` e `image`, cria os campos do Baileys, chama `instance.socket.sendMessage`. |
| Instância | `src/modules/whatsapp/instance.ts`, módulo antispam | Estado `CONNECTED`; wrapper de antispam é comum a texto/mídia. Observador anterior alterou `fetchAgent`, potencial regressão. |
| Baileys | `@whiskeysockets/baileys@7.0.0-rc14`: `src/Utils/messages-media.ts` | `getWAUploadToServer` tenta vários hosts. `uploadWithNodeHttp` interpreta JSON e devolve `undefined` se o corpo não for JSON; não preserva status HTTP nesse caminho. |
| Runtime | `Dockerfile` upstream `node:26-alpine`, `compose.secure.yaml` | Rootless Node, redes isoladas e volumes persistentes. DNS/HTTPS básicos aprovados. Não assumir problema de certificado sem código específico. |
| Fila boletins | `usuarioSec/management/commands/processar_envios_whatsapp.py` | Não reenvia automaticamente após resposta ambígua; preserva proteção por JID e valida publicação/declaração. |

## Ponto crítico encontrado nas próprias alterações

O diagnóstico anterior introduziu um `https.Agent` customizado por meio de `fetchAgent` na configuração do Baileys. Essa alteração **não era neutra**, pois modifica o transporte usado para subir a mídia. A mudança de padrão de erro entre a versão anterior e posterior sugere regressão, sem prová-la isoladamente. A correção preparada remove `fetchAgent: mediaFetchAgent` e todo o interceptor `addRequest`.

Foi criado um observador de status usando o evento Node.js `diagnostics_channel` `http.client.response.finish`, somente para POST com `origin=https://web.whatsapp.com` e `content-type=application/octet-stream`. A instrumentação registra **apenas** `httpStatus`; não registra URLs, body, cabeçalhos, arquivos, tokens, JID, número de telefone ou nome de host. O logger sanitizado do Baileys mantém `resultKind`, `responseStatus`, `hasError` e códigos enumerados.

## Entrega de código preparada (NÃO aplicada ao servidor)

- `deploy/wa-akg/aplicar_correcoes.py`: substitui instrumentação HTTPS invasiva pela passiva, e reconhece versões anteriores para não duplicar listeners/agentes.
- `deploy/wa-akg/test_diagnostico_upload.py`: cobre patch original, migração da versão já instrumentada, reaplicação idempotente e recusa de código parcialmente modificado.
- `deploy/wa-akg/testar_http_passivo.cjs`: servidor HTTP de loopback e POST sintético; verifica que a observação captura 403, ignora GET e POST de outras origens, sem WhatsApp real ou acesso à internet. Testado localmente em Node 22: **PASS**.
- `deploy/wa-akg/atualizar_diagnostico_midia.sh`: testa patches, executa o smoke sintético dentro do Node do contêiner, bloqueia atualização com boletins/campanhas em andamento e exige marcador `EMECA_MEDIA_HTTP_PASSIVE_V1` no contêiner atualizado e ausência de `fetchAgent: mediaFetchAgent`.
- `.github/workflows/integracao-ci.yml`: inclui smoke local Node. O resultado da execução do GitHub Actions **não foi confirmado** nesta análise.

**Não instalar às cegas nem retestar com dados escolares.** Antes de publicar no mini PC, o operador deve validar os testes e compilação. A substituição do contêiner interrompe brevemente a conexão e NÃO pode acontecer com lotes ativos. Nunca desconectar, limpar sessão, apagar DB/volumes nem reenviar boletins falhos sem confirmar recebimento no aparelho.

## Próximo diagnóstico necessário, após instalação controlada

Apenas **uma imagem pequena autorizada para o próprio número**, com WhatsApp `CONNECTED`. Recolher exclusivamente:
- `WA-MEDIA-HTTP-DIAG { httpStatus: ... }`
- `WA-MEDIA-UPLOAD-DIAG { reason, resultKind, responseStatus, hasError }`
- `Media send error (sanitized)`

Interpretação dependente dos dados: HTTP 401/403 pode indicar recusa de autorização/token de upload; 404 pode indicar rota/host; 429 limite; 5xx erro remoto; 2xx com resposta sem `direct_path`/`url` indica incompatibilidade de formato/semântica. Não atribuir uma causa final antes de ver os códigos. **Não falsificar resposta de sucesso** nem contornar checks de upload: confirmação exige `messageId` real.

## Outros achados não causais que devem permanecer separados

- Falhas Prisma P2002/P2003 de sincronização do histórico e erros `Failed to download encrypted media` ocorreram em operações diferentes. Podem ser auditados isoladamente, não justificam retransmitir PDFs.
- `src/server/index.ts` contém heartbeat externo de telemetria WA-AKG habilitado por padrão, salvo `ENABLE_TELEMETRY=false` ou `DISABLE_TELEMETRY=true`; revisar privacidade sem confundir com o problema de upload.
- A alteração de perfis RBAC do QA (HTTP 403 em testes de mensagens em massa) corrigiu **teste de autorização**, não upload de mídia.
- A emissão de boletins em massa **deve permanecer suspensa** até sucesso individual comprovado em destinatário autorizado.

## Limites desta auditoria

Foi revisado estaticamente o fluxo relevante e os logs fornecidos; não houve acesso remoto ao mini PC nem execução de testes reais de upload ou build Docker da nova instrumentação. A correção de observabilidade está preparada, mas a causa primária da rejeição do WhatsApp ainda não foi demonstrada. Não alegar “corrigido” antes de uma recepção real.
