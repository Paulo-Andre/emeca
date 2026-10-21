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

const helper = String.raw