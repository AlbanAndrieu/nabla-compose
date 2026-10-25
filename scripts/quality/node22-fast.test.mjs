// Offline compatibility gate. Does not install packages, touch Docker, or call CI.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const read = (path) => readFileSync(join(root, path), 'utf8');
const major = (version) => Number.parseInt(version.replace(/^v/, '').split('.')[0], 10);
const mustMatch = (source, pattern, name) => {
  assert.match(source, pattern, name + ' must remain declared');
};

test('Node 22 / npm 10 compatibility, no installation', () => {
  assert.equal(major(process.version), 22, 'Use Node 22 for the fast lane');
  const npm = execFileSync('npm', ['--version'], {
    encoding: 'utf8', timeout: 5000, stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
  assert.equal(major(npm), 10, 'Use npm 10 for the fast lane');
  const pkg = JSON.parse(read('package.json'));
  assert.equal(pkg.scripts['test:fast:node22'], 'node --test scripts/quality/node22-fast.test.mjs');
});

test('APISIX has one isolated canonical identity', () => {
  const compose = read('apps/apisix/compose.yml');
  mustMatch(compose, /^name: apisix\s*$/m, 'Compose project');
  mustMatch(compose, /^\s+id: apisix\s*$/m, 'x-nabla service ID');
  mustMatch(compose, /component:default\/apisix/, 'catalogue ref');
  assert.equal((compose.match(/profiles: \["apisix"\]/g) || []).length, 2);
  assert.doesNotMatch(compose, /^\s+ports:\s*$/m, 'No published port');
  assert.doesNotMatch(compose, /traefik\.enable/, 'No Traefik ingress');
  mustMatch(compose, /internal:\s*true/, 'isolated Docker network');
  assert.doesNotMatch(compose, /apisix-poc|APISIX_POC/, 'legacy name');
});

test('APISIX credentials and route stay private', () => {
  const routes = read('apps/apisix/config/apisix.yaml');
  const cfg = read('apps/apisix/config/config.yaml');
  mustMatch(routes, /uri:\s*\/health\b/, 'internal health route');
  mustMatch(routes, /key:\s*"\$env:\/\/APISIX_KEY"/, 'secret env source');
  mustMatch(routes, /hide_credentials:\s*true/, 'credentials redaction');
  mustMatch(routes, /rejected_code:\s*429/, 'quota');
  mustMatch(routes, /#END\s*$/, 'standalone file end');
  mustMatch(cfg, /enable_admin:\s*false/, 'disabled Admin API');
  mustMatch(cfg, /config_provider:\s*yaml/, 'file-driven config');
});

test('shell migration and diagnostics parse without executing', () => {
  for (const path of [
    'scripts/truenas/apisix.sh',
    'scripts/truenas/migration-operator.sh',
    'scripts/truenas/finish-migrations-20261024.sh',
    'scripts/truenas/migration-diagnostic-sections.sh',
    'scripts/truenas/triage-critical-failures.sh',
  ]) {
    assert.ok(existsSync(join(root, path)), path + ' missing');
    execFileSync('bash', ['-n', join(root, path)], {
      timeout: 5000, stdio: ['ignore', 'pipe', 'pipe'],
    });
  }
});

test('post-migration status distinguishes unknown from failed', () => {
  const runner = read('scripts/truenas/finish-migrations-20261024.sh');
  const sections = read('scripts/truenas/migration-diagnostic-sections.sh');
  mustMatch(runner, /ACTION_FLAGS > 1/, 'mutually exclusive CLI modes');
  mustMatch(runner, /SECTION.*postmigration/, 'postmigration section');
  mustMatch(runner, /WARNINGS > 0 \|\| SKIPPED > 0/, 'unverified exit');
  mustMatch(runner, /run_observation\(\)/, 'typed observations');
  mustMatch(sections, /^\s+postmigration\)/m, 'postmigration diagnostics');
  mustMatch(sections, /^\s+apisix\)/m, 'optional APISIX diagnostics');
  mustMatch(sections, /postmigration-service-readiness/, 'readiness');
  assert.doesNotMatch(sections, /docker compose[^\n]*\bup\b/, 'no implicit deployment');
});

test('local just recipes are opt-in and unchanged by CI', () => {
  const just = read('justfile');
  for (const recipe of [
    'node22-fast', 'apisix-check', 'apisix-smoke', 'apisix-down',
    'migration-operator-contracts', 'postmigration-check',
  ]) {
    mustMatch(just, new RegExp('^' + recipe + ':', 'm'), recipe);
  }
  mustMatch(just, /npm --offline run test:fast:node22/, 'offline mode');
  assert.ok(existsSync(join(root, 'docs/roadmap.md')));
});
