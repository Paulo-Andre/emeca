#!/usr/bin/env python3
"""Auditoria anônima, SEM GRAVAÇÃO, para recuperar boletins do período 3.

Não restaura ou apaga dados, não exibe identidades. Usa a API SQLite backup()
para ler uma cópia consistente do banco atual na memória. O arquivo de origem
também é aberto em modo imutável e somente leitura.
"""
import json
import subprocess

SCRIPT = r'''
import json
import sqlite3
import unicodedata
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote
from django.conf import settings

OUT={"fase":"INICIADO","periodo":3}
BACKUP_NAME="antes-atualizacao-validado-W7A2S2.sqlite3"
TABLES={
    "boletim":"site_publico_boletimaluno",
    "aluno":"site_publico_alunoboletim",
    "declaracao":"usuarioSec_declaracao",
}
def abrir(path, immutable=False):
    uri="file:"+quote(str(path),safe="/")+"?mode=ro"
    if immutable:
        uri+="&immutable=1"
    conn=sqlite3.connect(uri,uri=True,timeout=12)
    conn.execute("PRAGMA query_only=ON")
    return conn
def rows(c,table):
    cur=c.execute("SELECT * FROM "+table)
    names=[col[0] for col in cur.description]
    return {int(row[0]):dict(zip(names,row)) for row in cur}
def clean(name):
    s=unicodedata.normalize("NFKD",str(name or ""))
    s="".join(c for c in s if not unicodedata.combining(c))
    s=re.sub(r"[^A-Z0-9]+"," ",s.upper())
    return re.sub(r"\s+"," ",s).strip()
def chave(registro):
    if not registro:
        return None
    name=clean(registro.get("nomeDoAluno"))
    birth=str(registro.get("dataNascimentoAluno") or "").strip()
    if not name or not birth:
        return None
    return (name,birth)

try:
    db_path=Path(settings.DATABASES["default"]["NAME"])
    if settings.DATABASES["default"]["ENGINE"]!="django.db.backends.sqlite3":
        OUT["fase"]="BANCO_NAO_SQLITE"
    elif not db_path.exists():
        OUT["fase"]="ATUAL_INDISPONIVEL"
    else:
        matches=[p for p in Path("/backups").rglob(BACKUP_NAME)
                 if p.is_file() and not p.is_symlink()]
        if len(matches)!=1:
            OUT["fase"]="FONTE_NAO_UNICA_OU_AUSENTE"
            OUT["fontes_encontradas"]=len(matches)
        else:
            live=abrir(db_path)
            backup=abrir(matches[0],immutable=True)
            snap=sqlite3.connect(":memory:")
            try:
                live.backup(snap,pages=256,sleep=0.05)
                snap.execute("PRAGMA foreign_keys=ON")
                if snap.execute("PRAGMA quick_check").fetchone()[0]!="ok":
                    raise ValueError("ATUAL_INTEGRO_NAO_CONFIRMADO")
                if backup.execute("PRAGMA quick_check").fetchone()[0]!="ok":
                    raise ValueError("BACKUP_INTEGRO_NAO_CONFIRMADO")
                old={k:rows(backup,t) for k,t in TABLES.items()}
                now={k:rows(snap,t) for k,t in TABLES.items()}
                source={pk:v for pk,v in old["boletim"].items() if v["periodo_id"]==3}
                present={pk:v for pk,v in now["boletim"].items() if v["periodo_id"]==3}
                missing={pk:v for pk,v in source.items() if pk not in present}
                OUT["boletins_antigos"]=len(source)
                OUT["boletins_atuais"]=len(present)
                OUT["boletins_ausentes"]=len(missing)
                OUT["declaracoes_antigas"]=len(old["declaracao"])
                OUT["declaracoes_atuais"]=len(now["declaracao"])
                OUT["perfis_aluno_antigos"]=len(old["aluno"])
                OUT["perfis_aluno_atuais"]=len(now["aluno"])
                OUT["ids_boletim_reutilizados_fora_periodo"]=sum(
                    pk in now["boletim"] for pk in missing
                )
                # Índices fortes: nome normalizado e data de nascimento (ambos).
                current_by_key=defaultdict(list)
                for pk,d in now["declaracao"].items():
                    k=chave(d)
                    if k:
                        current_by_key[k].append(pk)
                aluno_by_decl=defaultdict(list)
                for pk,a in now["aluno"].items():
                    if a.get("declaracao_id") is not None:
                        aluno_by_decl[a["declaracao_id"]].append(pk)
                labels=Counter()
                mapped=[]
                refs=[]
                for pk,b in missing.items():
                    a=old["aluno"].get(b["aluno_id"])
                    if not a:
                        labels["SEM_PERFIL_ORIGEM"]+=1
                        continue
                    d=old["declaracao"].get(a.get("declaracao_id"))
                    k=chave(d)
                    if not k:
                        labels["ORIGEM_SEM_NOME_E_NASCIMENTO"]+=1
                        continue
                    dest=current_by_key.get(k,[])
                    if not dest:
                        labels["SEM_MATCH_NOME_E_NASCIMENTO"]+=1
                        continue
                    if len(dest)!=1:
                        labels["MULTIPLAS_DECLARACOES_COMPATIVEIS"]+=1
                        continue
                    dest_id=dest[0]
                    refs.append(dest_id)
                    perfis=aluno_by_decl.get(dest_id,[])
                    if len(perfis)>1:
                        labels["PERFIS_AMBIGUOS"]+=1
                        continue
                    if not perfis:
                        labels["MATCH_DECL_SEM_PERFIL"]+=1
                        continue
                    perfil=perfis[0]
                    if any(x["aluno_id"]==perfil for x in present.values()):
                        labels["JA_TEM_BOLETIM_NESTE_PERIODO"]+=1
                        continue
                    mapped.append((pk,perfil))
                    labels["MATCH_FORTE_PERFIL_EXISTENTE"]+=1
                OUT["correspondencias"]=dict(sorted(labels.items()))
                OUT["destinos_duplicados"]=len(refs)-len(set(refs))
                OUT["perfis_destino_duplicados"]=len(mapped)-len({x[1] for x in mapped})
                # Boletins ainda presentes: PK + aluno_id coincidem no backup,
                # mas IDs de perfil foram reciclados, exigindo checagem de identidade.
                identity=Counter()
                for pk,b in present.items():
                    origem=source.get(pk)
                    if not origem or origem.get("aluno_id")!=b.get("aluno_id"):
                        identity["ID_BOLETIM_OU_ALUNO_DIVERGENTE"]+=1
                        continue
                    a_old=old["aluno"].get(origem["aluno_id"])
                    a_now=now["aluno"].get(b["aluno_id"])
                    k_old=chave(old["declaracao"].get(a_old.get("declaracao_id"))) if a_old else None
                    k_now=chave(now["declaracao"].get(a_now.get("declaracao_id"))) if a_now else None
                    if k_old and k_now and k_old==k_now:
                        identity["IDENTIDADE_FORTE_CONFERIDA"]+=1
                    else:
                        identity["IDENTIDADE_NAO_CONFERIDA"]+=1
                OUT["boletins_presentes_identidade"]=dict(sorted(identity.items()))
                OUT["fks_atual_invalidas"]=len(snap.execute("PRAGMA foreign_key_check").fetchall())
                OUT["fase"]=(
                    "MATCH_24_CANDIDATOS_CONFIAVEIS"
                    if len(missing)==24 and len(mapped)==24
                    and OUT["destinos_duplicados"]==0
                    and OUT["perfis_destino_duplicados"]==0
                    and identity.get("IDENTIDADE_NAO_CONFERIDA",0)==0
                    and identity.get("ID_BOLETIM_OU_ALUNO_DIVERGENTE",0)==0
                    and OUT["fks_atual_invalidas"]==0
                    else "RECONCILIACAO_AINDA_NAO_SEGURA"
                )
            finally:
                backup.close()
                live.close()
                snap.close()
except Exception as exc:
    OUT["fase"]="ERRO_AUDITORIA"
    OUT["classe"]=type(exc).__name__
print("EMECA_AUDITORIA_ANONIMA:"+json.dumps(OUT,ensure_ascii=False))
'''

