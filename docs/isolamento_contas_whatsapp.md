# Troca segura de número no WhatsApp institucional do EMECA

## Comportamento atual (exclusão definitiva no servidor)

- **Pausar** interrompe a conexão; não exclui o histórico.
- **Desvincular número** exige confirmação administrativa expressa e
  **apaga permanentemente** os dados locais da sessão desvinculada:
  mensagens, contatos, grupos, etiquetas, agendamentos, mídia armazenada pelo
  WA-AKG e os dados auxiliares desta sessão no EMECA.
- Uma nova sessão de ID aleatório é criada **somente após o WA-AKG confirmar
  a limpeza**. O novo número nunca compartilha o identificador antigo.
- Se o logout ou a limpeza falhar, a sessão fica com
  `limpeza_pendente=True` e o EMECA bloqueia novos QR Codes. O administrador
  pode usar **Finalizar limpeza do histórico** para tentar novamente.
- Desconexões de rede não fazem limpeza; precisam ser tratadas separadamente
  de um logout voluntário.

## Limites

- A limpeza afeta o **servidor EMECA/WA-AKG**, não apaga o histórico do
  aplicativo WhatsApp no Android, backups externos ou cópias dos destinatários.
- Sessões históricas arquivadas antes desta versão não são apagadas
  automaticamente. Faça uma auditoria dos identificadores antigos e tenha
  autorização explícita antes de excluir cada sessão legada.
- Se o banco confirmar a exclusão mas arquivos de mídia não puderem ser
  removidos, o sistema exibirá aviso para limpeza de armazenamento manual.
- A exclusão definitiva pode afetar registros administrativos relevantes;
  confira as obrigações de retenção da escola antes de executar.

## Atualizar aplicativo e gateway juntos

No mini PC, a partir da pasta do EMECA:

```bash
cd /srv/projetos/emeca
git pull origin main

# Backup consistente SQLite + MySQL antes da atualização.
bash deploy/wa-akg/backup_antes_isolamento.sh

# Faz outro backup MySQL, aplica os overlays do WA-AKG, compila,
# atualiza os contêineres e roda os testes de integração Django.
bash deploy/wa-akg/implantar_emeca.sh
```

O script de implantação instala:
- sincronização de contatos, nomes e LID/telefone;
- listagem de grupos recém-criados antes de sua primeira mensagem;
- agendador corrigido para usar o identificador público da sessão;
- rota de exclusão definitiva de uma sessão **somente após LOGGED_OUT**.

Se o script `aplicar_correcoes.py` detectar código WA-AKG editado
localmente, ele interrompe a instalação sem sobrescrever essas edições.
Neste caso, envie apenas o erro e um diff sem dados sensíveis para revisão.

**Não compartilhe** senhas, `.env`, chaves de API, arquivos de autenticação
ou mensagens privadas. Os backups anteriores continuam existindo no disco
até serem eliminados de acordo com a política de retenção da escola.
