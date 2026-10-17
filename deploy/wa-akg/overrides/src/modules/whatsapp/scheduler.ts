import { prisma } from "@/lib/prisma";
import { waManager } from "./manager";
import { logger } from "@/lib/logger";

const checkScheduledMessages = async () => {
    try {
        const now = new Date();
        logger.debug("Scheduler", `Checking for messages due before ${now.toISOString()}...`);

        const pendingMessages = await prisma.scheduledMessage.findMany({
            where: {
                status: "PENDING",
                sendAt: { lte: now }
            },
            include: {
                // ScheduledMessage.sessionId stores Session.id (internal cuid).
                // waManager is keyed by Session.sessionId (public WhatsApp ID).
                session: { select: { sessionId: true } },
            },
            orderBy: { sendAt: "asc" },
            take: 100,
        });

        if (pendingMessages.length > 0) {
            logger.info("Scheduler", `Found ${pendingMessages.length} pending messages.`);
        }

        for (const msg of pendingMessages) {
            const waSessionId = msg.session.sessionId;
            const instance = waManager.getInstance(waSessionId);

            if (instance?.socket && instance.status === "CONNECTED") {
                try {
                    let content: any = {};
                    if (msg.mediaUrl) {
                        const url = msg.mediaUrl;
                        const type = msg.mediaType || 'image'; // Default to image if null

                        const res = await fetch(url);
                        if (!res.ok) throw new Error(`Failed to fetch media from URL: ${res.status} ${res.statusText}`);
                        const buffer = Buffer.from(await res.arrayBuffer());

                        if (type === 'video') {
                            content = { video: buffer, caption: msg.content };
                        } else if (type === 'document') {
                            content = { document: buffer, caption: msg.content, fileName: url.split('/').pop() || 'file', mimetype: 'application/octet-stream' };
                        } else {
                            content = { image: buffer, caption: msg.content };
                        }
                    } else {
                        content = { text: msg.content };
                    }

                    const sent = await instance.socket.sendMessage(msg.jid, content);
                    if (!sent?.key?.id) {
                        throw new Error("WhatsApp não confirmou o envio agendado.");
                    }

                    await prisma.scheduledMessage.update({
                        where: { id: msg.id },
                        data: { status: "SENT" }
                    });
                    logger.success("Scheduler", `Msg ${msg.id} sent to ${msg.jid}`);

                } catch (err) {
                    logger.error("Scheduler", `Failed to send scheduled msg ${msg.id}`, err);
                    await prisma.scheduledMessage.update({
                        where: { id: msg.id },
                        data: { status: "FAILED" }
                    });
                }
            } else {
                logger.warn("Scheduler", `Session ${waSessionId} not connected for scheduled msg ${msg.id}; pendente para retry`);
                // Optionally mark as failed or leave pending
            }
        }
    } catch (e) {
        logger.error("Scheduler", "Error executing scheduler loop:", e);
    }
};

let schedulerStarted = false;
let isChecking = false;

export function startScheduler() {
    if (schedulerStarted) return;
    schedulerStarted = true;
    logger.info("Scheduler", "Starting Message Scheduler...");

    const safeCheck = async () => {
        if (isChecking) return;
        isChecking = true;
        try {
            await checkScheduledMessages();
        } finally {
            isChecking = false;
        }
    };
    void safeCheck();
    setInterval(() => void safeCheck(), 30 * 1000);
}
