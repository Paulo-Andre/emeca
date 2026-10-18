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
import hashlib
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


def desativar_agendador_duplicado(manager_content: str) -> str:
    """WA-AKG: uma só instância de scheduler, sem reinicialização paralela.

    O servidor pode conter a alteração manual já feita: nesse caso respeita
    o arquivo como está. Mudanças desconhecidas são rejeitadas, nunca
    sobrescritas às cegas.
    """
    import_antigo = 'import { initScheduler } from "@/lib/cron";'
    chamada_antiga = '        initScheduler();'
    comentario = "        // Agendamento centralizado em src/modules/whatsapp/scheduler.ts"
    identificador = "Agendamento centralizado em src/modules/whatsapp/scheduler.ts"

    if "initScheduler" not in manager_content:
        if identificador not in manager_content:
            raise RuntimeError(
                "manager.ts sem marcador conhecido do agendador. "
                "Revise o diff; código não será sobrescrito."
            )
        return manager_content

    if manager_content.count(import_antigo) != 1 or manager_content.count(chamada_antiga) != 1:
        raise RuntimeError(
            "manager.ts usa uma forma desconhecida do agendador antigo. "
            "É necessário revisar o código antes da implantação."
        )
    resultado = manager_content.replace(import_antigo, "", 1)
    resultado = resultado.replace(chamada_antiga, comentario, 1)
    if "initScheduler" in resultado:
        raise RuntimeError("Há outras referências a initScheduler em manager.ts.")
    return resultado


