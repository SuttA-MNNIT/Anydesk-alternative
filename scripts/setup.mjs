import { randomBytes } from 'node:crypto';
import { mkdir, writeFile, access } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root = fileURLToPath(new URL('../', import.meta.url));
await mkdir(path.join(root, 'config'), { recursive: true });
const configPath = path.join(root, 'config/relay.json');
try { await access(configPath); console.log('Existing relay configuration preserved.'); }
catch {
  await writeFile(configPath, JSON.stringify({ listenHost: '127.0.0.1', port: 8787, enrollmentToken: randomBytes(32).toString('hex'), allowedOrigins: [] }, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
  console.log('Created config/relay.json with a random host enrollment token. Keep this file private.');
}
