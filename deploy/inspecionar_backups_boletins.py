#!/usr/bin/env python3
"""Procura possíveis backups de boletins sem restaurar ou alterar arquivos.
Conta registros de período 3 em arquivos SQLite acessíveis no contêiner web.
Arquivos compactados são apenas contabilizados para inspeção manual posterior.
"""
import json
import subprocess

CODE = r'''
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

raizes=[Path("/backups"),Path("/data")]
achados=[]
arquivos_compactados=0
vistos=set()
for raiz in raizes:
    if not raiz.is_dir():
        continue
    for caminho in raiz.rglob("*"):
        if len(vistos)>=2000:
            break
        if not caminho.is_file() or caminho.is_symlink():
            continue
        if str(caminho) in vistos:continue
        vistos.add(str(caminho))
        if caminho.suffix.lower() in (".gz",".zip",".tar",".tgz"):
            arquivos_compactados+=1
            continue
        if caminho.suffix.lower() not in (".sqlite3",".sqlite",".db"):
            continue
        try:
            tamanho=caminho.stat().st_size
            if tamanho>500*1024*1024 or tamanho<1024:
                continue
            url="file:"+quote(str(caminho),safe="/")+"?mode=ro"
            con=sqlite3.connect(url,uri=True,timeout=2)
            try:
                tabela=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='site_publico_boletimaluno'").fetchone()
                if not tabela:continue
                total=con.execute("SELECT COUNT(*) FROM site_publico_boletimaluno").fetchone()[0]
                periodo=con.execute("SELECT COUNT(*) FROM site_publico_boletimaluno WHERE periodo_id=3").fetchone()[0]
            finally:
                con.close()
            achados.append({"arquivo":caminho.name[:130],"origem":str(raiz),
                            "boletins_total":total,"periodo_3":periodo,
                            "tamanho_bytes":tamanho,
                            "modificado_em":int(caminho.stat().st_mtime)})
        except (OSError,sqlite3.DatabaseError):
            continue
achados.sort(key=lambda x:(x["periodo_3"],x["modificado_em"]),reverse=True)
print("EMECA_INVENTARIO_BACKUPS:"+json.dumps({
    "arquivos_validos":achados[:30],
    "compactados_encontrados":arquivos_compactados,
},ensure_ascii=False))
'''

def main():
    print("=== Busca de cópias para recuperação dos boletins ===")
    print("Somente leitura. Não restaura nenhum arquivo.")
    try:
        p=subprocess.run(["docker","exec","emeca-web-1","python","manage.py","shell","-c",CODE],
                         capture_output=True,text=True,timeout=70,check=False)
    except (subprocess.TimeoutExpired,OSError) as e:
        print("Inventário indisponível:",type(e).__name__)
        return
    if p.returncode:
        print("Inventário não concluído. Código:",p.returncode)
        return
    for line in p.stdout.splitlines():
        if not line.startswith("EMECA_INVENTARIO_BACKUPS:"):
            continue
        try:
            report=json.loads(line.split(":",1)[1])
        except (ValueError,IndexError):
            break
        print("Cópias SQLite localizadas:")
        for item in report.get("arquivos_validos",[]):
            print("- arquivo:",item.get("arquivo"),"em",item.get("origem"),
                  "| boletins período 3:",item.get("periodo_3"),
                  "| total:",item.get("boletins_total"))
        print("Arquivos compactados (não inspecionados):",
              report.get("compactados_encontrados"))
        print("Nada foi restaurado ou modificado.")
        return
    print("Formato do inventário não reconhecido.")

if __name__=="__main__":
    main()
