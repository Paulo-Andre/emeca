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

    let backfillStarted = false;
    async function backfillKnownLids(): Promise<void> {
        if (backfillStarted) return;
        backfillStarted = true;
        const dbSessionId = await sessionDbId();
        if (!dbSessionId) {
            backfillStarted = false;
            return;
        }

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
    }

    // Reconcile old contacts as soon as the existing session reconnects.
    // No new QR code, logout or credential reset is performed.
    sock.ev.on("connection.update", update => {
        if (update.connection === "open") {
            quietly(backfillKnownLids(), "backfill stored LID mappings");
        }
    });

    // The upstream store handles general contact sync. This listener preserves
    // phoneNumber/lid fields emitted by Baileys 7 which the original drops.
    sock.ev.on("contacts.upsert", contacts => {
        quietly(Promise.all(contacts.map(contact => syncContact(contact as ContactLike))), "contacts.upsert");
    });
    sock.ev.on("contacts.update", contacts => {
        quietly(Promise.all(contacts.map(contact => syncContact(contact as ContactLike))), "contacts.update");
    });
    sock.ev.on("messaging-history.set", history => {
        quietly(Promise.all((history.contacts || []).map(contact => syncContact(contact as ContactLike))), "history contacts");
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
