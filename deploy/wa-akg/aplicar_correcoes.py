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






def corrigir_broadcast_anexo(value: str) -> str:
    """Aceita imagem/PDF em broadcast sem modificar envio somente texto.

    O envio permanece uma mensagem individual por destinatário. WA-AKG só
    confirma que o lote foi iniciado; a fila interna não garante entrega.
    """
    value = substitute(
        value,
        '    message: z.string().min(1),',
        '    message: z.string().max(4000),',
        "legenda opcional para broadcast com arquivo",
    )
    value = substitute(
        value,
        '        const body = await request.json();',
        '        const multipart = (request.headers.get("content-type") || "")\n'
        '            .includes("multipart/form-data");\n'
        '        const form = multipart ? await request.formData() : null;\n'
        '        const upload = form?.get("file");\n'
        '        const mediaFile = upload instanceof File ? upload : null;\n'
        '        const body = multipart ? {\n'
        '            recipients: JSON.parse(String(form?.get("recipients") || "[]")),\n'
        '            message: String(form?.get("message") || ""),\n'
        '            delay: Number(form?.get("delay") || 2000),\n'
        '        } : await request.json();',
        "recebimento multipart de campanhas",
    )
    value = substitute(
        value,
        '        const { recipients, message, delay } = parseResult.data;',
        '        const { recipients, message, delay } = parseResult.data;\n'
        '        if ((!message.trim() && !mediaFile) || recipients.length === 0) {\n'
        '            return NextResponse.json({ status: false,\n'
        '                error: "Mensagem ou arquivo e destinatários são obrigatórios." },\n'
        '                { status: 400 });\n'
        '        }\n'
        '        if (mediaFile && (mediaFile.size < 1 || mediaFile.size > 25 * 1024 * 1024 ||\n'
        '            !["image/jpeg", "image/png", "image/webp", "application/pdf"].includes(mediaFile.type))) {\n'
        '            return NextResponse.json({ status: false,\n'
        '                error: "Anexe JPG, PNG, WEBP ou PDF de até 25 MB." },\n'
        '                { status: 400 });\n'
        '        }',
        "validar imagem/PDF e destinatários",
    )
    value = substitute(
        value,
        '                message,\n                total: recipients.length,',
        '                message: message || (mediaFile ? "[anexo]" : ""),\n                total: recipients.length,',
        "registro do lote de arquivos",
    )
    value = substitute(
        value,
        '        const messageContent: AnyMessageContent = { text: message };',
        '        const mediaBuffer = mediaFile ? Buffer.from(await mediaFile.arrayBuffer()) : null;\n'
        '        const messageContent: AnyMessageContent = mediaBuffer && mediaFile\n'
        '            ? mediaFile.type === "application/pdf"\n'
        '                ? { document: mediaBuffer, mimetype: "application/pdf",\n'
        '                    fileName: "documento.pdf", caption: message || undefined }\n'
        '                : { image: mediaBuffer, mimetype: mediaFile.type,\n'
        '                    caption: message || undefined }\n'
        '            : { text: message };',
        "conteúdo do broadcast com mídia",
    )
    return value


