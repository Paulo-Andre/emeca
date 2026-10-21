#!/usr/bin/env node
"use strict";
// EMECA: segunda etapa de correção RC9, após patch-baileys-rc9.cjs.
// Substitui apenas o POST de media via fetch() por Node.js HTTPS nativo,
// conforme estratégia do Baileys rc14, sem mudar API, sessão ou deps.
const fs = require("node:fs");
const path = require("node:path");
const root = process.argv[2] || path.join(process.cwd(), "node_modules", "@whiskeysockets", "baileys");
const manifest = path.join(root, "package.json");
const target = path.join(root, "lib", "Utils", "messages-media.js");
if (!fs.existsSync(manifest) || !fs.existsSync(target)) {
  throw new Error("Biblioteca Baileys ou uploader não encontrado");
}
const ver = JSON.parse(fs.readFileSync(manifest,"utf8")).version;
if(ver !== "7.0.0-rc.9") throw new Error("Patch exclusivo rc.9. Versão: "+ver);
const source = fs.readFileSync(target,"utf8");
const begin = source.indexOf("export const getWAUploadToServer");
const end = source.indexOf("const getMediaRetryKey",begin);
if(begin < 0 || end <= begin || source.indexOf("export const getWAUploadToServer",begin+1)>=0){
  throw new Error("Uploader não corresponde à rc.9; nenhum arquivo modificado");
}
const mark = "EMECA_RC9_HTTPS_UPLOAD_V2";
const firstPatch = "EMECA_BAILEYS_RC9_UPLOAD_V1";
if(!source.includes(firstPatch) || !source.includes("WA-MEDIA-HTTP-DIAG")) {
  throw new Error("Correção rc.9 anterior ausente. Aplicar patch V1 antes de V2.");
}
if(source.includes(mark)){
  const assertions = ["emecaHttpsUploadWithNode", "node:https", "response.status", "Content-Length"];
  if(assertions.some(x=>!source.includes(x)) ||
     source.includes("const response = await fetch(url, {")){
    throw new Error("Observador V2 parcial/inconsistente; abortando");
  }
  console.log("Transporte HTTPS V2 já aplicado, sem duplicar.");
  process.exit(0);
}

const helper = "// EMECA_RC9_HTTPS_UPLOAD_V2: porta somente o POST de mídia de Baileys rc14.\n// Nunca registrar URL assinada, token, JID, cabeçalhos, arquivo ou resposta.\nconst emecaHttpsUploadWithNode = async (mediaUrl, encryptedFile, opts, redirects = 0) => {\n    if (redirects > 5) throw new Error(\"MEDIA_TOO_MANY_REDIRECTS\");\n    const { request } = await import(\"node:https\");\n    const { createReadStream } = await import(\"node:fs\");\n    const { stat } = await import(\"node:fs/promises\");\n    const url = new URL(mediaUrl);\n    if (url.protocol !== \"https:\") throw new Error(\"MEDIA_INSECURE_REDIRECT\");\n    const { size } = await stat(encryptedFile);\n    if (!Number.isSafeInteger(size) || size <= 0) throw new Error(\"MEDIA_INVALID_SIZE\");\n    const contentLength = Number(opts.headers[\"Content-Length\"]);\n    if (contentLength !== size) throw new Error(\"MEDIA_SIZE_MISMATCH\");\n    return new Promise((resolve, reject) => {\n        const req = request(url, {\n            method: \"POST\", headers: opts.headers, signal: opts.signal\n        }, res => {\n            if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {\n                const nextUrl = new URL(res.headers.location, url);\n                res.resume();\n                if (nextUrl.protocol !== \"https:\") reject(new Error(\"MEDIA_INSECURE_REDIRECT\"));\n                else resolve(emecaHttpsUploadWithNode(nextUrl.toString(), encryptedFile, opts, redirects + 1));\n                return;\n            }\n            const chunks = [];\n            let bytes = 0;\n            res.on(\"data\", chunk => {\n                bytes += chunk.length;\n                if (bytes > 65536) req.destroy(new Error(\"MEDIA_RESPONSE_TOO_LARGE\"));\n                else chunks.push(chunk);\n            });\n            res.on(\"end\", () => resolve({\n                status: res.statusCode,\n                json: async () => JSON.parse(Buffer.concat(chunks).toString(\"utf8\"))\n            }));\n            res.on(\"error\", reject);\n        });\n        req.on(\"error\", reject);\n        const mediaStream = redirects === 0 ? opts.body : createReadStream(encryptedFile);\n        mediaStream.on(\"error\", err => req.destroy(err));\n        mediaStream.pipe(req);\n    });\n};\n";
const original='const response = await fetch(url, {';
const upgraded='const response = await emecaHttpsUploadWithNode(url, filePath, {';
const body=source.slice(begin,end);
if(body.split(original).length !== 2) throw new Error("Chamada fetch não é única no uploader rc.9; sem alteração");
const edited=source.slice(0,begin)+helper+body.replace(original,upgraded)+source.slice(end);
if(!edited.includes(mark)||!edited.includes(upgraded)) throw new Error("Patch V2 inválido");
fs.writeFileSync(target,edited,"utf8");
console.log("Baileys rc.9 HTTPS nativo V2 aplicado sem alterar sessão ou dependências.");
