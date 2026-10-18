# Plano e relatório QA EMECA — 18/10/2026

## Escopo e limites

Revisão por caixa branca, caixa cinza, segurança, regressão funcional, integridade de dados, acessibilidade/UX, dependências e navegador real. Base: branch `main` do repositório `Paulo-Andre/emeca`. Dados de teste **sempre fictícios**; nenhum WhatsApp real é acionado.

A execução no GitHub verifica a **versão de código**. Ela não valida sozinho o ambiente local `192.168.1.17`, seus dados reais, o WhatsApp efetivamente conectado, entrega de mensagens, backups, latência local ou impressão física. Requer homologação separada sem alterar produção.

## Matriz de testes

| Categoria | Escopo executável | Automação / resultado esperado |
|---|---|---|
| Caixa branca | funções de importação, total H, fórmulas e branch sem H | `site_publico.test_boletim_faltas_logo` |
| Caixa branca | PDF com símbolo fallback, mídia e proporção | `site_publico.test_boletim_faltas_logo` |
| Caixa branca | troca de identidade, homônimos e isolamento Declarações x Matrícula | `site_publico.test_vinculo_declaracao` |
| Caixa branca | correção atômica de faltas pré-importadas e rollback com ambiguidade | `site_publico.test_conferir_faltas_boletim` |
| Caixa branca | unidade de acesso, validações, serviços e regra de negócio | suítes `cadastro`, `secretaria`, `historico`, `usuarioSec`, `site_publico` |
| Caixa cinza | autenticação, perfis isolados, URLs e ausência de exposição de dados | `usuarioSec.test_qa_sistema`, `usuarioSec.test_security` |
| Caixa cinza | WhatsApp com gateway não configurado, UI carregando e API protegida | `usuarioSec.test_qa_sistema` |
| Segurança | CSRF, XSS, IDOR PDF, upload indevido, cabeçalhos HTTP, rate limit | `usuarioSec.test_security` e outras suítes existentes |
| Código | migrações, lint TypeScript, compilação Vite, pip-audit, npm audit, segredos | `.github/workflows/integracao-ci.yml` |
| Cobertura | módulos Python com análise de linhas e XML para download | `coverage report` e artefato `cobertura-emeca` |
| Performance | 240 GETs públicos e 30 POSTs de matrícula fictícia | `scripts/auditoria_carga.py` em runner isolado |
| Usabilidade estática | rótulos, nomes acessíveis, ids duplicados, sem formulários HTML aninhados | `usuarioSec.test_qa_sistema` e `usuarioSec.test_whatsapp_layout` |
| Usabilidade navegador | Chromium real: desktop, celular, conversa, filtro, anexo e retorno | `.github/workflows/qa-navegador.yml` com prints sintéticos |
| Resiliência da interface | falha do CDN de ícones não pode bloquear eventos do WhatsApp | Chromium com requisições externas canceladas |
| Caixa cinza WhatsApp real | reconexão, entrega e recibo, mídia, grupos, status e agendamento | **Pendente: exige instância de homologação e número controlado** |
| Operação local | backup/restauração, acesso HTTPS, fuso, worker, Docker, logs, recuperação após reiniciar | **Pendente: exige acesso à máquina local** |
| UX assistida | leitores de tela, teclado completo, contraste, revisão visual de PDFs oficiais, impressão | **Pendente: demanda revisão humana / dispositivos reais** |

## Defeitos encontrados durante este ciclo

- **QA-001 — Alta:** menu expansível da Secretaria cobria os filtros na tela de mensagens em Chromium desktop, bloqueando o clique. Correção isolada no CSS do inbox; deve ser confirmada por nova execução de navegador.
- **QA-002 — Alta:** páginas WhatsApp iniciavam JS com `lucide.createIcons()` sem testar se CDN carregou. Quando indisponível, falhava o início da interface. Proteção condicional adicionada.
- **QA-003 — Média:** ESLint identificou sete ocorrências de tipagem genérica, interface sem membros e variáveis não utilizadas no frontend da Matrícula. Ajustadas e lint incorporado ao CI.
- **QA-004 — Média:** componentes compartilhados de campos de Matrícula não associavam `label`/entrada via `htmlFor`/id. Corrigido nos componentes reutilizáveis; outros campos manuais ainda precisam auditoria completa.
- **QA-005 — Crítica para entrega:** o WhatsApp pode marcar `SENT` sem prova de entrega no aparelho. **Não declarar resolvido** antes de testes reais controlados.
- **QA-006 — Alta:** PDF e faltas devem ser validados frente ao XLS verdadeiro, não só fixtures sintéticas. O código agora usa H e o PDF inclui símbolo; comparação de registros antigos no mini PC continua pendente.
- **QA-007 — Alta:** atualização do EMECA dispara migrações via entrypoint. Proibido implantar sem backup restaurável e testes de migração; não reiniciar automaticamente com base neste relatório.

## Critérios de aceite

1. GitHub Actions Integração EMECA **verde** no commit de implantação, sem erros lint, migração nem testes.
2. QA Navegador **verde**, desktop e celular, com capturas de dados sintéticos.
3. Rever cobertura e acrescentar testes nos métodos mais críticos e pouco cobertos, sem presumir 100%.
4. Conciliar os boletins antigos com coluna H em prévia e corrigir apenas após backup e identificação inequívoca.
5. Validar PDF da escola em tela e impressão, símbolo e faltas, com um aluno sintético.
6. Testar WhatsApp com somente um número de homologação: conexão, recebimento, confirmação de entrega, anexo e agenda, sem disparo em massa.
7. Simular perda/restauração em ambiente isolado e verificar segregação de contas.
8. Registrar bloqueadores antes de implantar. **Nenhum teste automático comprova ausência total de defeitos.**

## Evidência

- Referência de CI antes do ciclo: https://github.com/Paulo-Andre/emeca/actions/runs/39157412556 — 333 testes aprovados.
- Novas execuções: https://github.com/Paulo-Andre/emeca/actions
- GitHub workflow QA navegador: `.github/workflows/qa-navegador.yml`
- GitHub workflow cobertura e lint: `.github/workflows/integracao-ci.yml`

Após a aprovação, qualquer alteração de aplicação exige nova execução de regressão no commit resultante.
