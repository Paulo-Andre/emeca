#!/usr/bin/env python3
"""Aplica atualizações versionadas ao WA-AKG, preservando volumes e sessão.

Uso na máquina projetos-edu:
    python3 /srv/projetos/emeca/deploy/wa-akg/aplicar_correcoes.py
O script não altera bancos, contêineres, arquivos .env ou chaves de autenticação.
Faça backup dos volumes antes de atualizar dependências ou a imagem.
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import shutil
import sys


def substitute(text: str, before: str, after: str, context: str) -> str:
    if after in text:
        return text
    if text.count(before) != 1:
        raise RuntimeError(
            f"WA-AKG mudou estrutura de {context}: esperado um marcador único, "
            f"encontrados {text.count(before)}. Nenhum arquivo será alterado."
        )
    return text.replace(before, after, 1)


def prepare(source: pathlib.Path, patch_dir: pathlib.Path):
    instance = source / "src/modules/whatsapp/instance.ts"
    index = source / "src/modules/whatsapp/store/index.ts"
    chat_service = source / "src/modules/whatsapp/chat.service.ts"
    chat_route = source / "src/app/api/chat/[sessionId]/route.ts"
    overlay_file = patch_dir / "overrides/src/modules/whatsapp/store/emeca-identity.ts"
    target_file = source / "src/modules/whatsapp/store/emeca-identity.ts"

    required = [instance, index, chat_service, chat_route, overlay_file]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise RuntimeError("Arquivos não encontrados: " + ", ".join(missing))
    if target_file.exists() and target_file.read_bytes() != overlay_file.read_bytes():
        raise RuntimeError(
            "O módulo emeca-identity.ts já existe com outro conteúdo; "
            "faça backup/revisão manual antes de continuar."
        )

    edits: dict[pathlib.Path, str] = {}

    value = instance.read_text(encoding="utf-8")
    value = substitute(
        value,
        'import { bindContactSync } from "./store/contacts";',
        'import { bindContactSync } from "./store/contacts";\n'
        'import { bindEmecaContactIdentity } from "./store/emeca-identity";',
        "import da instância",
    )
    value = substitute(
        value,
        '        bindContactSync(this.socket, this.sessionId);',
        '        bindContactSync(this.socket, this.sessionId);\n'
        '        bindEmecaContactIdentity(this.socket, this.sessionId);',
        "ligação dos eventos Baileys",
    )
    edits[instance] = value

    value = index.read_text(encoding="utf-8")
    value = substitute(
        value,
        'name: c.name || c.notify || c.verifiedName,',
        'name: c.name || c.verifiedName || undefined,',
        "nome de contato no upsert",
    )
    # The source's original contact-upsert doesn't persist phoneNumber.
    # The supplementary listener persists both directions of a proven LID/PN
    # link; legacy upserts continue to preserve raw contact data.
    value = substitute(
        value,
        'if (pushName) contactData.name = pushName;',
        '// pushName is a profile display-name, not a saved contact name.',
        "preservação de nomes salvos",
    )
    value = substitute(
        value,
        'name: !fromMe ? pushName : undefined,',
        'name: undefined, // do not overwrite a saved name with pushName',
        "nome criado a partir da mensagem",
    )
    edits[index] = value

    value = chat_service.read_text(encoding="utf-8")
    value = substitute(
        value,
        '        limit = 50,',
        '        limit = 300,',
        "limite padrão de chats",
    )
    value = substitute(
        value,
        '        return result;\n    }\n\n    /**\n     * Get messages for a specific chat',
        '        return await ChatService.enrichEmecaChats(dbSessionId, result);\n'
        '    }\n\n' + ENRICH_METHOD +
        '    /**\n     * Get messages for a specific chat',
        "identificação padronizada de chats",
    )
    edits[chat_service] = value

    value = chat_route.read_text(encoding="utf-8")
    value = substitute(
        value,
        '        const chatList = await ChatService.getChatsList(session.id);',
        '        const params = new URL(request.url).searchParams;\n'
        '        const requested = Number.parseInt(params.get("limit") || "300", 10);\n'
        '        const limit = Number.isFinite(requested) ? '
        'Math.max(1, Math.min(requested, 1000)) : 300;\n'
        '        const before = params.get("before") || undefined;\n'
        '        if (before && Number.isNaN(Date.parse(before))) {\n'
        '            return NextResponse.json({ status: false, error: "Invalid cursor" }, { status: 400 });\n'
        '        }\n'
        '        const chatList = await ChatService.getChatsList(session.id, limit, before);',
        "paginação do endpoint",
    )
    value = substitute(
        value,
        '        return NextResponse.json({ status: true, message: "Chats fetched successfully", data: chatList });',
        '        const nextBefore = chatList.length ? '
        'chatList[chatList.length - 1].lastMessage?.timestamp || null : null;\n'
        '        return NextResponse.json({ status: true, '
        'message: "Chats fetched successfully", data: chatList, '
        'meta: { limit, nextBefore } });',
        "cursor para todos os chats",
    )
    edits[chat_route] = value

    edits[target_file] = overlay_file.read_text(encoding="utf-8")
    return edits


ENRICH_METHOD = """    /**
     * Normaliza os metadados para EMECA sem inventar telefones.
     * As associações vêm dos campos explícitos LID/PN salvos pelo Baileys.
     * Mantém o JID original da conversa e fornece aliases para o consumidor.
     */
    private static async enrichEmecaChats(dbSessionId: string, rows: any[]): Promise<any[]> {
        const contacts = await prisma.contact.findMany({
            where: { sessionId: dbSessionId },
            select: {
                jid: true, lid: true, remoteJidAlt: true,
                name: true, notify: true, verifiedName: true,
                profilePic: true, data: true
            }
        });
        const known = new Map<string, Set<string>>();
        const byJid = new Map<string, typeof contacts>();
        const isPn = (jid: string) => /^\\d+@(s\\.whatsapp\\.net|c\\.us)$/.test(jid);
        const isLid = (jid: string) => /^\\d+(?::\\d+)?@lid$/.test(jid);
        const normalized = (jid: string) => jid.replace("@c.us", "@s.whatsapp.net");
        for (const c of contacts) {
            const data = (c.data && typeof c.data === "object") ? c.data as Record<string, any> : {};
            const values = [c.jid, c.lid, c.remoteJidAlt, data.phoneNumber, data.pnJid]
                .filter((jid): jid is string => typeof jid === "string" && (isPn(jid) || isLid(jid)))
                .map(normalized);
            for (const item of values) {
                if (!known.has(item)) known.set(item, new Set());
                if (!byJid.has(item)) byJid.set(item, []);
                byJid.get(item)!.push(c);
                for (const alt of values) known.get(item)!.add(alt);
            }
        }

        const out: any[] = [];
        const seen = new Map<string, any>();
        for (const row of rows) {
            const candidates = new Set<string>([normalized(row.jid)]);
            const queue = [normalized(row.jid)];
            while (queue.length) {
                const item = queue.pop()!;
                for (const alias of known.get(item) || []) {
                    if (!candidates.has(alias)) {
                        candidates.add(alias);
                        queue.push(alias);
                    }
                }
            }
            const phones = [...candidates].filter(isPn);
            const phoneJid = phones.length ? phones.sort()[0] : "";
            const canonical = phoneJid || [...candidates].sort()[0];
            const related = [...candidates].flatMap(jid => byJid.get(jid) || []);
            const saved = related.find(c => c.name && c.name !== c.notify)?.name;
            const display = saved || related.find(c => c.verifiedName)?.verifiedName ||
                related.find(c => c.name)?.name || related.find(c => c.notify)?.notify ||
                row.name || row.notify || null;
            const photo = related.find(c => c.profilePic)?.profilePic || row.profilePic;
            const enriched = {
                ...row,
                jid: canonical, phoneJid, aliases: [...candidates],
                name: display, notify: related.find(c => c.notify)?.notify || row.notify,
                profilePic: photo,
            };
            const previous = seen.get(canonical);
            if (!previous) {
                seen.set(canonical, enriched);
                out.push(enriched);
            } else {
                const newest = (enriched.lastMessage?.timestamp || "") >
                    (previous.lastMessage?.timestamp || "");
                const merged = { ...previous, ...enriched,
                    lastMessage: newest ? enriched.lastMessage : previous.lastMessage,
                    aliases: [...new Set([...previous.aliases, ...enriched.aliases])],
                };
                seen.set(canonical, merged);
                out[out.indexOf(previous)] = merged;
            }
        }
        return out.sort((a, b) => String(b.lastMessage?.timestamp || "")
            .localeCompare(String(a.lastMessage?.timestamp || "")));
    }

"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=pathlib.Path, default=pathlib.Path("/srv/projetos/wa-akg")
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="verifica os patches sem escrever arquivos",
    )
    args = parser.parse_args()
    source = args.source.resolve()
    patch_dir = pathlib.Path(__file__).resolve().parent
    edits = prepare(source, patch_dir)
    changing = [
        (path, new) for path, new in edits.items()
        if not path.exists() or path.read_text(encoding="utf-8") != new
    ]
    if not changing:
        print("WA-AKG já contém todas as alterações. Nenhuma escrita necessária.")
        return
    print("Arquivos a atualizar:")
    for path, _ in changing:
        print("  -", path.relative_to(source))
    if args.dry_run:
        print("Verificação concluída; nenhum arquivo modificado.")
        return
    # Back up modified files (never DB/auth credentials) before the first write.
    backup = source / ".emeca-backups" / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for path, new in changing:
        if path.exists():
            backup_path = backup / path.relative_to(source)
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new, encoding="utf-8")
    print("Código atualizado. Originais em:", backup)
    print("NÃO foram alterados banco, volumes, sessão ou credenciais.")
    print("Recompile e teste o WA-AKG antes de trocar o contêiner ativo.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("ERRO:", error, file=sys.stderr)
        sys.exit(1)
