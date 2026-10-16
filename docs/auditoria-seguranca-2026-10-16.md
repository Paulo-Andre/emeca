# Auditoria de Segurança, Privacidade, Integridade e Desempenho — EMECA

**Data:** 16/10/2026  
**Escopo:** aplicação Django EMECA, frontend público, módulo Histórico, Boletins, Secretaria e integração WhatsApp/WA-AKG.  
**Método:** revisão estática, testes automatizados, testes de segurança, consistência transacional, análise de concorrência, auditoria de dependências e smoke de carga em ambiente CI com dados sintéticos.

> Este documento não contém nomes, CPFs, telefones, tokens ou qualquer dado real de aluno/responsável.

## 1. Resumo executivo

A auditoria identificou falhas relevantes de autorização, CSRF, privacidade de logs/URLs, correlação de identidades e concorrência. As correções de aplicação foram implementadas nesta PR e validadas automaticamente.

A execução CI de referência (run 382) concluiu com sucesso:

- 151 testes Django: **PASSOU**
- Django system check: **PASSOU**
- migrations check: **PASSOU**
- check de produção: **PASSOU** com configuração segura de CI
- scanner de segredos versionados: **PASSOU**
- pip-audit: **0 vulnerabilidades conhecidas**
- npm audit de dependências de produção: **0 vulnerabilidades**
- smoke de carga: **0 erros**
- validação de access log contra conteúdo sintético do corpo: **PASSOU**

Ainda existem riscos que dependem de infraestrutura, governança ou histórico Git e não podem ser considerados resolvidos apenas por código.

## 2. Resultados funcionais e de segurança

| ID | Teste/controle | Resultado | Evidência sanitizada |
|---|---|---|---|
| T01 | Autenticação obrigatória em área interna | PASSOU | usuário anônimo recebe redirecionamento para login |
| T02 | CSRF em exclusão total | PASSOU | POST sem token recebe 403 |
| T03 | Exclusão total via GET | PASSOU após correção | GET recebe 405 e dados permanecem |
| T04 | CSRF na matrícula pública JSON | PASSOU após correção | POST sem CSRF recebe 403 |
| T05 | Payload JSON inválido | PASSOU | endpoint retorna 400, sem 500 |
| T06 | SQL injection em busca | PASSOU | payload sintético não expande resultados; ORM usado |
| T07 | Stored/reflected XSS | PASSOU | HTML sintético é escapado |
| T08 | URL javascript: em conteúdo editável | PASSOU após correção | formulário rejeita esquema inseguro |
| T09 | IDOR/BOLA no PDF do boletim | PASSOU após correção | outra sessão/ID não autorizado recebe 404 |
| T10 | Homônimos no boletim | PASSOU após correção | credenciais de um perfil não autorizam outro |
| T11 | Token sensível em URL do boletim | PASSOU após correção | autorização migrou para sessão server-side |
| T12 | PII em logs de auditoria | PASSOU após correção | chaves sensíveis são [REDACTED] e nome vira referência hash |
| T13 | PII em query string das buscas internas | PASSOU após correção | buscas por aluno migradas para POST |
| T14 | Open redirect na gestão | PASSOU após correção | destino externo não é aceito |
| T15 | Senha fraca no cadastro de usuário | PASSOU após correção | validadores Django são aplicados |
| T16 | Segredos de alta confiança no tree atual | PASSOU | scanner não encontrou chave/token privado versionado |
| T17 | Headers defensivos | PASSOU | CSP, nosniff, CORP, Referrer-Policy e no-store testados |
| T18 | CORS global permissivo | PASSOU | CORS_ALLOW_ALL_ORIGINS=False |
| T19 | Rollback ACID da importação de boletim | PASSOU | falha intermediária não deixa período parcial |
| T20 | Corrida na captura da fila de boletins | PASSOU após correção | claim condicional atômico impede mesmo lote em dois workers |
| T21 | Recuperação do worker | PASSOU | lote recente PROCESSANDO não é resetado por outro worker |
| T22 | Dependências Python runtime | PASSOU | pip-audit: 0 vulnerabilidades conhecidas |
| T23 | Dependências JS runtime | PASSOU | npm audit --omit=dev: 0 vulnerabilidades |
| T24 | Access log e corpo da matrícula | PASSOU | marcadores sintéticos do corpo não apareceram no access log |
| T25 | Build frontend | PASSOU | TypeScript/Vite compilados com sucesso |

