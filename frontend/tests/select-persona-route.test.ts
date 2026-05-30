import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const routeSource = fs.readFileSync(
  path.join(process.cwd(), '..', 'backend', 'app', 'api', 'onboarding.py'),
  'utf8',
);

test('select persona route clears persisted call verification when persona changes', () => {
  assert.match(routeSource, /async def _clear_call_verification/);
  assert.match(routeSource, /async with connection\.transaction\(\):/);
  assert.match(routeSource, /DELETE FROM demo_call_verifications/);
  assert.match(routeSource, /DELETE FROM demo_call_mobile_verifications/);
  assert.match(routeSource, /session_id = \$1/);
  assert.match(routeSource, /await _clear_call_verification\(connection, session_id\)/);
});
