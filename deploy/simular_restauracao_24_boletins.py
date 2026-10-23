#!/usr/bin/env python3
"""Simulação isolada de recuperação dos boletins do período 3.

Não modifica o banco ativo, seus WALs, arquivos de backup, nem sessões WhatsApp.
Consulta as cópias SQLite existentes, copia o banco ativo EM MEMÓRIA pela
API de backup SQLite e simula inserir somente boletins/notas ausentes.
Não imprime nomes, números, CPF, conteúdo de boletim ou outros dados pessoais.
"""
from __future__ import annotations

import json
import subprocess

CODE = r'''
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote
from django.conf import settings

B="site_publico_boletimaluno"
N="site_publico_notaboletim"
A="site_publico_alunoboletim"
D="site_publico_disciplinaboletim"
P="site_publico_periodoboletim"
DECL="usuarioSec_declaracao"
EXPECTED=(B,N,A,D,P,DECL)
PID=3
out={"fase":"iniciada","somente_simulacao":True}

def ro(path, backup=False):
    uri="file:"+quote(str(path),safe="/")+"?mode=ro"
    if backup: uri+="&immutable=1"
    cn=sqlite3.connect(uri,uri=True,timeout=12)
    cn.execute("PRAGMA query_only=ON")
    return cn

def linhas(conn, table, where="", args=()):
    return conn.execute("SELECT * FROM "+table+" "+where,args).fetchall()

def ids(conn, table, where="", args=()):
    return {int(row[0]):tuple(row) for row in conn.execute(
        "SELECT * FROM "+table+" "+where,args)}

def colunas(conn,table):
    return [r[1] for r in conn.execute("PRAGMA table_info("+table+")")]

def count(conn,table,where="",args=()):
    return conn.execute("SELECT COUNT(*) FROM "+table+" "+where,args).fetchone()[0]

try:
    cfg=settings.DATABASES["default"]
    if cfg["ENGINE"]!="django.db.backends.sqlite3":
        out["fase"]="BANCO_NAO_SQLITE"
    else:
        dbfile=Path(cfg["NAME"])
        root=Path("/backups")
        if not dbfile.is_file() or not root.is_dir():
            out["fase"]="ARQUIVOS_INDISPONIVEIS"
        else:
            live=ro(dbfile)
            try:
                # Fonte online -> destino :memory:; jamais editar produção.
                tmp=sqlite3.connect(":memory:")
                live.backup(tmp,pages=256,sleep=.05)
                tmp.execute("PRAGMA foreign_keys=ON")
                if tmp.execute("PRAGMA quick_check").fetchone()[0]!="ok":
                    raise RuntimeError("BANCO_ATUAL_INTEGRO_NAO_CONFIRMADO")
                campos={t:colunas(tmp,t) for t in EXPECTED}
                if any(not v for v in campos.values()):
                    raise RuntimeError("TABELA_AUSENTE")
                atual=ids(tmp,B)
                atuais_notas=ids(tmp,N)
                candidatos=sorted(
                    [path for path in root.rglob("*.sqlite3")
                     if path.is_file() and not path.is_symlink()
                     and len(path.relative_to(root).parts)<=4],
                    key=lambda p:p.stat().st_mtime,reverse=True,
                )[:80]
                selecionado=None
                motivo="SEM_BACKUP_COMPATIVEL"
                for path in candidatos:
                    try:
                        origem=ro(path,backup=True)
                        try:
                            if any(colunas(origem,t)!=campos[t] for t in EXPECTED):
                                continue
                            if origem.execute("PRAGMA quick_check").fetchone()[0]!="ok":
                                continue
                            antigos=ids(origem,B)
                            antigos_p3={i:v for i,v in antigos.items() if v[campos[B].index("periodo_id")]==PID}
                            if len(antigos_p3)<27:
                                continue
                            presentes_p3={
                                i:v for i,v in atual.items()
                                if v[campos[B].index("periodo_id")]==PID
                            }
                            # Dados/horários dos três boletins restantes podem
                            # ter sido editados depois do backup; preservá-los.
                            if any(
                                i not in antigos_p3 or any(
                                    antigos_p3[i][campos[B].index(chave)] !=
                                    v[campos[B].index(chave)]
                                    for chave in ("periodo_id","aluno_id")
                                )
                                for i,v in presentes_p3.items()
                            ):
                                motivo="BACKUP_NAO_CORRESPONDE_AOS_3_EXISTENTES"
                                continue
                            if any(i in atual and atual[i]!=v for i,v in antigos_p3.items()):
                                motivo="ID_BOLETIM_REUTILIZADO"
                                continue
                            selecionado=path
                            nota_backup=ids(origem,N)
                            aluno_backup=ids(origem,A)
                            disciplina_backup=ids(origem,D)
                            periodo_backup=ids(origem,P)
                            decl_backup=ids(origem,DECL)
                            break
                        finally:
                            origem.close()
                    except (OSError,sqlite3.Error,ValueError):
                        continue
                out["backups_verificados_ate"]=len(candidatos)
                out["periodo"]=PID
                out["boletins_atuais"]=sum(
                    v[campos[B].index("periodo_id")]==PID for v in atual.values()
                )
                if selecionado is None:
                    out["fase"]=motivo
                else:
                    ausentes={i:v for i,v in antigos_p3.items() if i not in atual}
                    vinculados={v[campos[B].index("aluno_id")] for v in ausentes.values()}
                    notas_ausentes={
                        i:v for i,v in nota_backup.items()
                        if v[campos[N].index("boletim_id")] in ausentes
                    }
                    out["referencia"]=selecionado.name
                    out["boletins_no_backup"]=len(antigos_p3)
                    out["boletins_para_simular"]=len(ausentes)
                    out["notas_para_simular"]=len(notas_ausentes)
                    out["notas_ja_existentes"]=len(atuais_notas)
                    col_aluno=campos[A]
                    alunos_agora=ids(tmp,A)
                    out["alunos_referenciados_ausentes"]=sum(
                        i not in alunos_agora for i in vinculados
                    )
                    out["alunos_id_reutilizado"]=sum(
                        i in alunos_agora and i in aluno_backup
                        and alunos_agora[i][col_aluno.index("nome")]!=aluno_backup[i][col_aluno.index("nome")]
                        for i in vinculados
                    )
                    out["notas_id_colidindo"]=len(set(notas_ausentes)&set(atuais_notas))
                    disciplinas_agora=ids(tmp,D)
                    disc_refs={v[campos[N].index("disciplina_id")] for v in notas_ausentes.values()}
                    out["disciplinas_incompatíveis"]=sum(
                        i not in disciplinas_agora or i not in disciplina_backup
                        or any(
                            disciplinas_agora[i][campos[D].index(field)] !=
                            disciplina_backup[i][campos[D].index(field)]
                            for field in ("periodo_id","nome")
                        )
                        for i in disc_refs
                    )
                    periodos_agora=ids(tmp,P)
                    out["periodo_compativel"]=(
                        PID in periodos_agora and PID in periodo_backup
                        and all(
                            periodos_agora[PID][campos[P].index(field)] ==
                            periodo_backup[PID][campos[P].index(field)]
                            for field in ("tipo","numero","ano","turma")
                        )
                    )
                    declaracoes_agora=ids(tmp,DECL)
                    out["declaracoes_ausentes_do_backup"]=len(set(decl_backup)-set(declaracoes_agora))
                    out["fks_atuais_invalidas"]=len(tmp.execute("PRAGMA foreign_key_check").fetchall())
                    blockers=[
                        out["alunos_referenciados_ausentes"],
                        out["alunos_id_reutilizado"],
                        out["notas_id_colidindo"],
                        out["disciplinas_incompatíveis"],
                        not out["periodo_compativel"],
                    ]
                    if any(blockers):
                        out["fase"]="BLOQUEADA_POR_INCONSISTENCIA"
                    elif len(ausentes)!=24 or len(notas_ausentes)!=240:
                        out["fase"]="QUANTIDADES_DIFERENTES_DAS_ESPERADAS"
                    else:
                        try:
                            tmp.execute("BEGIN")
                            for row in ausentes.values():
                                tmp.execute("INSERT INTO "+B+" VALUES ("+
                                    ",".join("?" for _ in row)+")",row)
                            for row in notas_ausentes.values():
                                tmp.execute("INSERT INTO "+N+" VALUES ("+
                                    ",".join("?" for _ in row)+")",row)
                            out["apos_simulacao_boletins"]=count(
                                tmp,B,"WHERE periodo_id=?",(PID,)
                            )
                            out["apos_simulacao_notas"]=count(tmp,N)
                            out["fks_apos_simulacao_invalidas"]=len(
                                tmp.execute("PRAGMA foreign_key_check").fetchall()
                            )
                            out["fase"]=(
                                "SIMULACAO_OK"
                                if out["apos_simulacao_boletins"]==27
                                and out["fks_apos_simulacao_invalidas"]==out["fks_atuais_invalidas"]
                                else "SIMULACAO_INCONSISTENTE"
                            )
                        except (sqlite3.Error, ValueError) as exc:
                            out["fase"]="FALHA_NA_SIMULACAO"
                            out["erro_classe"]=type(exc).__name__
                        finally:
                            tmp.rollback()
            finally:
                live.close()
except Exception as exc:
    out["fase"]="ERRO_DE_DIAGNOSTICO"
    out["erro_classe"]=type(exc).__name__

print("EMECA_RESTAURACAO_SIMULADA:"+json.dumps(out,ensure_ascii=False))
'''

