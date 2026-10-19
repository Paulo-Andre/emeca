#!/usr/bin/env bash
# Instala a reconciliação de CPFs e aplica APENAS correspondências comprovadas.
# Acionado pelo instalador Windows. Não reinicia nem modifica WA-AKG.
set -Eeuo pipefail
umask 077
ETAPA="início"
trap 'echo "FALHA na etapa: $ETAPA. Boletins não foram publicados. Verifique a saída acima." >&2' ERR

cd /srv/projetos/emeca
ARQUIVO="/srv/backups/emeca/conferencia-boletins/declaracoes-cpfs-oficial.xls"
ARQUIVO_CONTAINER="/backups/conferencia-boletins/declaracoes-cpfs-oficial.xls"
DIR_BACKUP="/srv/backups/emeca/conferencia-boletins"
COMANDO="python manage.py reconciliar_cpfs_declaracoes"

info() { printf '\n[EMECA] %s\n' "$*"; }
abortar() { echo "[EMECA] ERRO: $*" >&2; exit 1; }

ETAPA="verificar dados de entrada"
test -f "$ARQUIVO" && test -s "$ARQUIVO" || abortar "Excel ainda não foi enviado ao mini PC."
test -d "$DIR_BACKUP" && test -w "$DIR_BACKUP" || abortar "Diretório de backup indisponível."
chmod 600 "$ARQUIVO"
test "$(git branch --show-current)" = "main" || abortar "Branch não é main."
test -z "$(git status --porcelain)" || abortar "Alterações locais no Git: não prosseguir."
git merge-base --is-ancestor 7206a1e2f626a9bc0644116a6d4fcaf450db1eda HEAD ||
  abortar "Código de reconciliação não está na versão selecionada."
docker compose config --quiet
test -f usuarioSec/management/commands/reconciliar_cpfs_declaracoes.py ||
  abortar "Comando de reconciliação ausente do código."
info "Verificando que o site atual está ativo (sem reiniciar WhatsApp)"
test "$(docker compose ps -q web | wc -l)" = "1" || abortar "Serviço web não encontrado."

ETAPA="criar backup inicial"
info "Criando backup consistente, antes de atualizar código ou CPFs"
BACKUP="$(mktemp "$DIR_BACKUP/antes-atualizacao-cpfs-XXXXXXXX.sqlite3")"
chmod 600 "$BACKUP"
docker compose exec -T web python - "$(basename "$BACKUP")" <<'PY'
import os
import sqlite3
import sys
from pathlib import Path
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "App.settings")
import django
django.setup()
from django.conf import settings
origem = Path(settings.DATABASES["default"]["NAME"])
destino = Path("/backups/conferencia-boletins") / sys.argv[1]
if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
    raise SystemExit("Banco não é SQLite: interrompido.")
if not origem.is_file() or not destino.is_file() or destino.stat().st_size:
    raise SystemExit("Origem ou destino do backup inválidos.")
with sqlite3.connect(f"file:{origem}?mode=ro", uri=True) as atual:
    with sqlite3.connect(destino) as copia:
        atual.backup(copia)
        if copia.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise SystemExit("Backup com falha de integridade.")
        decl = copia.execute("SELECT COUNT(*) FROM usuarioSec_declaracao").fetchone()[0]
        boletins = copia.execute(
            "SELECT COUNT(*), COUNT(faltas_totais) "
            "FROM site_publico_boletimaluno WHERE periodo_id=3"
        ).fetchone()
        publicado = copia.execute(
            "SELECT publicado FROM site_publico_periodoboletim WHERE id=3"
        ).fetchone()
        if decl != 633 or boletins != (27, 27) or publicado != (0,):
            raise SystemExit(
                "Estado do banco diferente do auditado (633 Declarações, 27 faltas, privado)."
            )
print("Backup íntegro e estado dos boletins confirmado.")
PY
test -s "$BACKUP" || abortar "Backup não foi criado."
info "Backup preservado: $BACKUP"

ETAPA="compilar aplicação"
info "Compilando apenas a aplicação web (sem reiniciar WA-AKG)"
docker compose build web
# Os testes automatizados já são realizados uma única vez pelo CI do GitHub.
# No servidor, mantém-se apenas validação mínima pós-implantação.

ETAPA="atualizar site"
info "Reiniciando apenas EMECA Web; worker e WhatsApp continuam ligados"
docker compose up -d --no-deps web
docker compose exec -T web python manage.py check

ETAPA="prévia da reconciliação"
info "Simulando planilha antes de gravar qualquer CPF"
PREVIA="$(docker compose exec -T web $COMANDO "$ARQUIVO_CONTAINER")"
printf '%s\n' "$PREVIA"
PLANO_ID="$(printf '%s\n' "$PREVIA" | sed -n 's/^plano_id: //p' | tail -n 1)"
[[ "$PLANO_ID" =~ ^[a-f0-9]{64}$ ]] || abortar "Plano de reconciliação não identificado."
ATUALIZAVEIS="$(printf '%s\n' "$PREVIA" | sed -n 's/^cadastros_atualizaveis: //p' | tail -n 1)"
[[ "$ATUALIZAVEIS" =~ ^[0-9]+$ ]] || abortar "Contagem de atualizáveis inválida."

