#!/usr/bin/env node
"use strict";
// Diagnóstico temporário do retorno HTTP 400. Não registra resposta, token,
// URL, JID, cabeçalhos, documento ou qualquer valor fornecido pelo servidor.
const fs = require("node:fs");
const path = require("node:path");
const root = process.argv[2];
if(!root) throw Error("Uso: node patch-resposta-400.cjs DIRETORIO_BAILEYS");
const pkg = path.join(root,"package.json");
const file = path.join(root,"lib/Utils/messages-media.js");
if(!fs.existsSync(pkg) || !fs.existsSync(file)) throw Error("Biblioteca não encontrada");
if(JSON.parse(fs.readFileSync(pkg,"utf8")).version!=="7.0.0-rc.9") {
  throw Error("Diagnóstico exclusivo Baileys rc.9");
}
const source = fs.readFileSync(file,"utf8");
const mark="WA-MEDIA-REJECTION-DIAG-V1";
if(source.includes(mark)){
  if(source.split(mark).length!==2 || !source.includes("responseClass")) {
    throw Error("Diagnóstico parcial; não modificar");
  }
  console.log("Diagnóstico HTTP 400 já aplicado.");
  process.exit(0);
}
const hasV2 = source.includes("EMECA_RC9_HTTPS_UPLOAD_V2");
const hasV1 = source.includes("EMECA_BAILEYS_RC9_UPLOAD_V1");
if(!hasV1 && !hasV2) throw Error("Uploader fora das versões instrumentadas V1/V2; sem alteração");
const needle = [
'res.on("end", () => resolve({',
'                status: res.statusCode,',
'                json: async () => JSON.parse(Buffer.concat(chunks).toString("utf8"))',
'            }));'
].join("\n");
if(source.split(needle).length!==2) throw Error("Formato de resposta HTTPS não reconhecido; sem alteração");
const replacement = [
'res.on("end", () => {',
'                // WA-MEDIA-REJECTION-DIAG-V1',
'                const responseBody = Buffer.concat(chunks).toString("utf8");',
'                const lower = responseBody.toLowerCase();',
'                let responseFormat = responseBody.length === 0 ? "EMPTY" : "TEXT";',
'                try { JSON.parse(responseBody); responseFormat = "JSON"; }',
'                catch { if (/^\\s*<!?doctype|^\\s*<html/i.test(responseBody)) responseFormat = "HTML"; }',
'                let responseClass = "UNCLASSIFIED";',
'                if (/\\b(expired|expirado|expire)\\b/i.test(lower)) responseClass = "EXPIRED";',
'                else if (/\\b(auth|token|permission|unauthoriz|forbidden|credential|signature)\\b/i.test(lower)) responseClass = "AUTHORIZATION";',
'                else if (/\\b(content.length|too.large|payload.too.large|size|length|quota)\\b/i.test(lower)) responseClass = "CONTENT_SIZE";',
'                else if (/\\b(hash|sha256|checksum|digest|integrity)\\b/i.test(lower)) responseClass = "HASH_INTEGRITY";',
'                else if (/\\b(missing|malformed|invalid|parameter|bad.request)\\b/i.test(lower)) responseClass = "INVALID_REQUEST";',
'                else if (/\\b(rate.limit|too.many.requests)\\b/i.test(lower)) responseClass = "RATE_LIMIT";',
'                if (res.statusCode >= 400) console.error("WA-MEDIA-REJECTION-DIAG", {',
'                    httpStatus: res.statusCode, responseFormat, responseClass,',
'                    responseBytes: Buffer.byteLength(responseBody)',
'                });',
'                resolve({status: res.statusCode, json: async () => JSON.parse(responseBody)});',
'            });'
].join("\n");
// Na versão V1 o upload usa fetch() e não o transporte HTTPS nativo.
// Não mudar corpo, cabeçalhos, token nem URL: apenas classificar a resposta.
const v1Needle = "parsed = await response.json()";
const v1Replacement = [
  "// WA-MEDIA-REJECTION-DIAG-V1",
  "const emecaRawResponse = await response.text();",
  "if (response.status >= 400) {",
  "    const lower = emecaRawResponse.toLowerCase();",
  "    let responseFormat = emecaRawResponse.length === 0 ? \"EMPTY\" : \"TEXT\";",
  "    try { JSON.parse(emecaRawResponse); responseFormat = \"JSON\"; }",
  "    catch { if (/^\\s*<!?doctype|^\\s*<html/i.test(emecaRawResponse)) responseFormat = \"HTML\"; }",
  "    let responseClass = \"UNCLASSIFIED\";",
  "    if (/\\b(expired|expirado|expire)\\b/i.test(lower)) responseClass = \"EXPIRED\";",
  "    else if (/\\b(auth|token|permission|unauthoriz|forbidden|credential|signature)\\b/i.test(lower)) responseClass = \"AUTHORIZATION\";",
  "    else if (/\\b(content.length|too.large|payload.too.large|size|length|quota)\\b/i.test(lower)) responseClass = \"CONTENT_SIZE\";",
  "    else if (/\\b(hash|sha256|checksum|digest|integrity)\\b/i.test(lower)) responseClass = \"HASH_INTEGRITY\";",
  "    else if (/\\b(missing|malformed|invalid|parameter|bad.request)\\b/i.test(lower)) responseClass = \"INVALID_REQUEST\";",
  "    else if (/\\b(rate.limit|too.many.requests)\\b/i.test(lower)) responseClass = \"RATE_LIMIT\";",
  "    console.error(\"WA-MEDIA-REJECTION-DIAG\", {",
  "        httpStatus: response.status, responseFormat, responseClass,",
  "        responseBytes: Buffer.byteLength(emecaRawResponse)",
  "    });",
  "}",
  "parsed = JSON.parse(emecaRawResponse);"
].join("\n");
let patched;
if (hasV2) {
  if(source.split(needle).length!==2) throw Error("Resposta HTTPS V2 desconhecida; sem alteração");
  patched=source.replace(needle,replacement);
} else {
  if(!source.includes("const response = await fetch(url, {") || source.split(v1Needle).length!==2)
    throw Error("Resposta fetch V1 desconhecida; sem alteração");
  patched=source.replace(v1Needle,v1Replacement);
}
if(patched===source || patched.split(mark).length!==2) throw Error("Patch inesperado; sem escrita");
fs.writeFileSync(file,patched,"utf8");
console.log("Diagnóstico temporário de rejeição instalado para " + (hasV2 ? "HTTPS V2" : "fetch V1") + "; sem dados sensíveis.");