def main():
    print("=== Auditoria de identidade dos 24 boletins (SOMENTE LEITURA) ===")
    try:
        p=subprocess.run(
            ["docker","exec","emeca-web-1","python","manage.py","shell","-c",SCRIPT],
            capture_output=True,text=True,timeout=100,check=False,
        )
    except (OSError,subprocess.TimeoutExpired) as e:
        print("Consulta indisponível:",type(e).__name__)
        return
    if p.returncode:
        print("Auditoria falhou com código",p.returncode,
              "(detalhes ocultos para proteger alunos).")
        return
    for line in p.stdout.splitlines():
        if line.startswith("EMECA_AUDITORIA_ANONIMA:"):
            try:
                info=json.loads(line.split(":",1)[1])
            except ValueError:
                break
            for k in ("fase","boletins_antigos","boletins_atuais",
                      "boletins_ausentes","declaracoes_antigas",
                      "declaracoes_atuais","perfis_aluno_antigos",
                      "perfis_aluno_atuais","ids_boletim_reutilizados_fora_periodo",
                      "destinos_duplicados","perfis_destino_duplicados",
                      "fks_atual_invalidas","fontes_encontradas","classe"):
                if k in info:
                    print(k+":",info[k])
            print("Classificação de vínculos:",info.get("correspondencias",{}))
            print("Identidade dos 3 boletins existentes:",
                  info.get("boletins_presentes_identidade",{}))
            print("Nenhum dado, backup, boletim, nota ou sessão foi alterado.")
            return
    print("Sem resultado confiável; dados brutos protegidos.")

if __name__=="__main__":
    main()