def corrigir_resposta_envio_midia(value: str) -> str:
    """Não transformar envio de mídia confirmado em HTTP 500 por serialização.

    O Baileys pode retornar protobufs, buffers e BigInts. O endpoint original
    tenta serializar tudo após sendMessage; isso pode gerar falso erro mesmo
    quando o documento já foi transmitido. Não introduz qualquer reenvio.
    """
    # O passo de diagnóstico acrescenta `stage = "ACK"` DENTRO da saída
    # gerada pelo primeiro substitute(). Isso torna o marcador completo
    # anterior invisível numa segunda aplicação. Reconheça a versão final
    # somente quando TODOS os marcadores de segurança estiverem presentes.
    marcador = "        // EMECA: acknowledge with a JSON-safe identifier only. Baileys"
    if marcador in value:
        obrigatorios = (
            '    let stage = "AUTH";',
            '        stage = "MULTIPART";',
            '        stage = "BUFFER";',
            '        stage = "SEND";',
            '        stage = "ACK";',
            '        if (!messageId) {',
            '                error: "MEDIA_ACK_MISSING"',
            '            data: { messageId } });',
            '        console.error("Media send error (sanitized)", {',
            '            code: publicCode, name: safeName, statusCode, stage',
            '            message: "Falha no envio de mídia (" + publicCode + ", etapa " + stage + ").",',
        )
        faltantes = [marker for marker in obrigatorios if value.count(marker) != 1]
        if faltantes or value.count(marcador) != 1:
            raise RuntimeError(
                "Endpoint de mídia EMECA com patch parcial ou personalizado; "
                "nenhum arquivo será alterado. Marcadores inconsistentes: "
                + str(len(faltantes))
            )
        return value
    value = substitute(
        value,
        '        return NextResponse.json({ status: true, message: "Operation successful", data: sent });',
        '        // EMECA: acknowledge with a JSON-safe identifier only. Baileys\n'
        '        // may return buffers/BigInt/protobufs that cannot be serialized.\n'
        '        // Do NOT repeat a send when the acknowledgement fails.\n'
        '        const messageId = typeof sent?.key?.id === "string" ? sent.key.id : null;\n'
        '        if (!messageId) {\n'
        '            // The send may be ambiguous: never retry automatically.\n'
        '            return NextResponse.json({ status: false,\n'
        '                message: "Envio sem identificador de confirmação. Verifique o destinatário antes de repetir.",\n'
        '                error: "MEDIA_ACK_MISSING" }, { status: 502 });\n'
        '        }\n'
        '        return NextResponse.json({ status: true, message: "Operation successful",\n'
        '            data: { messageId } });',
        "resposta JSON segura para mídia",
    )
    value = substitute(
        value,
        '    } catch (e) {\n'
        '        console.error("Media send error", e);\n'
        '        return NextResponse.json({ status: false, message: "Failed to send media", error: "Failed to send media" }, { status: 500 });\n'
        '    }',
        '    } catch (e: any) {\n'
        '        // EMECA: the original route hid every cause behind one generic\n'
        '        // error. Never log the PDF, caption, recipient, headers, or tokens.\n'
        '        const rawCode = typeof e?.code === "string" ? e.code :\n'
        '            (typeof e?.cause?.code === "string" ? e.cause.code : "");\n'
        '        const safeCode = /^[A-Za-z][A-Za-z0-9_]{1,39}$/.test(rawCode)\n'
        '            ? rawCode.toUpperCase() : "MEDIA_SEND_FAILED";\n'
        '        const disconnected = typeof e?.message === "string" &&\n'
        '            e.message.includes("WhatsApp session is disconnected");\n'
        '        const publicCode = disconnected ? "MEDIA_SESSION_DISCONNECTED" : safeCode;\n'
        '        const safeName = typeof e?.name === "string" &&\n'
        '            /^[A-Za-z][A-Za-z0-9_]{1,39}$/.test(e.name) ? e.name : "Error";\n'
        '        const statusCode = typeof e?.output?.statusCode === "number"\n'
        '            ? e.output.statusCode : null;\n'
        '        console.error("Media send error (sanitized)", {\n'
        '            code: publicCode, name: safeName, statusCode\n'
        '        });\n'
        '        return NextResponse.json({ status: false,\n'
        '            message: "Falha no envio de mídia (" + publicCode + ").",\n'
        '            error: publicCode }, { status: disconnected ? 503 : 500 });\n'
        '    }',
        "diagnóstico seguro de envio de mídia",
    )
    value = substitute(
        value,
        '    try {\n        const user = await getAuthenticatedUser(request);',
        '    let stage = "AUTH";\n    try {\n'
        '        const user = await getAuthenticatedUser(request);',
        "estágio da autenticação do endpoint de mídia",
    )
    value = substitute(
        value,
        '        const formData = await request.formData();',
        '        stage = "MULTIPART";\n'
        '        const formData = await request.formData();',
        "estágio de leitura multipart",
    )
    value = substitute(
        value,
        '        const buffer = Buffer.from(await file.arrayBuffer());',
        '        stage = "BUFFER";\n'
        '        const buffer = Buffer.from(await file.arrayBuffer());',
        "estágio de leitura binária do PDF",
    )
    value = substitute(
        value,
        '        const sent = await ChatService.sendMediaMessage(',
        '        stage = "SEND";\n'
        '        const sent = await ChatService.sendMediaMessage(',
        "estágio de envio ao WhatsApp",
    )
    value = substitute(
        value,
        '        const messageId = typeof sent?.key?.id === "string" ? sent.key.id : null;',
        '        stage = "ACK";\n'
        '        const messageId = typeof sent?.key?.id === "string" ? sent.key.id : null;',
        "estágio de confirmação do gateway",
    )
    value = substitute(
        value,
        '            code: publicCode, name: safeName, statusCode',
        '            code: publicCode, name: safeName, statusCode, stage',
        "estágio nos registros sanitizados",
    )
    value = substitute(
        value,
        '            message: "Falha no envio de mídia (" + publicCode + ").",',
        '            message: "Falha no envio de mídia (" + publicCode + ", etapa " + stage + ").",',
        "estágio no erro exibido ao administrador",
    )
    value = substitute(
        value,
        '        const publicCode = disconnected ? "MEDIA_SESSION_DISCONNECTED" : safeCode;',
        '        const uploadAllHosts = e?.message === "Media upload failed on all hosts";\n'
        '        const publicCode = disconnected ? "MEDIA_SESSION_DISCONNECTED" :\n'
        '            uploadAllHosts ? "MEDIA_UPLOAD_ALL_HOSTS" : safeCode;',
        "diagnóstico do upload do Baileys",
    )
    return value




