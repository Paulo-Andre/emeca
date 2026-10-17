import { prisma } from "@/lib/prisma";
import { logger } from "@/lib/logger";
import type { WASocket } from "@whiskeysockets/baileys";

const isLid = (jid: unknown): jid is string =>
    typeof jid === "string" && /^[0-9]+(?:[:][0-9]+)?@lid$/.test(jid);

const isPhone = (jid: unknown): jid is string =>
    typeof jid === "string" && /^[0-9]+(?:[:][0-9]+)?@(s\.whatsapp\.net|c\.us)$/.test(jid);

const phone = (jid: string) => jid.replace("@c.us", "@s.whatsapp.net");

type ContactLike = Record<string, any>;

/** Complements the original WA-AKG stores without accessing users' phonebooks. */
export function bindEmecaContactIdentity(sock: WASocket, sessionId: string): void {
    async function sessionDbId(): Promise<string | null> {
        const session = await prisma.session.findUnique({
            where: { sessionId }, select: { id: true }
        });
        return session?.id || null;
    }

    async function persistPair(lid: string, pn: string): Promise<void> {
        if (!isLid(lid) || !isPhone(pn)) return;
        const dbSessionId = await sessionDbId();
        if (!dbSessionId) return;
        const pnJid = phone(pn);
        await prisma.$transaction([
            prisma.contact.upsert({
                where: { sessionId_jid: { sessionId: dbSessionId, jid: lid } },
                create: { sessionId: dbSessionId, jid: lid, lid, remoteJidAlt: pnJid },
                update: { lid, remoteJidAlt: pnJid }
            }),
            prisma.contact.upsert({
                where: { sessionId_jid: { sessionId: dbSessionId, jid: pnJid } },
                create: { sessionId: dbSessionId, jid: pnJid, lid },
                update: { lid }
            })
        ]);
    }

    async function syncContact(contact: ContactLike): Promise<void> {
        const jid = String(contact.id || contact.jid || "");
        if (!jid || jid.includes("@g.us") || jid.includes("@broadcast")) return;
        const dbSessionId = await sessionDbId();
        if (!dbSessionId) return;

        const lid = isLid(contact.lid) ? contact.lid : (isLid(jid) ? jid : undefined);
        const phoneJid = [
            contact.phoneNumber, contact.pnJid, contact.remoteJidAlt, contact.phoneJid,
            isPhone(jid) ? jid : null
        ].find(isPhone);
        const savedName = String(contact.name || contact.verifiedName || "").trim();
        const notify = String(contact.notify || contact.pushName || "").trim();
        const picture = typeof contact.imgUrl === "string" ? contact.imgUrl : "";
        // Persist only serializable identity fields, never full Baileys objects
        // (which may include binary payloads not accepted by Prisma JSON).
        const original = {
            id: jid,
            lid: lid || null,
            phoneNumber: phoneJid ? phone(phoneJid) : null,
            name: savedName || null,
            verifiedName: contact.verifiedName || null,
            notify: notify || null
        };

        await prisma.contact.upsert({
            where: { sessionId_jid: { sessionId: dbSessionId, jid } },
            create: {
                sessionId: dbSessionId, jid,
                lid: lid || undefined,
                remoteJidAlt: phoneJid ? phone(phoneJid) : undefined,
                name: savedName || undefined,
                notify: notify || undefined,
                verifiedName: contact.verifiedName || undefined,
                profilePic: picture || undefined,
                data: original
            },
            update: {
                lid: lid || undefined,
                remoteJidAlt: phoneJid ? phone(phoneJid) : undefined,
                name: savedName || undefined,
                notify: notify || undefined,
                verifiedName: contact.verifiedName || undefined,
                profilePic: picture || undefined,
                data: original
            }
        });
        if (lid && phoneJid) await persistPair(lid, phoneJid);
        // A contact can be synced as only @lid, while its PN already exists
        // in the encrypted Signal store from an earlier sync.
        if (lid && !phoneJid) await resolveStoredLid(lid);
    }

    function quietly(promise: Promise<unknown>, label: string): void {
        promise.catch(error => logger.error("EMECA Identity", label, error));
    }

    /**
     * Baileys 7 keeps PN↔LID links in its encrypted Signal key store.
     * The original WA-AKG never queried this store. Looking it up does not
     * request anyone's private contacts, guess a phone number, or reconnect.
     */
    async function resolveStoredLid(lid: string): Promise<boolean> {
        if (!isLid(lid)) return false;
        const mappingStore = (sock as any).signalRepository?.lidMapping;
        if (!mappingStore || typeof mappingStore.getPNForLID !== "function") return false;
        const mapped = await mappingStore.getPNForLID(lid);
        if (!isPhone(mapped)) return false;
        await persistPair(lid, mapped);
        return true;
    }

    // Every socket belongs to a single WA-AKG session. Run once after the
    // connection opens AND again after the full history has actually arrived:
    // on a first QR login the history usually arrives after connection=open.
    let backfillRunning = false;
    let backfillQueued = false;
    let lastBackfill = 0;
    let backfillTimer: ReturnType<typeof setTimeout> | null = null;

    function scheduleReconciliation(reason: string, delayMs = 10000): void {
        if (backfillTimer) clearTimeout(backfillTimer);
        backfillTimer = setTimeout(() => {
            backfillTimer = null;
            quietly(backfillKnownLids(reason), "automatic contact reconciliation");
        }, delayMs);
    }

    async function backfillKnownLids(reason: string): Promise<void> {
        if (backfillRunning) {
            backfillQueued = true;
            return;
        }
        // Avoid rescanning a large account with every batch of incoming contacts.
        if (Date.now() - lastBackfill < 30000) {
            scheduleReconciliation("recent sync", 35000);
            return;
        }
        backfillRunning = true;
        const dbSessionId = await sessionDbId();
        if (!dbSessionId) {
            backfillRunning = false;
            return;
        }
        try {
        // The WA-AKG stores historical LIDs in both Contacts and Messages.
        // Use bounded, local batches so reconnect is not blocked.
        const [contactRows, messageRows] = await Promise.all([
            prisma.contact.findMany({
                where: { sessionId: dbSessionId,
                    OR: [{ jid: { endsWith: "@lid" } }, { lid: { endsWith: "@lid" } }] },
                select: { jid: true, lid: true },
                take: 12000
            }),
            prisma.message.findMany({
                where: { sessionId: dbSessionId, remoteJid: { endsWith: "@lid" } },
                select: { remoteJid: true },
                distinct: ["remoteJid"],
                take: 12000
            })
        ]);
        const lids = [...new Set([
            ...contactRows.flatMap(c => [c.jid, c.lid]),
            ...messageRows.map(m => m.remoteJid)
        ].filter(isLid))];
        let resolved = 0;
        for (let i = 0; i < lids.length; i += 12) {
            const results = await Promise.all(lids.slice(i, i + 12).map(lid =>
                resolveStoredLid(lid).catch(() => false)
            ));
            resolved += results.filter(Boolean).length;
        }
        logger.info("EMECA Identity",
            "LID mappings recovered from existing Signal store: " +
            resolved + "/" + lids.length);

        // Em mensagens diretas antigas, o WA-AKG podia armazenar o LID
        // como remoteJid e o telefone original como senderJid.
        // Só usamos pares do MESMO registro de mensagem recebida.
        const historicalPairs = await prisma.message.findMany({
            where: {
                sessionId: dbSessionId,
                fromMe: false,
                remoteJid: { endsWith: "@lid" },
                senderJid: { endsWith: "@s.whatsapp.net" }
            },
            select: { remoteJid: true, senderJid: true },
            distinct: ["remoteJid", "senderJid"],
            take: 20000
        });
        const phonesByLid = new Map<string, Set<string>>();
        const lidsByPhone = new Map<string, Set<string>>();
        for (const pair of historicalPairs) {
            if (!isLid(pair.remoteJid) || !isPhone(pair.senderJid)) continue;
            const pn = phone(pair.senderJid);
            if (!phonesByLid.has(pair.remoteJid)) phonesByLid.set(pair.remoteJid, new Set());
            phonesByLid.get(pair.remoteJid)!.add(pn);
            if (!lidsByPhone.has(pn)) lidsByPhone.set(pn, new Set());
            lidsByPhone.get(pn)!.add(pair.remoteJid);
        }
        const verified = [...phonesByLid.entries()]
            .filter(([lid, pns]) => {
                if (pns.size !== 1) return false;
                const pn = [...pns][0];
                return lidsByPhone.get(pn)?.size === 1 && isLid(lid);
            })
            .map(([lid, pns]) => ({ lid, pn: [...pns][0] }));
        let fromHistory = 0;
        for (let i = 0; i < verified.length; i += 12) {
            const results = await Promise.all(verified.slice(i, i + 12).map(
                ({ lid, pn }) => persistPair(lid, pn).then(() => true).catch(() => false)
            ));
            fromHistory += results.filter(Boolean).length;
        }
        logger.info("EMECA Identity",
            "LID mappings recovered from historical message pairs: " +
            fromHistory + "/" + phonesByLid.size +
            " (ambiguous pairs skipped: " + (phonesByLid.size - verified.length) + ")");
        lastBackfill = Date.now();
        logger.info("EMECA Identity",
            "Automatic contact reconciliation finished for " + sessionId + " (" + reason + ")");
        } finally {
            backfillRunning = false;
            if (backfillQueued) {
                backfillQueued = false;
                scheduleReconciliation("history completed while processing", 35000);
            }
        }
    }

    // Reconcile old contacts as soon as the existing session reconnects.
    // No new QR code, logout or credential reset is performed.
    sock.ev.on("connection.update", update => {
        if (update.connection === "open") {
            scheduleReconciliation("QR connected / socket opened", 8000);
        } else if (update.connection === "close" && backfillTimer) {
            clearTimeout(backfillTimer);
            backfillTimer = null;
        }
    });

    // Automatic import per connected session, without uploading files.
    // Limit concurrent upserts, since a new QR connection can supply thousands
    // of contacts and chats in a single Baileys history event.
    async function syncBatch(entries: ContactLike[], source: string): Promise<void> {
        let stored = 0;
        for (let i = 0; i < entries.length; i += 12) {
            const results = await Promise.allSettled(
                entries.slice(i, i + 12).map(contact => syncContact(contact))
            );
            stored += results.filter(item => item.status === "fulfilled").length;
            for (const result of results) {
                if (result.status === "rejected") {
                    logger.error("EMECA Identity", source, result.reason);
                }
            }
        }
        logger.info("EMECA Identity",
            "Automatic contacts synced from " + source + ": " + stored + "/" + entries.length);
    }

    sock.ev.on("contacts.upsert", contacts => {
        quietly(syncBatch(contacts as ContactLike[], "contacts.upsert"), "contacts.upsert");
    });
    sock.ev.on("contacts.update", contacts => {
        quietly(syncBatch(contacts as ContactLike[], "contacts.update"), "contacts.update");
    });
    sock.ev.on("messaging-history.set", history => {
        const entries = [
            ...((history.contacts || []) as ContactLike[]),
            ...((history.chats || []) as ContactLike[])
        ];
        quietly(
            syncBatch(entries, "messaging-history.set").then(() => {
                // First QR login may finish many seconds after connection=open.
                // Run again once history is complete to include newly saved LIDs.
                if (history.isLatest) scheduleReconciliation("initial history completed", 12000);
            }),
            "automatic history contacts"
        );
    });

    // Depending on the Baileys RC version this event may not fire. The
    // contact.phoneNumber and message.remoteJidAlt fallbacks remain essential.
    (sock.ev as any).on("lid-mapping.update", (update: any) => {
        const pairs: { lid: string; pn: string }[] = [];
        if (Array.isArray(update)) {
            for (const item of update) {
                if (item?.lid && item?.pn) pairs.push(item);
            }
        } else if (update && typeof update === "object") {
            if (update.lid && update.pn) pairs.push(update);
            else for (const [lid, pn] of Object.entries(update)) {
                if (typeof pn === "string") pairs.push({ lid, pn });
            }
        }
        quietly(Promise.all(pairs.map(({ lid, pn }) => persistPair(lid, pn))), "lid-mapping");
    });

    sock.ev.on("messages.upsert", ({ messages }) => {
        quietly(Promise.all(messages.map(async msg => {
            if (msg.key.fromMe || !msg.key.remoteJid) return;
            const jid = msg.key.remoteJid;
            const alt = msg.key.remoteJidAlt;
            if (isLid(jid) && isPhone(alt)) await persistPair(jid, alt);
            else if (isPhone(jid) && isLid(alt)) await persistPair(alt, jid);
            else if (isLid(jid)) await resolveStoredLid(jid);

            // Contact identity in group participant metadata, when available.
            const participant = msg.key.participant;
            const participantAlt = (msg.key as any).participantAlt;
            if (isLid(participant) && isPhone(participantAlt)) {
                await persistPair(participant, participantAlt);
            } else if (isPhone(participant) && isLid(participantAlt)) {
                await persistPair(participantAlt, participant);
            }
        })), "message phone aliases");
    });
}
