import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { waManager } from "@/modules/whatsapp/manager";
import { canAccessSession, getAuthenticatedUser } from "@/lib/api-auth";
import { unlink } from "node:fs/promises";
import path from "node:path";

/**
 * EMECA: Excluir definitivamente o histórico de UMA sessão já desvinculada.
 *
 * A exclusão é irreversível e só é permitida depois do logout real. Não pode
 * ser usada para pausas, falhas de rede ou contas ainda conectadas.
 * Não exclui outras sessões WA-AKG nem o cadastro escolar do Django.
 */
export async function POST(
    request: NextRequest,
    { params }: { params: Promise<{ sessionId: string }> }
) {
    const user = await getAuthenticatedUser(request);
    if (!user) {
        return NextResponse.json({ status: false, message: "Não autenticado" }, { status: 401 });
    }
    if (user.role !== "SUPERADMIN" && user.role !== "OWNER") {
        return NextResponse.json({ status: false, message: "Sem permissão para apagar histórico" }, { status: 403 });
    }

    const { sessionId } = await params;
    if (!/^[a-zA-Z0-9_-]{3,120}$/.test(sessionId)) {
        return NextResponse.json({ status: false, message: "Sessão inválida" }, { status: 400 });
    }
    if (!await canAccessSession(user.id, user.role, sessionId)) {
        return NextResponse.json({ status: false, message: "Sem acesso à sessão" }, { status: 403 });
    }

    const session = await prisma.session.findUnique({
        where: { sessionId }, select: { id: true, sessionId: true, status: true }
    });
    if (!session) {
        return NextResponse.json({ status: false, message: "Sessão não encontrada" }, { status: 404 });
    }

    // Um status desconectado por rede não equivale a LOGGED_OUT.
    if (session.status !== "LOGGED_OUT") {
        return NextResponse.json({
            status: false,
            message: "O WhatsApp deve ser desvinculado primeiro; pausa não permite exclusão."
        }, { status: 409 });
    }
    const instance = waManager.getInstance(sessionId);
    if (instance && instance.status === "CONNECTED") {
        return NextResponse.json({
            status: false, message: "Aguardando encerramento da conexão WhatsApp."
        }, { status: 409 });
    }

    try {
        // Somente mídia guardada nas mensagens DESTA sessão. Nunca utilizar
        // um prefixo amplo em disco (poderia apagar arquivos de outra conta).
        const mediaRows = await prisma.message.findMany({
            where: { sessionId: session.id, mediaUrl: { not: null } },
            select: { mediaUrl: true }
        });
        const filenames = [...new Set(mediaRows
            .map(row => row.mediaUrl)
            .filter((url): url is string => typeof url === "string" && url.startsWith("/api/media/"))
            .map(url => url.slice("/api/media/".length))
            .filter(filename =>
                filename.startsWith(sessionId + "-") &&
                /^[a-zA-Z0-9._-]+$/.test(filename) &&
                filename === path.basename(filename)
            )
        )];

        // O Session do Prisma possui onDelete: Cascade para mensagens,
        // contatos, grupos, respostas automáticas etc. Label, AuthState e
        // BroadcastLog não possuem FK para Session e precisam ser apagados
        // explicitamente. Tudo ocorre na MESMA transação.
        const counts = await prisma.$transaction(async tx => {
            const messages = await tx.message.count({ where: { sessionId: session.id } });
            const contacts = await tx.contact.count({ where: { sessionId: session.id } });
            const groups = await tx.group.count({ where: { sessionId: session.id } });
            await tx.label.deleteMany({ where: { sessionId } });
            await tx.authState.deleteMany({ where: { sessionId } });
            await tx.broadcastLog.deleteMany({ where: { sessionId } });
            await tx.session.delete({ where: { id: session.id } });
            return { messages, contacts, groups };
        }, { timeout: 60000, maxWait: 10000 });

        let removedMedia = 0;
        let missingMedia = 0;
        let mediaErrors = 0;
        for (const filename of filenames) {
            try {
                await unlink(path.join(process.cwd(), "data", "media", filename));
                removedMedia++;
            } catch (error: any) {
                if (error?.code === "ENOENT") missingMedia++;
                else mediaErrors++;
            }
        }

        return NextResponse.json({
            status: true,
            message: "Histórico desta sessão excluído definitivamente",
            data: {
                ...counts,
                removedMedia, missingMedia, mediaErrors,
                mediaWarning: mediaErrors > 0
            }
        });
    } catch (error) {
        console.error("[EMECA] Falha ao excluir histórico da sessão WhatsApp", error);
        return NextResponse.json({
            status: false,
            message: "Erro ao excluir histórico desta sessão. A nova conta não deve ser conectada."
        }, { status: 500 });
    }
}
