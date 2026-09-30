import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { resolve, dirname } from 'node:path';
import { canonicalJSON, loadSources, reviewEvidence, getPointer, validateEvidencePointer } from '../core.mjs';

const fixtureRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../fixtures/original');
const read = name => JSON.parse(readFileSync(resolve(fixtureRoot, name), 'utf8'));
// Gold is evaluator-only: this test file is the sole gold consumer.
const gold = read('query-gold-v1.json');
const inventories = read('inventory-fictional.json').records;
const sources = loadSources();
const inventoryFor = id => structuredClone(inventories.find(item => item.inventory_id === `${id}-INV`));
const review = (id, overrides = {}) => {
  const fixture = gold.cases.find(item => item.case_id === id);
  return reviewEvidence({ caseId: id, inventory: inventoryFor(id), advisoryId: fixture.advisory_id,
    admittedSources: fixture.admitted_sources, sources, ...overrides });
};
const hash = value => createHash('sha256').update(value).digest('hex');

test('loadSources uses exact raw-byte SHA256 and preserves manifest record metadata', () => {
  const manifest = read('source-manifest.json');
  assert.equal(sources.length, 3);
  for (const source of sources) {
    const record = manifest.source_records.find(item => item.source_id === source.id);
    assert.deepEqual(source.metadata, record);
    assert.equal(source.hash, hash(readFileSync(resolve(fixtureRoot, record.file))));
    assert.equal(source.hash, manifest.file_integrity.find(item => item.path === record.file).sha256);
  }
});

for (const fixture of gold.cases) {
  test(`${fixture.case_id}: evaluator state, vendor statement and required pointer containment`, () => {
    const result = review(fixture.case_id);
    assert.equal(result.identity_or_coverage_state, fixture.expected_identity_or_coverage_state);
    assert.equal(result.vendor_statement, fixture.expected_vendor_statement);
    assert.equal(result.running_state, 'unknown');
    assert.equal(result.review_required, true);
    for (const expected of fixture.source_pointers) {
      const actual = result.source_pointers.find(item => item.source === expected.source && item.pointer === expected.pointer);
      assert.ok(actual, `${expected.source}${expected.pointer}`);
      assert.deepEqual(actual.value, expected.value);
    }
    for (const pointer of result.source_pointers) {
      assert.ok(validateEvidencePointer(pointer, { inventory: inventoryFor(fixture.case_id), sources }));
    }
    assert.ok(result.facts.length > 0);
    for (const fact of result.facts) {
      assert.ok(fact.pointer_ids.length > 0);
      for (const id of fact.pointer_ids) assert.ok(result.source_pointers.some(item => item.id === id));
    }
  });
}

test('E4 erratum ADVISORY-v1-E4-banner-wording-1: upstream banner compatibility leaves running unknown', () => {
  const result = review('E4');
  assert.equal(result.vendor_statement, 'fixed');
  const bannerFact = result.facts.find(item => item.text.includes('banner') && item.text.includes('compatible'));
  assert.ok(bannerFact);
  assert.match(bannerFact.text, /lacks the Debian revision/);
  assert.equal(result.running_state, 'unknown');
  assert.doesNotMatch(result.facts.map(item => item.text).join(' '), /different observed|mismatch|must restart|restart required/i);
});

test('E5 explicit unknown field scope is ambiguity, never invented host/container scope', () => {
  const result = review('E5', { inventory: { ...inventoryFor('E5'), field_scope: 'unknown' } });
  assert.equal(result.identity_or_coverage_state, 'INSUFFICIENT_IDENTITY');
  assert.equal(result.vendor_statement, 'not established');
  assert.ok(result.unknowns.some(item => item.includes('unknown scope')));
});

test('PURL matching is literal: qualifier ordering, architecture, distro and package/version never relax', () => {
  const original = inventoryFor('D1');
  for (const product_purl of [
    original.product_purl.replace('arch=amd64&distro=jammy', 'distro=jammy&arch=amd64'),
    original.product_purl.replace('arch=amd64', 'arch=fictional'),
    original.product_purl.replace('distro=jammy', 'distro=fictional'),
    original.product_purl.replace('openssh-server', 'openssh-fictional'),
    original.product_purl.replace('ubuntu0.17', 'ubuntu0.18'),
    original.product_purl.replace('1:8.9p1', '8.9p1'),
  ]) {
    const result = review('D1', { inventory: { ...original, product_purl } });
    assert.equal(result.identity_or_coverage_state, 'NO_EXACT_MATCH', product_purl);
    assert.equal(result.vendor_statement, 'not established');
  }
  const incomplete = review('D1', { inventory: { ...original, product_purl: original.product_purl.replace('?arch=amd64&distro=jammy', '') } });
  assert.equal(incomplete.identity_or_coverage_state, 'INSUFFICIENT_IDENTITY');
});