## 3. Carga e concorrência

Ambiente: runner Linux de CI, Gunicorn com 2 workers, banco SQLite temporário, dados 100% sintéticos. Estes números servem como baseline técnico, não como benchmark definitivo do mini PC de produção.

| Cenário | Carga | Erros | p50 | p95 | Máximo | Throughput |
|---|---:|---:|---:|---:|---:|---:|
| Home GET | 120 req / 20 concorrentes | 0 | 111,70 ms | 462,14 ms | 551,39 ms | 107,16 req/s |
| Configuração pública GET | 120 / 20 | 0 | 24,79 ms | 30,28 ms | 37,50 ms | 748,14 req/s |
| Matrícula POST | 30 / 10 | 0 | 20,13 ms | 23,05 ms | 23,74 ms | 457,95 req/s |

Conclusão: o smoke concorrente não apresentou erro HTTP nem lock de SQLite nessa carga curta. Isso **não elimina** o limite estrutural do SQLite: há um único escritor por vez e contenção pode surgir em picos prolongados, múltiplos workers ou operações pesadas.

## 4. Vulnerabilidades e riscos

| Severidade | Achado | Estado | Mitigação |
|---|---|---|---|
| **CRÍTICA** | O repositório é público e versões anteriores continham fixture explicitamente derivada de planilha real, incluindo PII de estudante/responsável | **Parcialmente corrigido**: tree atual sanitizado; histórico Git continua recuperável | tornar o repositório privado como contenção; executar rewrite de histórico com git-filter-repo/BFG; force-push coordenado; verificar forks/caches; considerar suporte GitHub para purge; revisar todo histórico antes de republicar |
| **ALTA** | Dados escolares sensíveis ficam em SQLite/volume sem criptografia de aplicação comprovada | Aberto / infraestrutura | criptografia de disco (LUKS), backups criptografados, permissões mínimas e teste periódico de restauração |
| **ALTA** | TLS/HTTPS real do servidor não foi verificável nesta auditoria; .env.example permite flags seguras desligadas para ambiente local | Condicional | em produção: HTTPS obrigatório, SECURE_COOKIES=1, SSL_REDIRECT=1, HSTS, proxy confiável e validação externa |
| **ALTA** | Rate limit do boletim é baseado em sessão e pode ser contornado trocando cookies; login também não possui proteção forte contra brute force | Aberto | rate limiting no reverse proxy + chave por IP/identificador HMAC; django-axes ou equivalente; MFA para usuários internos |
| **ALTA** | Usuário interno autenticado possui acesso amplo; não há RBAC granular consistente entre Secretaria, Histórico, Site, Boletins e WhatsApp | Aberto | grupos/permissões Django e princípio do menor privilégio; testes de matriz de autorização |
| **ALTA** | Dependências npm de desenvolvimento/build reportaram 9 vulnerabilidades altas (além de 3 médias e 1 baixa); runtime enviado ao navegador reportou 0 | Aberto | atualizar devDependencies/lockfile, revisar npm audit fix, usar npm ci e tornar auditoria completa do grafo um gate |
| **ALTA** | Integração WA-AKG usa HTTP interno e endpoint de mídia contém JID/telefone na URL, podendo aparecer nos logs do gateway | Aberto | rede Docker privada/TLS; não publicar porta do WA-AKG; redigir URL de access logs; preferir API que receba destinatário no corpo |
| **MÉDIA** | SQLite tem limite de concorrência de escrita | Aberto | migrar para PostgreSQL/MySQL antes de crescimento de carga; manter testes de concorrência |
| **MÉDIA** | CSP ainda permite unsafe-inline e páginas usam lucide@latest via unpkg | Aberto | self-host/pin de assets, SRI, nonces/hashes e remoção gradual de unsafe-inline |
| **MÉDIA** | Matrícula pública não possui rate limit/bot protection server-side | Aberto | limite por IP, janela temporal, reverse proxy e proteção antiabuso compatível com acessibilidade |
| **MÉDIA** | Uploads de conteúdo público usam principalmente extensão; imagens não têm validação forte de assinatura/magic bytes | Aberto | validar tipo real com Pillow/libmagic, reprocessar imagens no servidor e limitar dimensões |
| **MÉDIA** | Política de retenção/expurgo para mensagens, auditoria e dados pessoais não está formalizada no código | Aberto | política LGPD, prazos de retenção, jobs de expurgo e trilha de aprovação |
| **BAIXA** | Logout ainda é acionável por GET | Aberto | trocar por POST + CSRF |
| **BAIXA** | Dependências Python usam faixas de versão, reduzindo reprodutibilidade perfeita do build | Aberto | lock de dependências com hashes e atualização controlada |