def corrigir_diagnostico_upload_instancia(value: str) -> str:
    """Captura somente a classe da falha de upload, nunca URL, token ou stack.

    Baileys registra a causa de cada host em logger.warn, mas a configuração
    de produção usa nível error. Preservamos esse nível e interceptamos
    EXCLUSIVAMENTE os avisos de upload, emitindo um código enumerado.
    """
    value = substitute(
        value,
        '        this.socket = makeWASocket({',
        '        // EMECA: observe apenas motivos tipificados de falha de upload.\n'
        '        // Nunca imprimir trace, URL assinada, token, JID nem conteúdo.\n'
        '        const baileysLogger = pino({ level: process.env.BAILEYS_LOG_LEVEL || "error" }) as any;\n'
        '        const previousWarn = baileysLogger.warn.bind(baileysLogger);\n'
        '        baileysLogger.warn = (details: any, text?: string) => {\n'
        '            if (typeof text === "string" && text.startsWith("Error in uploading to ")) {\n'
        '                const trace = typeof details?.trace === "string" ? details.trace : "";\n'
        '                const recognized = [\n'
        '                    "ENOTFOUND", "EAI_AGAIN", "ETIMEDOUT", "ECONNRESET",\n'
        '                    "ECONNREFUSED", "ENETUNREACH", "EHOSTUNREACH",\n'
        '                    "ERR_INVALID_ARG_TYPE", "ERR_TLS_CERT_ALTNAME_INVALID",\n'
        '                    "CERT_HAS_EXPIRED", "UNABLE_TO_VERIFY_LEAF_SIGNATURE",\n'
        '                    "SELF_SIGNED_CERT_IN_CHAIN", "HPE_CLOSED_CONNECTION"\n'
        '                ].find(code => trace.includes(code));\n'
        '                const reason = recognized || (\n'
        '                    trace.includes("Upload timeout") ? "UPLOAD_TIMEOUT" :\n'
        '                    trace.includes("upload failed, reason:") ? "UNEXPECTED_UPLOAD_RESPONSE" :\n'
        '                    "UNKNOWN_UPLOAD_ERROR"\n'
        '                );\n'
        '                console.error("WA-MEDIA-UPLOAD-DIAG", { reason });\n'
        '                return;\n'
        '            }\n'
        '            previousWarn(details, text);\n'
        '        };\n'
        '        this.socket = makeWASocket({',
        "diagnóstico sanitizado de hosts de upload",
    )
    value = substitute(
        value,
        '            logger: pino({ level: process.env.BAILEYS_LOG_LEVEL || "error" }) as any,',
        '            logger: baileysLogger,',
        "logger de mídia do socket",
    )
    return value


