#!/usr/bin/env python3
"""Audita somente a identidade do boletim restante após 23 matches fortes.
Leitura do backup e cópia SQLite em memória; não altera o banco em produção.
Não mostra nomes, CPF, datas de nascimento, IDs de aluno ou notas.
"""
import json
import subprocess

CODE = r"""
import json, sqlite3, unicodedata, re
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote
from django.conf import settings

B='site_publico_boletimaluno'
A='site_publico_alunoboletim'
D='usuarioSec_declaracao'
BACKUP='antes-atualizacao-validado-W7A2S2.sqlite3'
out={'estado':'INICIADO'}
def ro(path, immutable=False):
    u='file:'+quote(str(path),safe='/')+'?mode=ro'
    if immutable:u+='&immutable=1'
    c=sqlite3.connect(u,uri=True,timeout=15)
    c.execute('PRAGMA query_only=ON')
    return c
def table(c,name):
    cur=c.execute('SELECT * FROM '+name)
    cols=[x[0] for x in cur.description]
    return {int(row[0]):dict(zip(cols,row)) for row in cur}
def norm(v):
    v=unicodedata.normalize('NFKD',str(v or ''))
    v=''.join(c for c in v if not unicodedata.combining(c)).upper()
    return re.sub(r'\s+',' ',re.sub(r'[^A-Z0-9]+',' ',v)).strip()
def key(decl):
    if not decl:return None
    n=norm(decl.get('nomeDoAluno'))
    birth=str(decl.get('dataNascimentoAluno') or '').strip()
    return (n,birth) if n and birth else None
try:
    cfg=settings.DATABASES['default']
    if cfg['ENGINE']!='django.db.backends.sqlite3':
        out['estado']='BANCO_NAO_SQLITE'
    else:
        src=Path(cfg['NAME'])
        copies=[p for p in Path('/backups').rglob(BACKUP) if p.is_file() and not p.is_symlink()]
        if len(copies)!=1 or not src.is_file():
            out['estado']='FONTE_INDISPONIVEL_OU_AMBIGUA'
        else:
            live=ro(src)
            old=ro(copies[0],immutable=True)
            mem=sqlite3.connect(':memory:')
            try:
                live.backup(mem,pages=256,sleep=.05)
                if old.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                    raise ValueError('BACKUP_CORROMPIDO')
                if mem.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                    raise ValueError('ATUAL_CORROMPIDO')
                ob,oa,od=(table(old,t) for t in (B,A,D))
                nb,na,nd=(table(mem,t) for t in (B,A,D))
                source={i:b for i,b in ob.items() if b['periodo_id']==3}
                present={i:b for i,b in nb.items() if b['periodo_id']==3}
                missing={i:b for i,b in source.items() if i not in present}
                current_decls_by_key=defaultdict(list)
                for id,d in nd.items():
                    k=key(d)
                    if k:current_decls_by_key[k].append(id)
                current_profiles_by_decl=defaultdict(list)
                for id,a in na.items():
                    if a.get('declaracao_id') is not None:
                        current_profiles_by_decl[a['declaracao_id']].append(id)
                in_period={b['aluno_id'] for b in present.values()}
                matched_profiles=set()
                leftover=[]
                for i,b in missing.items():
                    oldprofile=oa.get(b['aluno_id'])
                    olddecl=od.get(oldprofile.get('declaracao_id')) if oldprofile else None
                    k=key(olddecl)
                    candidates=current_decls_by_key.get(k,[]) if k else []
                    profile_ids=current_profiles_by_decl.get(candidates[0],[]) if len(candidates)==1 else []
                    if len(profile_ids)==1 and profile_ids[0] not in in_period and profile_ids[0] not in matched_profiles:
                        matched_profiles.add(profile_ids[0])
                    else:
                        leftover.append((i,oldprofile,olddecl))
                out['faltantes']=len(missing)
                out['matches_primarios']=len(matched_profiles)
                out['pendentes_identidade']=len(leftover)
                if len(missing)!=24 or len(matched_profiles)!=23 or len(leftover)!=1:
                    out['estado']='ESTADO_MUDOU_REAUDITAR'
                else:
                    oldpk, oldprof, olddecl=leftover[0]
                    out['perfil_antigo_presente']=bool(oldprof)
                    out['declaracao_antiga_presente']=bool(olddecl)
                    out['declaracao_antiga_existe_no_atual']=bool(
                        olddecl and oldprof.get('declaracao_id') in nd
                    )
                    out['nome_antigo_perfil_disponivel']=bool(oldprof and norm(oldprof.get('nome')))
                    out['nascimento_antigo_perfil_disponivel']=bool(
                        oldprof and oldprof.get('data_nascimento')
                    )
                    old_name=norm(oldprof.get('nome')) if oldprof else ''
                    old_birth=str(oldprof.get('data_nascimento') or '').strip() if oldprof else ''
                    if old_name and old_birth:
                        # Identidade independente do ID antigo e compatível também
                        # com o cadastro de Declarações que o perfil atual referencia.
                        options=[]
                        for id,profile in na.items():
                            if id in matched_profiles or id in in_period:continue
                            dd=nd.get(profile.get('declaracao_id'))
                            if not dd:continue
                            if (norm(profile.get('nome'))==old_name and
                                str(profile.get('data_nascimento') or '').strip()==old_birth and
                                key(dd)==(old_name,old_birth)):
                                options.append(id)
                        out['alternativas_por_nome_nascimento_do_perfil']=len(options)
                        out['estado']=(
                            'IDENTIDADE_24_CANDIDATA_COM_MATCH_FORTE'
                            if len(options)==1 else
                            'IDENTIDADE_24_NAO_RESOLVIDA'
                        )
                    else:
                        out['alternativas_por_nome_nascimento_do_perfil']=0
                        out['estado']='IDENTIDADE_24_SEM_DADOS_SUFFICIENTES'
            finally:
                live.close();old.close();mem.close()
except Exception as exc:
    out['estado']='ERRO_AUDITORIA'
    out['classe']=type(exc).__name__
print('EMECA_ULTIMA_IDENTIDADE:'+json.dumps(out,ensure_ascii=False))
"""
def main():
    print('=== EMECA: investigação anônima do 24º boletim — SOMENTE LEITURA ===')
    try:
        r=subprocess.run(['docker','exec','emeca-web-1','python','manage.py',
                          'shell','-c',CODE],
                         capture_output=True,text=True,timeout=100,check=False)
    except (OSError,subprocess.TimeoutExpired) as e:
        print('Auditoria indisponível:',type(e).__name__)
        return
    if r.returncode:
        print('Auditoria interrompida:',r.returncode,
              '— detalhes não exibidos por privacidade.')
        return
    for line in r.stdout.splitlines():
        if line.startswith('EMECA_ULTIMA_IDENTIDADE:'):
            try:out=json.loads(line.split(':',1)[1])
            except ValueError:break
            for k in ('estado','faltantes','matches_primarios','pendentes_identidade',
                      'perfil_antigo_presente','declaracao_antiga_presente',
                      'declaracao_antiga_existe_no_atual',
                      'nome_antigo_perfil_disponivel',
                      'nascimento_antigo_perfil_disponivel',
                      'alternativas_por_nome_nascimento_do_perfil','classe'):
                if k in out:print(k+':',out[k])
            print('Nenhuma restauração, exclusão ou gravação de dados.')
            return
    print('Resultado não reconhecido; nenhum dado foi alterado.')
if __name__=='__main__':
    main()