def prepare(source: pathlib.Path, patch_dir: pathlib.Path):
    manager = source / "src/modules/whatsapp/manager.ts"
    instance = source / "src/modules/whatsapp/instance.ts"
    index = source / "src/modules/whatsapp/store/index.ts"
    contact_store = source / "src/modules/whatsapp/store/contacts.ts"
    chat_service = source / "src/modules/whatsapp/chat.service.ts"
    chat_route = source / "src/app/api/chat/[sessionId]/route.ts"
    messages_route = source / "src/app/api/chat/[sessionId]/[jid]/route.ts"
    contacts_route = source / "src/app/api/contacts/[sessionId]/route.ts"
    overlay_file = patch_dir / "overrides/src/modules/whatsapp/store/emeca-identity.ts"
    target_file = source / "src/modules/whatsapp/store/emeca-identity.ts"
    profile_route_overlay = patch_dir / "overrides/src/app/api/chat/[sessionId]/[jid]/contact-profile/route.ts"
    profile_route_target = source / "src/app/api/chat/[sessionId]/[jid]/contact-profile/route.ts"
    purge_route_overlay = patch_dir / "overrides/src/app/api/sessions/[sessionId]/purge-history/route.ts"
    purge_route_target = source / "src/app/api/sessions/[sessionId]/purge-history/route.ts"
    group_route_overlay = patch_dir / "overrides/src/app/api/groups/[sessionId]/create/route.ts"
    group_route_target = source / "src/app/api/groups/[sessionId]/create/route.ts"
    scheduler_overlay = patch_dir / "overrides/src/modules/whatsapp/scheduler.ts"
    scheduler_target = source / "src/modules/whatsapp/scheduler.ts"

    required = [manager, instance, index, contact_store, chat_service, chat_route, messages_route, contacts_route, overlay_file, profile_route_overlay, purge_route_overlay, group_route_overlay, scheduler_overlay, group_route_target, scheduler_target]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise RuntimeError("Arquivos não encontrados: " + ", ".join(missing))
    if target_file.exists() and target_file.read_bytes() != overlay_file.read_bytes():
        # Only upgrade the exact v1 overlay previously delivered by EMECA.
        # Other custom local changes are NEVER overwritten automatically.
        old = target_file.read_bytes()
        git_blob = hashlib.sha1(
            b"blob " + str(len(old)).encode() + b"\0" + old
        ).hexdigest()
        approved_prior_versions = {
            "3e44cfba9b5ea22bdbab55cdd6bbe7342244cb58",
            "0ce64f8730400cbdc52c2c47d56001d05f7f0397",
            "62e2800a7d6a4a527894ee186d9165f0e6d18c87",
        }
        if git_blob not in approved_prior_versions:
            raise RuntimeError(
                "emeca-identity.ts contém alterações locais desconhecidas. "
                "Nenhum arquivo foi modificado; revise o backup e o diff."
            )

    edits: dict[pathlib.Path, str] = {}
    edits[manager] = desativar_agendador_duplicado(manager.read_text(encoding="utf-8"))

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

    # The upstream contacts.ts originally treated pushName/notify as the
    # address-book name. Preserve saved names and let the EMECA listener
    # import PN/LID mappings and profile names in separate columns.
    value = contact_store.read_text(encoding="utf-8")
    value = substitute(
        value,
        'name: update.name || update.notify,',
        'name: update.name || undefined,',
        "nome salvo em contacts.update",
    )
    value = substitute(
        value,
        'name: contact.name || contact.notify,',
        'name: contact.name || undefined,',
        "nome salvo em messaging-history.set",
    )
    edits[contact_store] = value

    value = chat_service.read_text(encoding="utf-8")
    value = substitute(
        value,
        '        dbSessionId: string,\n        limit = 50,\n        before?: string,\n        search?: string',
        '        dbSessionId: string,\n        limit = 300,\n        before?: string,\n        search?: string',
        "limite padrão de chats",
    )
    if "private static async enrichEmecaChats" in value:
        # Atualizar somente a implementação que o próprio EMECA adicionou
        # anteriormente. O patch antigo não continha profileNames.
        first = value.find(
            '    /**\n     * Normaliza os metadados para EMECA sem inventar telefones.'
        )
        last = value.find('    /**\n     * Get messages for a specific chat', first)
        existing = value[first:last] if first >= 0 and last > first else ""
        if not existing or "const known = new Map<string, Set<string>>();" not in existing:
            raise RuntimeError("Método de identificação foi alterado localmente; revise manualmente.")
        if existing != ENRICH_METHOD:
            value = value[:first] + ENRICH_METHOD + value[last:]
    else:
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

    value = messages_route.read_text(encoding="utf-8")
    value = substitute(
        value,
        '        const messages = await prisma.message.findMany({\n'
        '            where: {\n'
        '                sessionId: dbSessionId,\n'
        '                remoteJid: decodedJid\n'
        '            },\n'
        '            orderBy: { timestamp: \'desc\' }, // Fetch NEWEST first\n'
        '            take: 100\n'
        '        });\n\n'
        '        // Reverse to show oldest -> newest\n'
        '        messages.reverse();',
        '        const params = new URL(request.url).searchParams;\n'
        '        const wanted = Number.parseInt(params.get("limit") || "100", 10);\n'
        '        const limit = Number.isFinite(wanted) ? Math.max(1, Math.min(wanted, 500)) : 100;\n'
        '        const before = params.get("before");\n'
        '        if (before && Number.isNaN(Date.parse(before))) {\n'
        '            return NextResponse.json({ status: false, error: "Invalid cursor" }, { status: 400 });\n'
        '        }\n'
        '        // The same conversation may have been stored under phone and LID.\n'
        '        const contact = await prisma.contact.findFirst({\n'
        '            where: { sessionId: dbSessionId, OR: [\n'
        '                { jid: decodedJid }, { lid: decodedJid },\n'
        '                { remoteJidAlt: decodedJid }\n'
        '            ] },\n'
        '            select: { jid: true, lid: true, remoteJidAlt: true }\n'
        '        });\n'
        '        const aliasJids = [...new Set([\n'
        '            decodedJid, contact?.jid, contact?.lid, contact?.remoteJidAlt\n'
        '        ].filter((id): id is string => typeof id === "string" && !!id))];\n'
        '        const messages = await prisma.message.findMany({\n'
        '            where: { sessionId: dbSessionId,\n'
        '                remoteJid: { in: aliasJids },\n'
        '                ...(before ? { timestamp: { lt: new Date(before) } } : {})\n'
        '            },\n'
        '            orderBy: { timestamp: "desc" },\n'
        '            take: limit + 1\n'
        '        });\n'
        '        const hasMore = messages.length > limit;\n'
        '        if (hasMore) messages.pop();\n'
        '        messages.reverse();\n'
        '        const nextBefore = messages.length ? messages[0].timestamp.toISOString() : null;',
        "paginação e resolução de aliases do histórico",
    )
    value = substitute(
        value,
        'return NextResponse.json({ status: true, data: enrichedMessages });',
        'return NextResponse.json({ status: true, data: enrichedMessages, meta: { hasMore, nextBefore } });',
        "cursor de mensagens de grupo",
    )
    value = substitute(
        value,
        'return NextResponse.json({ status: true, data: messages });',
        'return NextResponse.json({ status: true, data: messages, meta: { hasMore, nextBefore } });',
        "cursor de mensagens",
    )
    edits[messages_route] = value

    value = contacts_route.read_text(encoding="utf-8")
    value = substitute(
        value,
        '            data: contacts,',
        '            data: contacts.map(contact => {\n'
        '                const raw = (contact.data && typeof contact.data === "object")\n'
        '                    ? contact.data as Record<string, any> : {};\n'
        '                const candidates = [contact.jid, contact.lid, contact.remoteJidAlt,\n'
        '                    raw.phoneNumber, raw.pnJid].filter(\n'
        '                    (jid): jid is string => typeof jid === "string" && !!jid\n'
        '                );\n'
        '                const aliases = [...new Set(candidates.map(jid =>\n'
        '                    jid.replace("@c.us", "@s.whatsapp.net")))];\n'
        '                const phoneJid = aliases.find(jid =>\n'
        '                    /^[0-9]+@s\\.whatsapp\\.net$/.test(jid)) || "";\n'
        '                return { ...contact, aliases, phoneJid,\n'
        '                    displayName: contact.name || contact.verifiedName ||\n'
        '                        contact.notify || (phoneJid ? phoneJid.split("@")[0] : null)\n'
        '                };\n'
        '            }),',
        "formato completo de contatos",
    )
    edits[contacts_route] = value

    if profile_route_target.exists() and profile_route_target.read_bytes() != profile_route_overlay.read_bytes():
        raise RuntimeError(
            "O endpoint contact-profile/route.ts foi personalizado no servidor. "
            "Para preservar suas alterações, revise o diff antes de continuar."
        )
    edits[profile_route_target] = profile_route_overlay.read_text(encoding="utf-8")
    if purge_route_target.exists() and purge_route_target.read_bytes() != purge_route_overlay.read_bytes():
        raise RuntimeError(
            "purge-history/route.ts já existe e está diferente do módulo EMECA. "
            "Revisar o diff antes de atualizar para não sobrescrever código local."
        )
    edits[purge_route_target] = purge_route_overlay.read_text(encoding="utf-8")
    for original, patch in [
        (group_route_target, group_route_overlay),
        (scheduler_target, scheduler_overlay),
    ]:
        desired = patch.read_text(encoding="utf-8")
        current = original.read_text(encoding="utf-8")
        if current == desired:
            continue
        # Strictly permit updating only the corresponding upstream baseline.
        # Never overwrite unknown local edits made by another administrator.
        approved = {
            "src/app/api/groups/[sessionId]/create/route.ts": {
                "3d40ca6f3151b6cc8419bd1588f4bfd9112d535a",
            },
            "src/modules/whatsapp/scheduler.ts": {
                "626d731a9bf199a21597c25f20ee0b9dc1cc8862",
                # Version of the EMECA scheduler already present on
                # some installations before atomic claiming was added.
                "4599cb13a2c9be2a3143328ffcd3e4113ad92123",
            },
        }[str(original.relative_to(source))]
        digest = hashlib.sha1(
            b"blob " + str(len(current.encode("utf-8"))).encode() +
            b"\0" + current.encode("utf-8")
        ).hexdigest()
        if digest not in approved:
            raise RuntimeError(
                f"{original.relative_to(source)} tem alterações locais não reconhecidas. "
                "Patcher não sobrescreveu o arquivo; confira o diff e faça backup."
            )
        edits[original] = desired
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
        // Contacts without an address-book name can still have a verified
        // display-name in an incoming message. Read one latest pushName per
        // remote JID in a bounded batch rather than one API call per chat.
        const unresolvedLids = rows
            .filter(row => row.jid?.endsWith("@lid") && !row.name && !row.notify)
            .map(row => row.jid as string);
        const profileNames = new Map<string, string>();
        if (unresolvedLids.length) {
            const recentSenders = await prisma.message.findMany({
                where: {
                    sessionId: dbSessionId, fromMe: false,
                    remoteJid: { in: unresolvedLids },
                    pushName: { not: null }
                },
                select: { remoteJid: true, pushName: true },
                orderBy: { timestamp: "desc" },
                distinct: ["remoteJid"],
                take: Math.min(unresolvedLids.length, 5000)
            });
            for (const message of recentSenders) {
                const name = (message.pushName || "").trim();
                if (name && name.length <= 160) profileNames.set(message.remoteJid, name);
            }
        }
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
                row.name || row.notify ||
                [...candidates].map(id => profileNames.get(id)).find(Boolean) || null;
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
