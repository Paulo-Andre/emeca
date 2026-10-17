# Auditoria de recursos WA-AKG → EMECA

Data: 2026-10-17

## Escopo analisado

Foi revisada a árvore completa de APIs do WA-AKG 1.6.x e as páginas do dashboard do projeto upstream. O WA-AKG expõe 81 rotas de API, distribuídas entre sessões, conversas, contatos, mensagens, mídia, grupos, etiquetas, agendamentos, respostas automáticas, perfil, notificações, webhooks, usuários e monitoramento.

## Recursos de atendimento incorporados ao EMECA

### Sessão e conexão
- status da sessão;
- iniciar sessão;
- QR Code;
- sessão persistente no servidor.

### Conversas
- lista de conversas;
- resolução de JID, LID e número real;
- nome do contato pelo WA-AKG, pushName ou base escolar;
- tentativa de foto por todos os aliases conhecidos;
- abrir histórico usando todos os aliases do contato;
- marcar como lida;
- fixar;
- silenciar;
- arquivar;
- bloquear/desbloquear;
- indicador de digitando/pausado;
- atualização automática;
- busca local de conversa;
- busca de mensagens no histórico.

### Mensagens
- enviar texto;
- iniciar nova conversa;
- pesquisar contato por nome ou telefone;
- validar telefone no WhatsApp;
- responder mensagem específica com citação;
- reagir com emoji;
- favoritar mensagem;
- editar mensagem enviada;
- apagar mensagem enviada;
- encaminhar mensagem;
- status/timestamp de mensagens;
- envio individual direto;
- broadcast para múltiplos destinatários.

### Mídia
- enviar imagem;
- enviar vídeo;
- enviar áudio;
- enviar documento;
- legenda de mídia;
- limite de 25 MB no EMECA;
- bloqueio de extensões executáveis;
- exibição/stream de imagem, vídeo e áudio recebidos;
- abertura/download de documentos recebidos via proxy autenticado do EMECA.

### Organização e automação
- etiquetas;
- aplicar/remover etiquetas por conversa;
- respostas automáticas;
- mensagens agendadas;
- histórico de agendamentos;
- grupos: listagem e criação;
- ajuste do fuso horário usado pelo agendador.

## Recursos do WA-AKG mantidos no painel técnico do gateway

Os itens abaixo pertencem à administração da infraestrutura e não foram duplicados na interface operacional da secretaria:

- API Keys;
- documentação Swagger/API Docs;
- usuários internos do WA-AKG e permissões de sessão;
- webhooks técnicos e logs de webhook;
- monitor de sistema;
- atualização do software;
- configurações globais de branding do gateway;
- gerenciamento técnico de sessões múltiplas;
- bot settings avançados;
- configurações de perfil do próprio número;
- administração completa de membros/configurações de grupos;
- sticker manager dedicado.

Esses recursos continuam disponíveis no painel WA-AKG para o administrador do servidor. O EMECA consome apenas a sessão institucional configurada em WA_AKG_SESSION_ID.

## Diferenças importantes corrigidas

1. Conversas podem chegar do WhatsApp usando `@lid` em vez do JID baseado em telefone. O EMECA agora tenta todos os aliases do mesmo contato ao abrir histórico, foto e nome.
2. A API de chat por JID exato não é suficiente para contatos migrados para LID. O EMECA agrega mensagens encontradas pelos aliases e remove duplicadas.
3. Fotos podem não estar no registro Contact. O EMECA consulta também o endpoint de foto de perfil.
4. Quando o WA-AKG não conhece o nome, o EMECA usa `pushName` das mensagens e, por último, tenta relacionar o telefone à base escolar.
5. O agendador do WA-AKG usa o fuso configurado no próprio gateway. A tela de gerenciamento permite ajustar para `America/Sao_Paulo`.
6. Mídia recebida não é exposta diretamente ao navegador pela rede privada: o EMECA atua como proxy autenticado.

## Segurança

- a API Key do WA-AKG permanece somente no backend;
- o navegador nunca recebe a chave;
- endpoints operacionais exigem usuário autenticado no EMECA;
- mídia recebida passa por endpoint autenticado do EMECA;
- anexos executáveis são bloqueados;
- upload limitado a 25 MB;
- conteúdo textual recebido é inserido com textContent no navegador para evitar HTML injetado;
- MySQL do WA-AKG permanece sem porta publicada para a rede local;
- WA-AKG continua acessível apenas pela rede privada/localhost conforme o compose seguro.
