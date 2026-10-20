# Anexos de imagem e PDF no WhatsApp EMECA

## O que foi implementado

- WhatsApp > Mensagens / Disparos: texto opcional + **uma** imagem (JPG, PNG, WEBP) ou documento PDF, até 25 MB, por envio. Funciona nos modos Individual, Por turma ou Todos. Nenhum grupo compartilhado é criado: o WA-AKG envia a cada número individualmente.
- WhatsApp > Boletins: seleciona um **anexo adicional** que acompanha cada PDF **personalizado** do aluno. São até duas mensagens individuais por item: primeiro o boletim e depois a imagem/PDF complementar, sempre ao mesmo JID previamente validado como contato do aluno.
- WhatsApp > Central de conversas: botões diretos **Imagem** e **PDF** na caixa de resposta. Selecionar arquivo prepara o anexo; o usuário confirma com **Enviar**. Nova conversa também tem seletor de arquivo com legenda.
- Validação de tamanho, extensão e assinatura binária nos formulários de campanhas. Nenhum programa executável é enviado por esses campos.
- Dados de anexos adicionais dos boletins são salvos com nomes opacos e permissões privadas **fora da pasta pública MEDIA_ROOT**, em diretório compartilhado entre web e worker no volume `/data`. São excluídos ao terminar o lote. Registros antigos não são migrados.
- O WA-AKG continua aceitando broadcast só de texto, e agora também recebe multipart para imagem/PDF no mesmo endpoint. Retorna ID de lote; sucesso do endpoint não significa entrega confirmada pelo celular.

## Segurança operacional

- Não houve alteração de número, histórico, tabelas AuthState, credenciais ou banco WA-AKG.
- Não existe repetição automática para PDFs escolares. Se o boletim for aceito mas o anexo falhar, o registro fica com erro explicativo e pede conferência do destinatário para evitar duplicidade.
- A fila de broadcast do WA-AKG fica em segundo plano, como já era para texto. Reiniciar o contêiner durante uma campanha pode interromper envios; o instalador interrompe a atualização caso identifique campanhas ou lotes de boletins em andamento.
- Para envio do PDF principal, o endpoint de mídia do WA-AKG foi atualizado separadamente para confirmação JSON simples e código de erro por etapa; isso ainda exige instalação e teste real. Não afirmar entrega ou funcionamento de mídia apenas por `CONNECTED`.

## Instalação no mini PC

Em horário sem envios:

```bash
cd /srv/projetos/emeca
git pull --ff-only origin main
bash deploy/wa-akg/ativar_anexos_emeca.sh
```

O instalador valida patches, compila imagens, testa Django com imagens novas **antes** do reinício e só troca os contêineres web, whatsapp-worker e wa-akg-app. Não remove volumes, conversa, tabelas ou autenticação. A atualização do WA-AKG provoca breve reconexão.

Para verificar autenticação depois:

```bash
docker compose exec -T web python manage.py shell -c '
from usuarioSec.whatsapp_gateway import obter_sessao
print((obter_sessao().get("data") or {}).get("status"))
'
```

Antes de qualquer campanha real: conferir `CONNECTED`, enviar **uma imagem e um PDF para um destinatário autorizado**, confirmar entrega no aparelho e testar **um boletim com anexo extra**. Não usar "Todos" até receber os três documentos em testes individuais.
