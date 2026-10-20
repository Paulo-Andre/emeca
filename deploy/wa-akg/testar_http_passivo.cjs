'use strict';
// Teste sintético: NÃO conecta ao WhatsApp, à internet ou a arquivos pessoais.
const assert = require('node:assert/strict');
const dc = require('node:diagnostics_channel');
const http = require('node:http');

const statuses = [];
const channel = dc.channel('http.client.response.finish');
const watcher = ({ request, response }) => {
  if (request?.method !== 'POST' ||
      request?.getHeader?.('origin') !== 'https://web.whatsapp.com' ||
      request?.getHeader?.('content-type') !== 'application/octet-stream') return;
  const status = response?.statusCode;
  statuses.push(Number.isInteger(status) && status >= 100 && status <= 599 ? status : null);
};
channel.subscribe(watcher);

async function request(port, method, origin) {
  return new Promise((resolve, reject) => {
    const req = http.request({
      hostname: '127.0.0.1', port, path: '/synthetic-test', method,
      headers: {'Origin': origin, 'Content-Type': 'application/octet-stream'},
      timeout: 3000,
    }, res => {res.resume(); res.once('end', resolve);});
    req.once('error', reject);
    req.once('timeout', () => req.destroy(new Error('local test timeout')));
    req.end(method === 'POST' ? 'synthetic' : undefined);
  });
}

(async () => {
  const server = http.createServer((_req, res) => {
    res.writeHead(403, {'Content-Type': 'text/plain'});
    res.end('synthetic rejection');
  });
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const port = server.address().port;
    await request(port, 'POST', 'https://web.whatsapp.com');
    await request(port, 'GET', 'https://web.whatsapp.com');
    await request(port, 'POST', 'https://other.invalid');
    assert.deepEqual(statuses, [403]);
    console.log('PASS: status HTTP capturado passivamente; sem trafego externo.');
  } finally {
    channel.unsubscribe(watcher);
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {console.error('FAIL:', error.name); process.exitCode = 1;});