test('current CVE requires exact vulnerability name; historical notice requires explicit exact alias', () => {
  const current = review('D1', { advisoryId: 'CVE-2024-6388' });
  assert.equal(current.identity_or_coverage_state, 'NO_EXACT_MATCH');
  const historical = review('D2', { advisoryId: 'CVE-2024-6388' });
  assert.equal(historical.identity_or_coverage_state, 'NO_EXACT_MATCH');
  const mutatedSources = structuredClone(sources);
  const usn = mutatedSources.find(item => item.id === 'U-USN');
  usn.document.statements[0].vulnerability.aliases = ['https://ubuntu.com/security/CVE-2024-6387'];
  const noExplicitAlias = review('D2', { sources: mutatedSources });
  assert.equal(noExplicitAlias.identity_or_coverage_state, 'NO_EXACT_MATCH');
  const cve = mutatedSources.find(item => item.id === 'U-CVE');
  cve.document.statements[0].vulnerability.name = 'CVE-2024-6388';
  cve.document.statements[0].vulnerability.aliases.push('CVE-2024-6387');
  assert.equal(review('D1', { sources: mutatedSources }).identity_or_coverage_state, 'NO_EXACT_MATCH');
});

test('source admission and revocation change evidence without lookup into an unadmitted record', () => {
  const admitted = review('D2');
  const revoked = review('D2', { admittedSources: ['U-CVE'] });
  assert.equal(admitted.identity_or_coverage_state, 'HISTORICAL_ADVISORY_EXACT_MATCH');
  assert.equal(revoked.identity_or_coverage_state, 'NO_EXACT_MATCH');
  assert.notEqual(admitted.evidence_fingerprint, revoked.evidence_fingerprint);
  assert.ok(revoked.source_pointers.every(item => item.source === 'INVENTORY' || item.source === 'U-CVE'));
  const unreadable = { id: 'U-USN', get document() { throw new Error('unadmitted document accessed'); } };
  assert.equal(review('D2', { admittedSources: ['U-CVE'], sources: [sources[0], unreadable] }).identity_or_coverage_state, 'NO_EXACT_MATCH');
  const negative = revoked.facts.find(item => item.text.includes('0 exact matches'));
  assert.ok(negative);
  const grounding = negative.pointer_ids.map(id => revoked.source_pointers.find(item => item.id === id));
  assert.ok(grounding.some(item => item.source === 'INVENTORY' && item.pointer === '/product_purl'));
  assert.ok(grounding.every(item => !item.pointer.includes('/products/')));
  assert.ok(grounding.every(item => item.pointer !== '/statements'));
  const receipt = revoked.lookup_receipts.find(item => negative.lookup_ids.includes(item.id));
  assert.equal(receipt.collection_path, '/statements');
  assert.equal(receipt.source_hash, sources.find(item => item.id === 'U-CVE').hash);
  assert.equal(receipt.candidate_count, 432);
  assert.equal(receipt.exact_match_count, 0);
  assert.equal(receipt.inventory_pointer, '/product_purl');
  assert.match(negative.text, /432 candidate product entries, 0 exact matches/);
});

test('fingerprint covers entire derived output and changes for snapshot, inventory and admission changes', () => {
  const result = review('D1');
  const { evidence_fingerprint, ...unsigned } = result;
  assert.equal(evidence_fingerprint, hash(canonicalJSON(unsigned)));
  assert.deepEqual(review('D1'), result);
  const changedSources = structuredClone(sources);
  changedSources[0].hash = 'a'.repeat(64);
  assert.notEqual(review('D1', { sources: changedSources }).evidence_fingerprint, evidence_fingerprint);
  assert.notEqual(review('D1', { inventory: { ...inventoryFor('D1'), observed_at: '2026-10-01T00:00:00Z' } }).evidence_fingerprint, evidence_fingerprint);
  const reversed = review('D2', { admittedSources: ['U-USN', 'U-CVE', 'U-CVE'] });
  assert.equal(reversed.evidence_fingerprint, review('D2').evidence_fingerprint);
});

test('tampered pointers fail value, address, quote, hash or source validation', () => {
  const result = review('D1');
  const original = result.source_pointers.find(item => item.source === 'U-CVE' && item.pointer.endsWith('/status'));
  const context = { inventory: inventoryFor('D1'), sources };
  assert.ok(validateEvidencePointer(original, context));
  for (const patch of [
    { value: 'not_affected' }, { quote: 'fixed' }, { pointer: '/statements/999/status' },
    { source_hash: 'b'.repeat(64) }, { source: 'U-USN' },
  ]) assert.equal(validateEvidencePointer({ ...original, ...patch }, context), false);
  assert.equal(validateEvidencePointer(original, { ...context, sources: [] }), false);
});

