import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { waManager } from "@/modules/whatsapp/manager";
import { getAuthenticatedUser, canAccessSession } from "@/lib/api-auth";

/**
 * Authenticated, read-only contact profile. It never changes a contact,
 * sends a message or interprets LID digits as a phone number.
 */
export async function GET(
    request: NextRequest,
    { params }: { params: Promise<{ sessionId: string; jid: string }> }
) {
    const { sessionId, jid: jidEncoded } = await params;
    const jid = decodeURIComponent(jidEncoded);
    if (!/^[0-9:-]{5,85}@(lid|s\.whatsapp\.net|c\.us|g\.us)$/.test(jid)) {
        return NextResponse.json({ status: false, error: "Invalid contact" }, { status: 400 });
    }
    const user = await getAuthenticatedUser(request);
    if (!user) {
        return NextResponse.json({ status: false, error: "Unauthorized" }, { status: 401 });
    }
    if (!await canAccessSession(user.id, user.role, sessionId)) {
        return NextResponse.json({ status: false, error: "Forbidden" }, { status: 403 });
    }
    const session = await prisma.session.findUnique({
        where: { sessionId }, select: { id: true }
    });
    if (!session) {
        return NextResponse.json({ status: false, error: "Session not found" }, { status: 404 });
    }
    const contact = await prisma.contact.findFirst({
        where: {
            sessionId: session.id,
            OR: [{ jid }, { lid: jid }, { remoteJidAlt: jid }]
        },
        select: {
            jid: true, lid: true, remoteJidAlt: true,
            name: true, notify: true, verifiedName: true
        }
    });
    let about: string | null = null;
    const instance = waManager.getInstance(sessionId);
    if (instance?.socket && typeof (instance.socket as any).fetchStatus === "function") {
        try {
            const fetchStatus = (instance.socket as any).fetchStatus.bind(instance.socket);
            const result = await Promise.race([
                fetchStatus(jid),
                new Promise<null>(resolve => setTimeout(() => resolve(null), 4000))
            ]);
            const value = Array.isArray(result) ? result[0]?.status : result?.status;
            if (typeof value === "string" && value.trim()) about = value.trim().slice(0, 300);
        } catch {
            // Privacy settings, offline contacts and Baileys versions may
            // prevent reading the About field. Do not invent a default.
        }
    }
    return NextResponse.json({
        status: true,
        data: {
            jid,
            name: contact?.name || null,
            notify: contact?.notify || null,
            verifiedName: contact?.verifiedName || null,
            about
        }
    });
}
