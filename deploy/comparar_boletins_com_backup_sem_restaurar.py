#!/usr/bin/env python3
"""Comparação EMECA SOMENTE LEITURA antes de restaurar boletins desaparecidos.

Executado no contêiner web para abrir tanto o banco atual quanto o backup
sem SQLite ATTACH, INSERT, UPDATE, DELETE, manipulação de arquivos ou DDL.
Não exibe nomes, CPF, telefone, notas, boletins, textos ou JIDs.
"""
import json
import subprocess

CODE = r'''
import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote
from django.conf import settings

BACKUP_NOME="antes-atualizacao-validado-W7A2S2.sqlite3"
CURRENT_TABLE="site_publico_boletimaluno"
PROFILE_TABLE="site_publico_alunoboletim"
GRADES_TABLE="site_publico_notaboletim"
SUBJECT_TABLE="site_publico_disciplinaboletim"
PERIOD_TABLE="site_publico_periodoboletim"

out={"status":"INICIADO","modo":"SOMENTE_LEITURA"}
def connect_ro(path):
    uri="file:"+quote(str(path),safe="/")+"?mode=ro"
    c=sqlite3.connect(uri,uri=True,timeout=8)
    c.execute("PRAGMA query_only=ON")
    c.row_factory=sqlite3.Row
    return c

def rows(conn,sql,*args):
    return [dict(r) for r in conn.execute(sql,args)]

def table_cols(conn, table):
    return {r["name"] for r in rows(conn,"PRAGMA table_info("+table+")")}

def keymap(seq):
    return {int(r["id"]):r for r in seq}

def read_type(conn,table):
    return rows(conn,"SELECT * FROM "+table)

def compact(t):
    return {k:v for k,v in t.items() if k!="atualizado_em"}

if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
    out.update(status="BANCO_ATUAL_NAO_SQLITE")
else:
    src=Path(str(settings.DATABASES["default"]["NAME"]))
    matches=[p for p in Path("/backups").rglob(BACKUP_NOME)
        if p.is_file() and not p.is_symlink()]
    if len(matches)!=1:
        out.update(status="BACKUP_INDISPONIVEL_OU_AMBIGUO",quantidade=len(matches))
    elif not src.is_file():
        out.update(status="BANCO_ATUAL_INDISPONIVEL")
    else:
        backup=matches[0]
        try:
            with connect_ro(src) as live, connect_ro(backup) as old:
                required=[CURRENT_TABLE,PROFILE_TABLE,GRADES_TABLE,SUBJECT_TABLE,PERIOD_TABLE]
                out["integridade_atual"]=live.execute("PRAGMA quick_check").fetchone()[0]
                out["integridade_backup"]=old.execute("PRAGMA quick_check").fetchone()[0]
                cols={t:table_cols(live,t)==table_cols(old,t) for t in required}
                out["mesma_estrutura_tabelas"]=all(cols.values())
                out["tabelas_diferentes"]=[t for t,ok in cols.items() if not ok]
                p_live=live.execute("SELECT * FROM "+PERIOD_TABLE+" WHERE id=3").fetchone()
                p_old=old.execute("SELECT * FROM "+PERIOD_TABLE+" WHERE id=3").fetchone()
                if not p_live or not p_old:
                    out.update(status="PERIODO_3_AUSENTE")
                else:
                    periodo_fields=("tipo","numero","ano","turma")
                    out["mesmo_periodo_escolar"]=all(p_live[k]==p_old[k] for k in periodo_fields)
                    boletins_old=keymap(rows(old,"SELECT * FROM "+CURRENT_TABLE+" WHERE periodo_id=3"))
                    boletins_live=keymap(rows(live,"SELECT * FROM "+CURRENT_TABLE+" WHERE periodo_id=3"))
                    out["boletins_backup"]=len(boletins_old)
                    out["boletins_atuais"]=len(boletins_live)
                    oldids=set(boletins_old)
                    liveids=set(boletins_live)
                    desaparecidos=oldids-liveids
                    novos=liveids-oldids
                    comuns=oldids&liveids
                    out["ids_ausentes"]=len(desaparecidos)
                    out["ids_novos"]=len(novos)
                    out["ids_comuns"]=len(comuns)
                    out["ids_comuns_outro_aluno"]=sum(
                        boletins_old[i]["aluno_id"]!=boletins_live[i]["aluno_id"]
                        for i in comuns
                    )
                    out["ids_comuns_nota_ou_faltas_diferente"]=sum(
                        (boletins_old[i]["numero_chamada"]!=boletins_live[i]["numero_chamada"]
                        or boletins_old[i]["faltas_totais"]!=boletins_live[i]["faltas_totais"])
                        for i in comuns
                    )
                    perfis_live=keymap(read_type(live,PROFILE_TABLE))
                    perfis_old=keymap(read_type(old,PROFILE_TABLE))
                    out["perfis_desaparecidos_ausentes"]=sum(
                        boletins_old[i]["aluno_id"] not in perfis_live for i in desaparecidos
                    )
                    out["perfis_desaparecidos_id_reutilizado"]=sum(
                        (boletins_old[i]["aluno_id"] in perfis_live and
                         boletins_old[i]["aluno_id"] in perfis_old and
                         perfis_old[boletins_old[i]["aluno_id"]]["nome"] !=
                         perfis_live[boletins_old[i]["aluno_id"]]["nome"])
                        for i in desaparecidos
                    )
                    perfis_diferentes=0
                    for i in desaparecidos:
                        pid=boletins_old[i]["aluno_id"]
                        if pid in perfis_live and pid in perfis_old:
                            if ("declaracao_id" in perfis_live[pid] and
                                perfis_old[pid].get("declaracao_id")!=perfis_live[pid].get("declaracao_id")):
                                perfis_diferentes+=1
                    out["perfis_vinculo_declaracao_alterado"]=perfis_diferentes
                    existentes_mesmo_aluno={
                        r["aluno_id"] for r in boletins_live.values()
                    }
                    out["desaparecidos_com_aluno_ja_presentes"]=sum(
                        boletins_old[i]["aluno_id"] in existentes_mesmo_aluno for i in desaparecidos
                    )
                    disciplinas_live=keymap(rows(live,"SELECT * FROM "+SUBJECT_TABLE+" WHERE periodo_id=3"))
                    disciplinas_old=keymap(rows(old,"SELECT * FROM "+SUBJECT_TABLE+" WHERE periodo_id=3"))
                    out["disciplinas_backup"]=len(disciplinas_old)
                    out["disciplinas_atuais"]=len(disciplinas_live)
                    out["disciplinas_id_ausentes"]=len(set(disciplinas_old)-set(disciplinas_live))
                    out["disciplinas_id_trocou_nome"]=sum(
                        disciplinas_old[i]["nome"]!=disciplinas_live[i]["nome"]
                        for i in set(disciplinas_old)&set(disciplinas_live)
                    )
                    ids=sorted(desaparecidos)
                    notas=[]
                    for n in range(0,len(ids),150):
                        batch=ids[n:n+150]
                        if not batch:continue
                        q="SELECT * FROM "+GRADES_TABLE+" WHERE boletim_id IN ("+",".join("?" for _ in batch)+")"
                        notas.extend(rows(old,q,*batch))
                    out["notas_recuperaveis_do_backup"]=len(notas)
                    out["notas_com_disciplina_ausente"]=sum(
                        n["disciplina_id"] not in disciplinas_live for n in notas
                    )
                    out["notas_com_disciplina_trocada"]=sum(
                        n["disciplina_id"] in disciplinas_live and n["disciplina_id"] in disciplinas_old and
                        disciplinas_live[n["disciplina_id"]]["nome"]!=disciplinas_old[n["disciplina_id"]]["nome"]
                        for n in notas
                    )
                    out["notas_com_id_ja_em_uso"]=0
                    old_grade_ids=[n["id"] for n in notas]
                    for z in range(0,len(old_grade_ids),200):
                        batch=old_grade_ids[z:z+200]
                        if batch:
                            q="SELECT COUNT(*) AS n FROM "+GRADES_TABLE+" WHERE id IN ("+",".join("?" for _ in batch)+")"
                            out["notas_com_id_ja_em_uso"]+=live.execute(q,batch).fetchone()["n"]
                    out["boletins_ids_em_uso_outro_periodo"]=0
                    for z in range(0,len(ids),200):
                        batch=ids[z:z+200]
                        if batch:
                            q="SELECT COUNT(*) AS n FROM "+CURRENT_TABLE+" WHERE id IN ("+",".join("?" for _ in batch)+")"
                            out["boletins_ids_em_uso_outro_periodo"]+=live.execute(q,batch).fetchone()["n"]
                    out["verificacao_chaves_atual"]=len(rows(live,"PRAGMA foreign_key_check"))
                    out["verificacao_chaves_backup"]=len(rows(old,"PRAGMA foreign_key_check"))
                    out["pronto_para_restauracao_automatica"]=bool(
                        out["integridade_atual"]=="ok" and out["integridade_backup"]=="ok"
                        and out["mesma_estrutura_tabelas"]
                        and out["mesmo_periodo_escolar"]
                        and out["boletins_backup"]==27 and out["boletins_atuais"]==3
                        and out["ids_ausentes"]==24
                        and not any(out[k] for k in (
                            "ids_novos","ids_comuns_outro_aluno",
                            "perfis_desaparecidos_ausentes","perfis_desaparecidos_id_reutilizado",
                            "perfis_vinculo_declaracao_alterado",
                            "desaparecidos_com_aluno_ja_presentes",
                            "disciplinas_id_ausentes","disciplinas_id_trocou_nome",
                            "notas_com_disciplina_ausente","notas_com_disciplina_trocada",
                            "notas_com_id_ja_em_uso","boletins_ids_em_uso_outro_periodo",
                            "verificacao_chaves_atual","verificacao_chaves_backup"
                        ))
                    )
                    out["status"]="ANALISADO"
        except (OSError,sqlite3.Error,KeyError,ValueError) as exc:
            out["status"]="FALHA_AO_COMPARAR"
            out["tipo_erro"]=type(exc).__name__
print("EMECA_COMPARACAO_RECUPERACAO:"+json.dumps(out,ensure_ascii=False))
'''

def main():
    print("=== COMPARAÇÃO SEGURA: boletins atuais x backup antigo ===")
    print("Somente leitura; não altera nenhum banco ou backup.")
    try:
        p=subprocess.run(
            ["docker","exec","emeca-web-1","python","manage.py","shell","-c",CODE],
            capture_output=True,text=True,timeout=85,check=False,
        )
    except (OSError,subprocess.TimeoutExpired) as exc:
        print("Consulta indisponível:",type(exc).__name__)
        return
    if p.returncode:
        print("Falha na consulta: código",p.returncode,
              "— detalhes ocultos para proteger alunos.")
        return
    for line in p.stdout.splitlines():
        if line.startswith("EMECA_COMPARACAO_RECUPERACAO:"):
            try: d=json.loads(line.split(":",1)[1])
            except ValueError: break
            for key,val in d.items():
                if key in ("modo","tabelas_diferentes"):
                    continue
                print(key+":",val)
            print("COMPARAÇÃO CONCLUÍDA. Nenhum dado modificado.")
            return
    print("Relatório inesperado; detalhes omitidos.")

if __name__=="__main__":
    main()