test('JSON pointer escaping, missing values and prototype properties are handled precisely', () => {
  const doc = { 'a/b': { '~key': ['value', null] } };
  assert.equal(getPointer(doc, '/a~1b/~0key/0'), 'value');
  assert.equal(getPointer(doc, '/a~1b/~0key/1'), null);
  assert.equal(getPointer(doc, '/a~1b/~0key/01'), undefined);
  assert.equal(getPointer(doc, '/constructor'), undefined);
  assert.equal(getPointer(doc, '/a~2b'), undefined);
  assert.equal(getPointer(doc, 'a/b'), undefined);
  assert.deepEqual(getPointer(doc, ''), doc);
});

test('projection is scoped to declared CVE/CPE/component and preserves conflict without precedence', () => {
  const result = review('E6');
  assert.equal(result.identity_or_coverage_state, 'CONFLICTING_SOURCES');
  assert.equal(result.vendor_statement, 'not established');
  assert.ok(result.facts.some(item => item.text.includes('not authoritative VEX')));
  assert.ok(result.facts.some(item => item.text.includes('no precedence')));
  assert.equal(review('E6', { advisoryId: 'CVE-2026-44193' }).identity_or_coverage_state, 'INSUFFICIENT_IDENTITY');
  assert.equal(review('E6', { inventory: { ...inventoryFor('E6'), cpe: 'fictional-other-cpe' } }).identity_or_coverage_state, 'INSUFFICIENT_IDENTITY');
});

test('unavailable or empty admitted sources remain unresolved and all running builds are conservatively unknown', () => {
  const missing = review('D1', { admittedSources: ['missing-source'] });
  assert.equal(missing.identity_or_coverage_state, 'INSUFFICIENT_EVIDENCE');
  assert.ok(missing.unknowns.some(item => item.includes('unavailable')));
  assert.deepEqual(missing.source_ids, []);
  const running = review('D1', { inventory: { ...inventoryFor('D1'), running_build: inventoryFor('D1').product_purl } });
  assert.equal(running.running_state, 'unknown');
});

test('missing identity facts describe supplied fields without claiming completeness', () => {
  const result = review('D3');
  assert.match(result.facts[0].text, /supplied component identity fields/);
  assert.doesNotMatch(result.facts[0].text, /complete component identity/);
});

test('not_affected positive fact explicitly includes exact vendor justification', () => {
  const result = review('E1');
  const fact = result.facts.find(item => item.text.includes('states "not_affected"'));
  assert.ok(fact);
  assert.match(fact.text, /Vendor justification: "vulnerable_code_not_present"/);
  assert.ok(fact.pointer_ids.some(id => result.source_pointers.find(item => item.id === id)?.pointer === '/statements/1/justification'));
});

test('missing snapshots are insufficient evidence and do not fabricate a completed negative lookup', () => {
  for (const overrides of [{ admittedSources: [] }, { admittedSources: ['missing-source'] }, { sources: [] }]) {
    const result = review('D1', overrides);
    assert.equal(result.identity_or_coverage_state, 'INSUFFICIENT_EVIDENCE');
    assert.equal(result.vendor_statement, 'not established');
    assert.deepEqual(result.lookup_receipts, []);
    assert.ok(result.facts.every(item => !item.text.includes('0 exact matches')));
  }
  assert.equal(review('D3', { admittedSources: [] }).identity_or_coverage_state, 'INSUFFICIENT_IDENTITY');
});

test('historical statement timestamp and source record timestamp are distinct exact quoted pointers', () => {
  const result = review('D2');
  const statementTime = result.source_pointers.find(item => item.source === 'U-USN' && item.pointer === '/statements/0/timestamp');
  const recordTime = result.source_pointers.find(item => item.source === 'U-USN' && item.pointer === '/timestamp');
  assert.equal(statementTime.value, '2024-07-01T09:06:31Z');
  assert.equal(statementTime.quote, '"2024-07-01T09:06:31Z"');
  assert.equal(recordTime.value, '2026-04-24T08:06:55.497955Z');
  assert.notEqual(statementTime.value, recordTime.value);
});

test('all original outputs have compact fact cards and no product-array or statement-collection payloads', () => {
  for (const fixture of gold.cases) {
    const result = review(fixture.case_id);
    assert.ok(result.facts.length >= 3 && result.facts.length <= 6, `${fixture.case_id} fact count`);
    assert.ok(result.source_pointers.every(item => item.pointer !== '/statements'
      && !item.pointer.endsWith('/products')));
    assert.ok(JSON.stringify(result).length < 16000, `${fixture.case_id} payload bytes`);
  }
});
