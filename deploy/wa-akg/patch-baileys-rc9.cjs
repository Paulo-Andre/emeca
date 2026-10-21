#!/usr/bin/env node
'use strict';
// EMECA: correção LOCAL no uploader da versão instalada 7.0.0-rc.9.
// Não conecta ao WhatsApp, não envia mensagens, não altera DB ou credenciais.
const fs = require('node:fs');
const path = require('node:path');
const root = process.argv[2] || path.join(process.cwd(), 'node_modules', '@whiskeysockets', 'baileys');
const manifest = path.join(root, 'package.json');
const target = path.join(root, 'lib', 'Utils', 'messages-media.js');
if (!fs.existsSync(manifest) || !fs.existsSync(target)) {
  throw new Error('Biblioteca Baileys instalada ou arquivo de upload não encontrado');
}
const version = JSON.parse(fs.readFileSync(manifest, 'utf8')).version;
if (version !== '7.0.0-rc.9') {
  throw new Error('Patch restrito à versão 7.0.0-rc.9; encontrado ' + version);
}
const old = fs.readFileSync(target, 'utf8');
const start = old.indexOf('export const getWAUploadToServer');
const end = old.indexOf('const getMediaRetryKey', start);
if (start < 0 || end <= start) {
  throw new Error('Uploader Baileys modificado ou não reconhecido. Nenhum arquivo alterado.');
}
let part = old.slice(start, end);
const mark = 'EMECA_BAILEYS_RC9_UPLOAD_V1';
if (part.includes(mark)) {
  const markers = [
    mark,
    "'Content-Length': emecaEncryptedFileSize",
    'result?.direct_path',
    'WA-MEDIA-HTTP-DIAG'
  ];
  if (markers.some(x => !part.includes(x))) {
    throw new Error('Patch de upload parcial. Nenhum arquivo alterado.');
  }
  console.log('Patch de mídia rc.9 já aplicado.');
  process.exit(0);
}
function replaceOnce(before, after, label) {
  const arr = part.split(before);
  if (arr.length !== 2) throw new Error('Estrutura inesperada (' + label + '): ' + (arr.length - 1) + ' ocorrências. Sem alteração.');
  part = arr.join(after);
}
// O fetch da rc.9 usa upload em chunked transfer encoding quando recebe
// ReadStream sem tamanho. A rc14 usa Content-Length no envio via HTTPS.
// Aqui mantemos o fetch, a sessão e o restante da rc.9 inalterados.
replaceOnce(
  'const response = await fetch(url, {',
  '// ' + mark + '\n' +
  "const emecaEncryptedFileSize = (await (await import('node:fs/promises')).stat(filePath)).size;\n" +
  'const response = await fetch(url, {',
  'início da chamada fetch'
);
replaceOnce(
  "'Content-Type': 'application/octet-stream',",
  "'Content-Type': 'application/octet-stream',\n" +
  "'Content-Length': emecaEncryptedFileSize,",
  'tamanho da mídia criptografada'
);
// Loga somente o status HTTP, nunca URL, token, JID ou resposta do servidor.
replaceOnce(
  'let parsed = undefined',
  'console.error("WA-MEDIA-HTTP-DIAG", { httpStatus: response.status });\n' +
  'let parsed = undefined',
  'resposta HTTP'
);
// Compatibilidade com resposta que usa direct_path (snake_case).
replaceOnce(
  'if (result?.url || result?.directPath) {',
  'if (result?.url || result?.direct_path || result?.directPath) {',
  'campo de confirmação'
);
replaceOnce(
  'directPath: result.direct_path,',
  'directPath: result.direct_path || result.directPath,',
  'campo direct_path'
);
const result = old.slice(0, start) + part + old.slice(end);
if (result === old || !result.includes(mark)) {
  throw new Error('Nenhuma correção preparada. Nenhum arquivo alterado.');
}
fs.writeFileSync(target, result, 'utf8');
console.log('Uploader Baileys rc.9 corrigido: Content-Length, direct_path, HTTP sanitizado.');
