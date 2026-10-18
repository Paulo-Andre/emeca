# Pacote de atualização única EMECA + WA-AKG

**Estado:** preparado no GitHub; **não executado no mini PC**. Qualquer implantação depende de acesso SSH do administrador e autorização expressa. Não há tarefas em segundo plano no servidor.

## Correções acumuladas para o próximo lote

- Boletins vinculados diretamente aos alunos de **Declarações** sem sobrescrever dados históricos em Matrículas e Histórico.
- Correção do total de faltas pela **coluna H** na planilha escolar, sem somar os detalhamentos; conferência separada de registros antigos.
- PDF do boletim com símbolo da escola e identidade institucional, inclusive para WhatsApp.
- Interface de mensagens WhatsApp responsiva com melhorias de navegação, filtros e acessibilidade.
- Envio de boletins por WhatsApp sempre por ID de Declaração, nunca por homônimos.
- Revalidação de **publicação, vínculo e telefone** imediatamente antes de cada PDF sair da fila, consultando o banco atual e não apenas o cache do lote.
- Respostas com `success:false`, `status:false` ou sem confirmação não podem gerar status `ENVIADO`.
- Timeouts/falhas de envio **não reencaminham automaticamente** documentos: um timeout pode ocorrer depois de a mensagem ter sido aceita. A Secretaria deve revisar individualmente.
- O número de documentos `ENVIADO` no EMECA significa **aceite pela API**, não comprovante de entrega no WhatsApp da família.
- Persistência da desativação do agendador antigo `initScheduler()` do WA-AKG, mesmo após reinstalar o overlay do EMECA. O patcher não substitui alterações locais desconhecidas.
- Novo scheduler reserva agendamentos com atualização atômica `PENDING → PROCESSING` antes de chamar o WhatsApp. Uma interrupção pode deixar `PROCESSING` pendente de revisão; **nunca reativar manualmente como PENDING sem conferir no aparelho e nos registros, pois poderia duplicar o envio**.
- Auditoria QA com Django, cobertura, lint, verificação de segurança, testes sintéticos de concorrência e testes Chromium desktop/celular.

## Como funciona a implantação única segura

O script é `deploy/atualizar_lote_seguro.sh` e substitui o uso irrestrito do antigo `deploy/wa-akg/implantar_emeca.sh`. O instalador antigo agora somente encaminha ao procedimento novo.

**Na futura conexão SSH, após conferir que não existem mudanças locais que devam ser preservadas**:

```bash
cd /srv/projetos/emeca
git status --short
git pull --ff-only origin main

# Somente verificação; não modifica imagens ou banco
bash deploy/atualizar_lote_seguro.sh --preflight
```

A pré-verificação valida `docker compose config` dos dois serviços, versão local, estado dos containers, compatibilidade do patcher WA-AKG e plano de migrações Django. Se indicar divergências, **não force** a instalação nem use `git reset --hard`.

**Somente depois de revisar o resultado, os backups disponíveis, o espaço em disco e o CI do commit correspondente**, um operador pode executar:

```bash
cd /srv/projetos/emeca
EMECA_APLICAR_LOTE=SIM bash deploy/atualizar_lote_seguro.sh --aplicar
```

O procedimento recusa banco EMECA diferente de SQLite, uma vez que seu snapshot incorporado usa a API online `sqlite3.backup`. Se a instância tiver migrado para PostgreSQL, preparar backup específico antes da atualização.

Ele salva:
1. snapshot SQLite verificado por `PRAGMA quick_check`;
2. arquivo compactado de mídias/documentos do EMECA;
3. dump transacional MySQL do WA-AKG;
4. arquivos persistidos nos volumes de mídia e sessão WA-AKG;
5. referências às imagens Docker anteriores e commit do EMECA.

Os arquivos ficam em `/srv/backups/emeca/implantacao-<timestamp>`, com restrição de acesso. **Os backups incluem dados pessoais e mídias escolares/WhatsApp: não envie a terceiros nem os publique em repositórios.** Recomenda-se ainda uma cópia criptografada externa sob política institucional.

Depois dos backups, o script aplica o patcher WA-AKG, compila **ambas** as imagens sem parar a aplicação ativa, atualiza o gateway, pausa temporariamente o worker, atualiza o EMECA com migrações, verifica o Django e só então reinicia o worker. Se uma etapa falhar, interrompe a atualização. Qualquer rollback deve considerar migrações de banco e exigir conferência separada; não se deve restaurar dados cegamente.

## Verificações manuais obrigatórias após implantação

O pacote **não** envia mensagens automaticamente para testar entrega. Homologar com números autorizados e um aluno fictício:
- Login, permissões e operação responsiva no navegador;
- pesquisa/edição completa em Declarações e CPF dos responsáveis;
- Matrícula e Histórico preservados e independentes;
- notas e faltas na coluna H de planilha real, com prévia sem alteração;
- PDF com símbolo e faltas totais, impressão institucional;
- consulta de boletim para a família correta;
- WA-AKG conectado sem misturar contas ou históricos;
- mensagem de teste e anexo, verificação no celular destinatário, leitura e retorno;
- um PDF fictício pela fila, com entrega recebida e checagem do arquivo;
- agendamento controlado, disparo uma única vez e comportamento após reiniciar.
- conferir também agendamentos no estado `PROCESSING`/`FAILED` após queda ou reinicialização; somente reenviar mediante decisão humana, nunca por rotina de recuperação automática.

**Não disparar para todas as famílias antes de concluir a homologação.** Status aceito no gateway não demonstra entrega física. Não reprocessar lotes antigos automaticamente.

## Evidências

- GitHub Actions: https://github.com/Paulo-Andre/emeca/actions
- Relatório QA: `docs/qa-auditoria-integral-2026-10-18.md`
- Regras de identidade: `docs/vinculo-boletins-declaracoes.md`
- Faltas e símbolo: `docs/correcao-faltas-e-simbolo-boletim.md`

**Atenção:** use sempre um commit cujo CI esteja verde antes da implantação. O script não recupera uma aplicação automaticamente se uma migração for interrompida; conserve backups restauráveis e plano de recuperação.