def main():
    print("=== EMECA: simulação de restauração isolada (NENHUMA GRAVAÇÃO) ===")
    try:
        p=subprocess.run(
            ["docker","exec","emeca-web-1","python","manage.py","shell","-c",CODE],
            text=True,capture_output=True,timeout=90,check=False,
        )
    except (OSError,subprocess.TimeoutExpired) as exc:
        print("Simulação indisponível:",type(exc).__name__)
        return
    if p.returncode:
        print("Simulação falhou com código",p.returncode,
              "(saída detalhada protegida para não expor registros).")
        return
    report=None
    for line in p.stdout.splitlines():
        if line.startswith("EMECA_RESTAURACAO_SIMULADA:"):
            try: report=json.loads(line.split(":",1)[1])
            except ValueError: pass
    if not isinstance(report,dict):
        print("Resultado não reconhecido. Nenhuma alteração efetuada.")
        return
    for key in (
        "fase","referencia","periodo","boletins_atuais","boletins_no_backup",
        "boletins_para_simular","notas_para_simular","notas_ja_existentes",
        "alunos_referenciados_ausentes","alunos_id_reutilizado",
        "notas_id_colidindo","disciplinas_incompatíveis","periodo_compativel",
        "declaracoes_ausentes_do_backup","fks_atuais_invalidas",
        "apos_simulacao_boletins","apos_simulacao_notas",
        "fks_apos_simulacao_invalidas","erro_classe"
    ):
        if key in report:
            print(key+":",report[key])
    print("NENHUM BOLETIM, NOTA, DECLARAÇÃO, BACKUP OU SESSÃO ALTERADO.")

if __name__=="__main__":
    main()