def corrigir_reconexao_instancia(value: str) -> str:
    """Uma conexão Baileys por sessão; descartar eventos/timers de sockets antigos.

    Não modifica o banco nem altera chaves de autenticação.
    """
    value = substitute(
        value,
        '    private reconnectCount: number = 0;',
        '    private reconnectCount: number = 0;\n'
        '    private initializingSocket: boolean = false;\n'
        '    private socketGeneration: number = 0;\n'
        '    private closeHandled: boolean = false;\n'
        '    private reconnectTimer: ReturnType<typeof setTimeout> | null = null;',
        "controle de instância e tentativas",
    )
    value = substitute(
        value,
        '    async init() {\n'
        '        const sessionData = await prisma.session.findUnique({',
        '    async init() {\n'
        '        if (this.isStopped || this.initializingSocket || (this.socket && !this.closeHandled)) return;\n'
        '        this.initializingSocket = true;\n'
        '        this.closeHandled = false;\n'
        '        const generation = ++this.socketGeneration;\n'
        '        try {\n'
        '            if (this.reconnectTimer) {\n'
        '                clearTimeout(this.reconnectTimer);\n'
        '                this.reconnectTimer = null;\n'
        '            }\n'
        '            const previousSocket = this.socket;\n'
        '            this.socket = null;\n'
        '            if (previousSocket) {\n'
        '                try { previousSocket.end(undefined); } catch { /* already closed */ }\n'
        '            }\n'
        '            await this.initializeSocket(generation);\n'
        '        } finally {\n'
        '            this.initializingSocket = false;\n'
        '        }\n'
        '    }\n\n'
        '    private async initializeSocket(generation: number) {\n'
        '        const sessionData = await prisma.session.findUnique({',
        "inicialização exclusiva do socket",
    )
    value = substitute(
        value,
        '        this.socket.ev.on("creds.update", saveCreds);\n\n'
        '        this.socket.ev.on("connection.update", async (update) => {\n'
        '            await this.handleConnectionUpdate(update);\n'
        '        });',
        '        this.socket.ev.on("creds.update", async () => {\n'
        '            if (generation !== this.socketGeneration || this.isStopped) return;\n'
        '            await saveCreds();\n'
        '        });\n\n'
        '        this.socket.ev.on("connection.update", async (update) => {\n'
        '            if (generation !== this.socketGeneration || this.isStopped) return;\n'
        '            await this.handleConnectionUpdate(update, generation);\n'
        '        });',
        "descartar eventos de sockets antigos",
    )
    value = substitute(
        value,
        '    async handleConnectionUpdate(update: Partial<ConnectionState>) {\n'
        '        const { connection, lastDisconnect, qr } = update;',
        '    async handleConnectionUpdate(update: Partial<ConnectionState>, generation: number) {\n'
        '        if (generation !== this.socketGeneration || this.isStopped) return;\n'
        '        const { connection, lastDisconnect, qr } = update;',
        "estado somente da geração ativa",
    )
    value = substitute(
        value,
        '            if (connection === "close") {\n'
        '                const code = (lastDisconnect?.error as any)?.output?.statusCode;',
        '            if (connection === "close") {\n'
        '                if (this.closeHandled) return;\n'
        '                this.closeHandled = true;\n'
        '                const code = (lastDisconnect?.error as any)?.output?.statusCode;',
        "ignorar múltiplos closes do mesmo socket",
    )
    # Match the precise old reconnect block. Restrict replacement to one block.
    old_start = '                    logger.warn("Instance",\n'
    old_end = '                    }, 3000);'
    marker = '                    this.reconnectTimer = setTimeout(() => {'
    if marker not in value:
        at = value.find(old_start, value.find('            if (connection === "close")'))
        end = value.find(old_end, at)
        if at < 0 or end < 0:
            raise RuntimeError("Reconexão WA-AKG desconhecida; abortando patch.")
        old = value[at:end + len(old_end)]
        if "disconnected. Reconnecting" not in old or "if (!this.isStopped) this.init();" not in old:
            raise RuntimeError("Reconexão personalizada; nenhum patch aplicado.")
        new = (
            '                    logger.warn("Instance",\n'
            '                        "Session " + this.sessionId + " disconnected (code " +\n'
            '                        String(code ?? "unknown") + "). Reconnecting (" +\n'
            '                        this.reconnectCount + "/" + MAX_RECONNECT_ATTEMPTS + ")..."\n'
            '                    );\n'
            '                    this.reconnectTimer = setTimeout(() => {\n'
            '                        this.reconnectTimer = null;\n'
            '                        if (!this.isStopped && this.status !== "CONNECTED") {\n'
            '                            void this.init().catch(error =>\n'
            '                                logger.error("Instance", "Reconnect initialization failed", error)\n'
            '                            );\n'
            '                        }\n'
            '                    }, 3000);'
        )
        value = value[:at] + new + value[end + len(old_end):]
    value = substitute(
        value,
        '            if (connection === "open") {\n'
        '                // Connected — reset reconnect count',
        '            if (connection === "open") {\n'
        '                if (this.status === "CONNECTED" && !this.closeHandled) return;\n'
        '                if (this.reconnectTimer) {\n'
        '                    clearTimeout(this.reconnectTimer);\n'
        '                    this.reconnectTimer = null;\n'
        '                }\n'
        '                this.closeHandled = false;\n'
        '                // Connected — reset reconnect count',
        "cancelar reconexão pendente quando abriu",
    )
    value = substitute(
        value,
        '                bindAutoReply(this.socket as WASocket, this.sessionId);\n'
        '                bindPpGuard(this.socket as WASocket, this.sessionId);',
        '                // A previous socket must never overwrite a newer connection state.\n'
        '                if (generation !== this.socketGeneration || this.closeHandled || this.isStopped) return;\n'
        '                bindAutoReply(this.socket as WASocket, this.sessionId);\n'
        '                bindPpGuard(this.socket as WASocket, this.sessionId);',
        "não confirmar conexão obsoleta depois de syncGroups",
    )
    value = substitute(
        value,
        '    async shutdown() {\n'
        '        this.isStopped = true;\n'
        '        this.socket?.end(undefined);\n'
        '        this.socket = null;\n'
        '        this.reconnectCount = 0;\n'
        '    }',
        '    async shutdown() {\n'
        '        this.isStopped = true;\n'
        '        ++this.socketGeneration;\n'
        '        if (this.reconnectTimer) {\n'
        '            clearTimeout(this.reconnectTimer);\n'
        '            this.reconnectTimer = null;\n'
        '        }\n'
        '        const socket = this.socket;\n'
        '        this.socket = null;\n'
        '        try { socket?.end(undefined); } catch { /* already closed */ }\n'
        '        this.reconnectCount = 0;\n'
        '        this.closeHandled = false;\n'
        '    }',
        "cancelar timers no desligamento protegido",
    )
    return value