## 5. Correções implementadas nesta auditoria

1. Operações de apagar todas as matrículas/declarações mudadas para POST + CSRF.
2. Senhas passam pelos validadores configurados do Django.
3. JSON inválido retorna erro controlado.
4. Matrícula pública deixou de ser csrf_exempt e o frontend envia X-CSRFToken.
5. Redirect arbitrário em next foi bloqueado.
6. Token do boletim foi retirado da URL e movido para sessão server-side com expiração.
7. IDOR do boletim foi testado e negado por sessão.
8. Correlação de homônimos foi endurecida para impedir mistura de identidades.
9. Logs de auditoria redigem CPF, telefone, senha, token, API key e outros campos.
10. Nomes em objeto_repr de auditoria foram substituídos por referência hash.
11. Buscas internas por nome/matrícula foram movidas de query string para POST.
12. Links editáveis rejeitam javascript: e aceitam apenas caminho interno ou http/https.
13. Worker de boletins usa claim atômico e não reseta lotes ativos recentes.
14. Fixtures derivadas de dados escolares foram substituídas no tree atual por dados sintéticos.
15. CI ganhou scanner sanitizado de segredos, pip-audit, testes de segurança/integridade e smoke de carga.

## 6. Integridade e ACID

As operações críticas revisadas usam transaction.atomic onde necessário. A importação de boletim recebeu teste explícito de rollback: quando a importação falha após criar o período, a transação é revertida e nenhum registro parcial permanece.

O Histórico possui constraints de unicidade para relações ativas e notas por componente. O worker de boletins passou a reivindicar um lote com UPDATE condicional, evitando processamento duplicado por dois workers.

Para carga maior, recomenda-se PostgreSQL/MySQL: o SQLite é transacional e consistente, porém sua serialização de escrita limita escalabilidade e aumenta risco de lock sob carga prolongada.

## 7. Privacidade de tráfego e logs

Após as correções:
- CPF e data de nascimento do boletim são enviados por POST, não entram no link de acesso;
- buscas internas com nome/matrícula usam POST;
- o access log do teste não registrou conteúdo sintético do corpo;
- eventos de auditoria redigem chaves sensíveis;
- API keys do WA-AKG continuam apenas no backend EMECA.

Pendente: proteger também o transporte/log do WA-AKG e validar HTTPS real do servidor.

## 8. Limitações da execução

A auditoria executou código e carga no CI do GitHub, não no mini PC de produção. Portanto, não foram afirmados como validados:
- certificado TLS e cadeia HTTPS real;
- firewall/portas abertas do host;
- criptografia física do disco e backups;
- permissões Unix do volume /data;
- comportamento de memória em soak de horas;
- capacidade máxima do hardware real;
- configuração de logs do WA-AKG/reverse proxy em execução.

Esses itens exigem auditoria no host/staging e não devem ser inferidos apenas pelo repositório.

## 9. Plano de mitigação priorizado

**P0 — imediato:** conter a exposição do histórico Git com PII; tornar privado e reescrever o histórico antes de considerar nova publicação. Validar HTTPS/cookies/HSTS no servidor.

**P1 — curto prazo:** rate limit robusto no login e boletim; RBAC por função; remover vulnerabilidades npm de build; isolar WA-AKG em rede privada e eliminar JID de logs.

**P2 — antes de ampliar uso:** migrar SQLite para PostgreSQL/MySQL, criptografar backups/disco, reforçar uploads e criar testes de restauração.

**P3 — hardening contínuo:** CSP sem unsafe-inline, assets locais/pinados, logout POST, lock de dependências, retenção/expurgo LGPD, soak tests e monitoramento de erro/latência.

## 10. Critério de aceite

A PR pode ser considerada tecnicamente apta para merge quando o CI do commit final permanecer verde. O sistema **não deve ser classificado como plenamente seguro para exposição pública** enquanto o item CRÍTICO de histórico Git, HTTPS real, rate limiting, RBAC e proteção de dados em repouso não forem tratados.
