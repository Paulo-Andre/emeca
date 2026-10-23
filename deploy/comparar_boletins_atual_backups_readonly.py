#!/usr/bin/env python3
"""Compara o banco SQLite EMECA com o backup mais recente com >=27 boletins.
NUNCA modifica os arquivos, não usa ORM com gravação e não restaura nada.
Saída somente com contagens e IDs técnicos de períodos, sem dados pessoais.
"""
import json
import subprocess

CODE = r'''
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote
from django.conf import settings

T_BOLETIM = "site_publico_boletimaluno"
T_NOTA = "site_publico_notaboletim"
T_ALUNO = "site_publico_alunoboletim"
T_DECLARACAO = "usuarioSec_declaracao"
T_PERIODO = "site_publico_periodoboletim"
EXPECTED=(T_BOLETIM,T_NOTA,T_ALUNO,T_PERIODO)
out={"estado":"INICIADO"}

def abrir(path, immutable=False):
    uri="file:"+quote(str(path),safe="/")+"?mode=ro"
    if immutable:
        uri+="&immutable=1"
    db=sqlite3.connect(uri,uri=True,timeout=10)
    db.execute("PRAGMA query_only=ON")
    return db

def tem_tabelas(db):
    nomes={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return all(t in nomes for t in EXPECTED)

def carregar(db):
    boletins=db.execute(
        "SELECT id,periodo_id,aluno_id FROM "+T_BOLETIM
    ).fetchall()
    por_id={int(row[0]):(int(row[1]),int(row[2])) for row in boletins}
    pares={value for value in por_id.values()}
    distribuicao={
        int(k):int(v) for k,v in db.execute(
            "SELECT periodo_id,COUNT(*) FROM "+T_BOLETIM+" GROUP BY periodo_id"
        ).fetchall()
    }
    notas={int(k):int(v) for k,v in db.execute(
        "SELECT boletim_id,COUNT(*) FROM "+T_NOTA+" GROUP BY boletim_id"
    ).fetchall()}
    return {
        "boletins":por_id,
        "pares":pares,
        "distribuicao":distribuicao,
        "notas":notas,
        "alunos":db.execute("SELECT COUNT(*) FROM "+T_ALUNO).fetchone()[0],
        "declaracoes":db.execute("SELECT COUNT(*) FROM "+T_DECLARACAO).fetchone()[0]
            if db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(T_DECLARACAO,)).fetchone() else None,
    }

try:
    banco=settings.DATABASES["default"]
    if banco.get("ENGINE")!="django.db.backends.sqlite3":
        out["estado"]="BANCO_ATUAL_NAO_EH_SQLITE"
    else:
        origem=Path(banco["NAME"])
        backups=Path("/backups")
        if not origem.is_file() or not backups.is_dir():
            out["estado"]="BANCO_OU_PASTA_INDISPONIVEL"
        else:
            with abrir(origem) as db:
                if not tem_tabelas(db):
                    raise RuntimeError("ESQUEMA_ATUAL_INVALIDO")
                atual=carregar(db)
            selecionado=None
            selecionado_dados=None
            vistos=0
            caminhos=sorted(
                (p for p in backups.rglob("*.sqlite3")
                 if p.is_file() and not p.is_symlink()
                 and len(p.relative_to(backups).parts)<=4),
                key=lambda p:p.stat().st_mtime,reverse=True
            )
            for arquivo in caminhos[:80]:
                vistos+=1
                try:
                    with abrir(arquivo,immutable=True) as db:
                        if not tem_tabelas(db):
                            continue
                        qtd=db.execute("SELECT COUNT(*) FROM "+T_BOLETIM).fetchone()[0]
                        if qtd<27:
                            continue
                        # Confirmar integridade antes de usar como referência.
                        if db.execute("PRAGMA quick_check").fetchone()[0]!="ok":
                            continue
                        selecionado=arquivo
                        selecionado_dados=carregar(db)
                        break
                except (OSError,sqlite3.Error):
                    continue
            out["copias_analisadas"]=vistos
            out["atual_total"]=len(atual["boletins"])
            out["atual_periodo_3"]=atual["distribuicao"].get(3,0)
            if selecionado is None:
                out["estado"]="SEM_BACKUP_COM_27_BOLETINS_VALIDADO"
            else:
                velho=selecionado_dados
                ai=atual["boletins"]
                bi=velho["boletins"]
                iguais=set(ai).intersection(bi)
                mudaram=[i for i in iguais if ai[i]!=bi[i]]
                out.update({
                    "estado":"COMPARACAO_CONCLUIDA",
                    "referencia":str(selecionado.relative_to(backups)),
                    "backup_total":len(bi),
                    "backup_periodo_3":velho["distribuicao"].get(3,0),
                    "ids_antigos_ausentes":len(set(bi)-set(ai)),
                    "ids_novos":len(set(ai)-set(bi)),
                    "ids_mantidos_mesmo_aluno_periodo":len(iguais)-len(mudaram),
                    "ids_reutilizados_para_outro_aluno_ou_periodo":len(mudaram),
                    "vinculos_antigos_ausentes":len(velho["pares"]-atual["pares"]),
                    "vinculos_novos":len(atual["pares"]-velho["pares"]),
                    "notas_backup":sum(velho["notas"].values()),
                    "notas_atual":sum(atual["notas"].values()),
                    "alunos_backup":velho["alunos"],
                    "alunos_atual":atual["alunos"],
                    "declaracoes_backup":velho["declaracoes"],
                    "declaracoes_atual":atual["declaracoes"],
                    "por_periodo":[
                        {"periodo_id":p,
                         "antes":velho["distribuicao"].get(p,0),
                         "atual":atual["distribuicao"].get(p,0)}
                        for p in sorted(set(velho["distribuicao"])|set(atual["distribuicao"]))
                    ]
                })
except Exception as exc:
    out["estado"]="ERRO_COMPARACAO"
    out["erro_classe"]=type(exc).__name__
print("COMPARACAO_PRIVADA:"+json.dumps(out,ensure_ascii=False))
'''