def corrigir_gravacao_mensagens_emeca(value: str) -> str:
    """Impede duplicidades ruidosas e escrita por sockets de sessões substituídas.

    Nenhuma mensagem ou tabela é apagada. Usa os constraints já existentes
    e evita reatribuir mensagens de uma sessão antiga a outra sessão.
    """
    original = (
        '        // Ensure we have the database session ID\n'
        '        if (!dbSessionId) {\n'
        '            const session = await prisma.session.findUnique({ where: { sessionId }, select: { id: true } });\n'
        '            if (!session) return;\n'
        '            dbSessionId = session.id;\n'
        '        }'
    )
    seguro = (
        '        // EMECA: verify the internal Session record on each incoming batch.\n'
        '        // An old socket must not write after its Session is replaced.\n'
        '        const currentStoreSession = await prisma.session.findUnique({\n'
        '            where: { sessionId }, select: { id: true }\n'
        '        });\n'
        '        if (!currentStoreSession || (dbSessionId && dbSessionId !== currentStoreSession.id)) {\n'
        '            logger.warn("Store", "Ignoring events from removed/replaced session");\n'
        '            return;\n'
        '        }\n'
        '        dbSessionId = currentStoreSession.id;'
    )
    # Exactly two message consumers: messages.upsert and messaging-history.set.
    # The contacts listener must keep its existing behavior.
    if seguro in value:
        if value.count(seguro) != 2:
            raise RuntimeError("Guarda de sessão parcial/inesperada em store/index.ts.")
    elif value.count(original) >= 2:
        value = value.replace(original, seguro, 2)
    else:
        raise RuntimeError("Handlers de mensagens WA-AKG não reconhecidos; não aplicar.")

    value = substitute(
        value,
        '            } catch (error) {\n'
        '                logger.error("Store", "Error saving message", error);\n'
        '            }',
        '            } catch (error: any) {\n'
        '                // EMECA: stop the old batch if its Session was removed.\n'
        '                if (error?.code === "P2003") {\n'
        '                    logger.warn("Store", "Message batch stopped: Session FK no longer exists");\n'
        '                    break;\n'
        '                }\n'
        '                logger.error("Store", "Error saving message", error);\n'
        '            }',
        "parada do lote de mensagens sem sessão",
    )
    value = substitute(
        value,
        '                } catch (error) {\n'
        '                    logger.error("Store", "Error saving historical message", error);\n'
        '                }',
        '                } catch (error: any) {\n'
        '                    // EMECA: do not iterate thousands of messages against a missing FK.\n'
        '                    if (error?.code === "P2003") {\n'
        '                        logger.warn("Store", "History batch stopped: Session FK no longer exists");\n'
        '                        break;\n'
        '                    }\n'
        '                    logger.error("Store", "Error saving historical message", error);\n'
        '                }',
        "parada da sincronização antiga sem sessão",
    )
    value = substitute(
        value,
        '    } catch (e: any) {\n'
        '        logger.error("Store", "Error saving message query", e);\n'
        '        throw e;\n'
        '    }',
        '    } catch (e: any) {\n'
        '        // The findUnique/create sequence races across history and live listeners.\n'
        '        // P2002 means another listener already persisted this message.\n'
        '        if (e?.code === "P2002") return null;\n'
        '        logger.error("Store", "Error saving message query", e);\n'
        '        throw e;\n'
        '    }',
        "duplicidades concorrentes do histórico",
    )
    return value


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
    media_route = source / "src/app/api/messages/[sessionId]/[jid]/media/route.ts"
    broadcast_route = source / "src/app/api/messages/[sessionId]/broadcast/route.ts"
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

    required = [manager, instance, index, contact_store, chat_service, media_route, broadcast_route, chat_route, messages_route, contacts_route, overlay_file, profile_route_overlay, purge_route_overlay, group_route_overlay, scheduler_overlay, group_route_target, scheduler_target]
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
    value = corrigir_reconexao_instancia(value)
    value = corrigir_diagnostico_upload_instancia(value)
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
    value = corrigir_gravacao_mensagens_emeca(value)
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

    value = corrigir_resposta_envio_midia(media_route.read_text(encoding="utf-8"))
    edits[media_route] = value

    value = corrigir_broadcast_anexo(broadcast_route.read_text(encoding="utf-8"))
    edits[broadcast_route] = value

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
