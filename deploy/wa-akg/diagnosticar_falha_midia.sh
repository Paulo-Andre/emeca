#!/usr/bin/env bash
# Diagnóstico somente leitura de falha SEND em imagens/PDF.
# Não envia mensagens, não consulta documentos, não altera a sessão.
set -euo pipefail

echo "=== Últimas falhas sanitizadas de envio de mídia ==="
docker logs --since=90m wa-akg-app 2>&1 \
  | grep -F "WA-MEDIA-UPLOAD-DIAG" | tail -n 30 || true
docker logs --since=90m wa-akg-app 2>&1 \
  | grep -A 6 -F 'Media send error (sanitized)' \
  | grep -F -e 'Media send error (sanitized)' -e 'code:' -e 'name:' -e 'statusCode:' -e 'stage:' \
  | tail -n 35 || true

echo
echo "=== Verificação de DNS e conexão HTTPS do contêiner (sem upload) ==="
docker exec -i wa-akg-app node - <<'NODE'
const dns = require('node:dns').promises;
const https = require('node:https');

(async () => {
  const host = 'mmg.whatsapp.net';
  try {
    const results = await dns.lookup(host, { all: true });
    console.log('DNS mídia WhatsApp:', results.length ? 'OK' : 'SEM RESPOSTA',
      'IPv4:', results.filter(x => x.family === 4).length,
      'IPv6:', results.filter(x => x.family === 6).length);
  } catch (e) {
    console.log('DNS mídia WhatsApp: FALHA', String(e.code || e.name || 'UNKNOWN'));
  }
  await new Promise(resolve => {
    let finished = false;
    const finish = () => {
      if (finished) return false;
      finished = true;
      resolve();
      return true;
    };
    const req = https.request({
      hostname: host, path: '/', method: 'HEAD', timeout: 12000
    }, res => {
      // 4xx é esperado sem token de upload, mas comprova acesso HTTPS.
      if (!finished) {
        console.log('HTTPS mídia WhatsApp: CONECTOU (HTTP ' + res.statusCode + ')');
        finish();
      }
      res.resume();
    });
    req.on('timeout', () => {
      if (!finished) {
        console.log('HTTPS mídia WhatsApp: TIMEOUT');
        finish();
      }
      req.destroy();
    });
    req.on('error', e => {
      if (!finished) {
        console.log('HTTPS mídia WhatsApp: FALHA',
          String(e.code || e.name || 'UNKNOWN'));
        finish();
      }
    });
    req.end();
  });
})();
NODE