def main():
    print("=== EMECA: comparação segura de boletins com backups (SEM RESTAURAÇÃO) ===")
    try:
        r=subprocess.run(
            ["docker","exec","emeca-web-1","python","manage.py","shell","-c",CODE],
            capture_output=True,text=True,check=False,timeout=60,
        )
    except (OSError,subprocess.TimeoutExpired) as e:
        print("Consulta indisponível:",type(e).__name__)
        return
    if r.returncode:
        print("Consulta Django falhou; código:",r.returncode,"(detalhes ocultados).")
        return
    report=None
    for ln in r.stdout.splitlines():
        if ln.startswith("COMPARACAO_PRIVADA:"):
            try: report=json.loads(ln.split(":",1)[1])
            except ValueError: pass
    if not isinstance(report,dict):
        print("Formato de resposta não reconhecido; nenhuma mudança efetuada.")
        return
    print("Estado:",report.get("estado"))
    print("Total banco atual:",report.get("atual_total","—"))
    print("Boletins período 3 atual:",report.get("atual_periodo_3","—"))
    if report.get("estado")=="COMPARACAO_CONCLUIDA":
        print("Backup de referência:",report["referencia"])
        for key in (
            "backup_total","backup_periodo_3",
            "ids_antigos_ausentes","ids_novos",
            "ids_mantidos_mesmo_aluno_periodo",
            "ids_reutilizados_para_outro_aluno_ou_periodo",
            "vinculos_antigos_ausentes","vinculos_novos",
            "notas_backup","notas_atual",
            "alunos_backup","alunos_atual",
            "declaracoes_backup","declaracoes_atual"
        ):
            print(key+":",report.get(key))
        for row in report.get("por_periodo",[]):
            print("Período",row["periodo_id"],"| antes:",row["antes"],"| atual:",row["atual"])
    else:
        print("Detalhe técnico:",report.get("erro_classe","—"))
    print("Nenhum arquivo restaurado, gravado, apagado ou modificado.")

if __name__=="__main__":
    main()
