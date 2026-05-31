import test from 'node:test';
import assert from 'node:assert/strict';

import { getPersonaById } from '../lib/personas';
import { buildPersonaBrief, getPersonaSuggestions } from '../lib/agent/persona-suggestions';

test('buildPersonaBrief exposes the selected persona without leaking internal JSON', () => {
  const persona = getPersonaById('cust_demo_001');
  assert.ok(persona);

  const brief = buildPersonaBrief(persona);

  assert.equal(brief.name, 'Ananya Sharma');
  assert.equal(brief.customerId, 'cust_demo_001');
  assert.match(brief.statusLine, /KYC - Pending review/);
  assert.match(brief.moneyLine, /PAY-8831/);
  assert.doesNotMatch(JSON.stringify(brief), /"payments":/);
});

test('getPersonaSuggestions prioritizes tasks available for a payment-failed persona', () => {
  const persona = getPersonaById('cust_demo_001');
  assert.ok(persona);

  const suggestions = getPersonaSuggestions(persona);
  const ids = suggestions.map((suggestion) => suggestion.id);

  assert.deepEqual(ids.slice(0, 3), ['payment-status', 'fd-booking-status', 'kyc-status']);
  assert.ok(suggestions.every((suggestion) => suggestion.prompt.length > 12));
});

test('getPersonaSuggestions includes secure-link and premature withdrawal actions when available', () => {
  const persona = getPersonaById('cust_demo_004');
  assert.ok(persona);

  const ids = getPersonaSuggestions(persona).map((suggestion) => suggestion.id);

  assert.ok(ids.includes('premature-withdrawal'));
  assert.ok(ids.includes('secure-link'));
});

test('demo personas cover the required support scenarios', () => {
  const personas = ['cust_demo_001', 'cust_demo_002', 'cust_demo_003', 'cust_demo_004', 'cust_demo_005'].map((id) => {
    const persona = getPersonaById(id);
    assert.ok(persona, `${id} should exist`);
    return persona;
  });

  assert.deepEqual(
    personas.map((persona) => persona.name),
    ['Ananya Sharma', 'Rohan Mehta', 'Priya Nair', 'Vikram Patel', 'Meera Iyer'],
  );

  const [ananya, rohan, priya, vikram, meera] = personas;

  assert.equal(ananya.kyc_status, 'pending_review');
  assert.equal(ananya.payments[0]?.status, 'failed');
  assert.equal(ananya.fixed_deposits[0]?.status, 'processing');

  assert.equal(rohan.kyc_status, 'rejected');
  assert.match(rohan.kyc_next_step ?? '', /Resubmit/i);

  assert.equal(priya.fixed_deposits.length, 1);
  assert.equal(priya.fixed_deposits[0]?.status, 'matured');
  assert.match(priya.fixed_deposits[0]?.payout_status ?? '', /delay/i);

  assert.equal(vikram.fixed_deposits[0]?.status, 'active');
  assert.ok(vikram.fixed_deposits[0]?.premature_withdrawal_estimate);
  assert.equal(vikram.secure_links[0]?.status, 'ready_to_send');

  assert.equal(meera.open_tickets[0]?.status, 'open');
});