if [ "$ATUALIZAVEIS" -gt 0 ]; then
  ETAPA="aplicar CPFs com backup e transação"
  info "Atualizando SOMENTE CPFs dos $ATUALIZAVEIS cadastros inequívocos"
  docker compose exec -T web $COMANDO "$ARQUIVO_CONTAINER" \
    --aplicar --plano-id "$PLANO_ID" \
    --backup-existente "/backups/conferencia-boletins/$(basename "$BACKUP")"
else
  info "Nenhum cadastro apto à atualização automática; sem alteração dos CPFs."
fi

ETAPA="auditoria final"
info "Comparando boletins e outros campos das Declarações com o backup"
docker compose exec -T web python - "$(basename "$BACKUP")" <<'PY'
import os
import re
import sqlite3
import sys
from pathlib import Path
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "App.settings")
import django
django.setup()
from django.conf import settings
from site_publico.models import BoletimAluno, PeriodoBoletim

antigo = Path("/backups/conferencia-boletins") / sys.argv[1]
atual = Path(settings.DATABASES["default"]["NAME"])
with sqlite3.connect(f"file:{antigo}?mode=ro", uri=True) as antes, \
     sqlite3.connect(f"file:{atual}?mode=ro", uri=True) as depois:
    if depois.execute("PRAGMA integrity_check").fetchone() != ("ok",):
        raise SystemExit("Falha na integridade do banco ativo.")
    for tabela in (
        "site_publico_boletimaluno",
        "site_publico_notaboletim",
        "site_publico_alunoboletim",
        "site_publico_periodoboletim",
        "usuarioSec_telefonedeclaracao",
    ):
        a = antes.execute(f'SELECT * FROM "{tabela}" ORDER BY id').fetchall()
        b = depois.execute(f'SELECT * FROM "{tabela}" ORDER BY id').fetchall()
        if a != b:
            raise SystemExit(f"Tabela modificada indevidamente: {tabela}")
    colunas = [
        linha[1] for linha in
        antes.execute('PRAGMA table_info("usuarioSec_declaracao")').fetchall()
    ]
    excluidas = {"cpfMae", "cpfResponsavel", "cpfDoAluno"}
    nomes = [c for c in colunas if c not in excluidas]
    lista = ", ".join('"' + c.replace('"', '""') + '"' for c in nomes)
    sql = f'SELECT {lista} FROM "usuarioSec_declaracao" ORDER BY id'
    if antes.execute(sql).fetchall() != depois.execute(sql).fetchall():
        raise SystemExit("Outros campos das Declarações foram modificados.")
    if antes.execute('SELECT COUNT(*) FROM "usuarioSec_declaracao"').fetchone() != (
        depois.execute('SELECT COUNT(*) FROM "usuarioSec_declaracao"').fetchone()
    ):
        raise SystemExit("Quantidade de Declarações mudou.")

periodo = PeriodoBoletim.objects.get(pk=3)
boletins = BoletimAluno.objects.filter(periodo_id=3).select_related("aluno__declaracao")
total = boletins.count()
sem_vinculo = 0
sem_documento = 0
aptos = 0
pendencias = []
for b in boletins:
    d = b.aluno.declaracao
    if not d:
        sem_vinculo += 1
        pendencias.append((b.pk, b.aluno.pk, "Sem Declaração vinculada"))
    elif not d.dataNascimentoAluno:
        pendencias.append((b.pk, b.aluno.pk, "Sem nascimento"))
    elif not any(
        len(re.sub(r"\D", "", c or "")) == 11
        for c in (d.cpfMae, d.cpfResponsavel)
    ):
        sem_documento += 1
        pendencias.append((b.pk, b.aluno.pk, "Sem CPF válido em formato"))
    else:
        aptos += 1

if total != 27 or boletins.filter(faltas_totais__isnull=True).exists():
    raise SystemExit("Quantidade de boletins ou total de faltas inesperado.")
if periodo.publicado:
    raise SystemExit("Período foi publicado sem autorização nesta rotina.")
print("AUDITORIA APROVADA: 633 Declarações e notas/vínculos/faltas preservados.")
print(f"BOLETINS: {total}; aptos em formato: {aptos}; sem vínculo: {sem_vinculo}; sem CPF: {sem_documento}.")
for boletim_id, perfil_id, motivo in pendencias:
    print(f"Pendente - Boletim {boletim_id} / Perfil {perfil_id}: {motivo}")
print("PUBLICAÇÃO: continua privada; nenhum boletim foi enviado ao WhatsApp.")
print(
    "HTTPS:",
    "habilitado" if all((
        settings.SECURE_SSL_REDIRECT,
        settings.SESSION_COOKIE_SECURE,
        settings.CSRF_COOKIE_SECURE,
    )) else "não configurado para acesso público seguro",
)
PY

ETAPA="saúde dos serviços"
info "Verificando serviços em funcionamento"
docker compose ps
info "INSTALAÇÃO FINALIZADA. CPFs aptos reconciliados; boletins PRIVADOS até corrigir vínculos e HTTPS."
