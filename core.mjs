import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const DEFAULT_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), 'fixtures/original');
const sha256 = value => createHash('sha256').update(value).digest('hex');

/** Canonical JSON for derived evidence identities (source snapshots use raw bytes). */
export function canonicalJSON(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJSON).join(',')}]`;
  return `{${Object.keys(value).filter(key => value[key] !== undefined).sort()
    .map(key => `${JSON.stringify(key)}:${canonicalJSON(value[key])}`).join(',')}}`;
}

/** Load only the manifest's source records. Evaluator gold is never loaded here. */
export function loadSources(root = DEFAULT_ROOT) {
  const manifest = JSON.parse(readFileSync(resolve(root, 'source-manifest.json'), 'utf8'));
  return manifest.source_records.map(metadata => {
    const bytes = readFileSync(resolve(root, metadata.file));
    const hash = sha256(bytes);
    const expected = manifest.file_integrity.find(entry => entry.path === metadata.file);
    if (expected && (hash !== expected.sha256 || bytes.length !== expected.bytes)) {
      throw new Error(`Source integrity check failed: ${metadata.source_id}`);
    }
    return { id: metadata.source_id, document: JSON.parse(bytes.toString('utf8')), hash,
      metadata: structuredClone(metadata) };
  });
}

/** RFC 6901 lookup. The empty pointer selects the complete document. */
export function getPointer(document, pointer) {
  if (pointer === '') return document;
  if (typeof pointer !== 'string' || !pointer.startsWith('/')) return undefined;
  let value = document;
  for (const token of pointer.slice(1).split('/')) {
    if (/~(?:[^01]|$)/.test(token)) return undefined;
    const key = token.replace(/~1/g, '/').replace(/~0/g, '~');
    if (value === null || typeof value !== 'object' || !Object.hasOwn(value, key)) return undefined;
    if (Array.isArray(value) && !/^(0|[1-9][0-9]*)$/.test(key)) return undefined;
    value = value[key];
  }
  return value;
}

/** Checks address, exact JSON value/quote and source snapshot identity independently. */
export function validateEvidencePointer(pointer, { inventory, sources }) {
  if (!pointer || typeof pointer !== 'object') return false;
  const source = pointer.source === 'INVENTORY'
    ? { document: inventory, hash: sha256(canonicalJSON(inventory)) }
    : sources.find(item => item.id === pointer.source);
  if (!source) return false;
  const value = getPointer(source.document, pointer.pointer);
  return value !== undefined && canonicalJSON(value) === canonicalJSON(pointer.value)
    && JSON.stringify(value) === pointer.quote && source.hash === pointer.source_hash;
}

function ubuntuIdentity(purl) {
  // This check establishes sufficient fields only. Matching never normalizes any PURL.
  if (typeof purl !== 'string' || !purl) return { kind: 'missing' };
  if (!purl.startsWith('pkg:deb/ubuntu/')) return { kind: 'outside' };
  const match = /^pkg:deb\/ubuntu\/[^@?]+@([^?]+)\?(.+)$/.exec(purl);
  if (!match) return { kind: 'missing' };
  const entries = match[2].split('&').map(part => part.split('='));
  const arch = entries.filter(([key, value]) => key === 'arch' && value);
  const distro = entries.filter(([key, value]) => key === 'distro' && value);
  if (arch.length !== 1 || distro.length !== 1 || entries.some(part => part.length !== 2)) {
    return { kind: 'missing' };
  }
  return { kind: 'ubuntu', distro: distro[0][1], version: match[1] };
}

/** Pure, CPU-only review of explicitly admitted snapshots and one inventory object. */
export function reviewEvidence({ caseId, inventory, advisoryId, admittedSources = [], sources = [] }) {
  if (!inventory || typeof inventory !== 'object') throw new TypeError('inventory must be an object');
  if (typeof advisoryId !== 'string' || !advisoryId) throw new TypeError('advisoryId is required');
  const ids = [...new Set(admittedSources)].sort();
  const admitted = ids.map(id => sources.find(source => source.id === id)).filter(Boolean);
  if (admitted.some((source, index) => admitted.findIndex(other => other.id === source.id) !== index)) {
    throw new Error('Duplicate source identity');
  }
  const inventoryHash = sha256(canonicalJSON(inventory));
  const pointers = [];
  const facts = [];
  const lookupReceipts = [];
  const unknowns = ['Exact running build is not established by this slice; installed package evidence does not establish the running service build.'];
  const pointer = (source, path) => {
    const origin = source === 'INVENTORY' ? { document: inventory, hash: inventoryHash }
      : admitted.find(item => item.id === source);
    if (!origin) throw new Error(`Pointer source is not admitted: ${source}`);
    const value = getPointer(origin.document, path);
    if (value === undefined) throw new Error(`Missing evidence pointer: ${source}${path}`);
    const existing = pointers.find(item => item.source === source && item.pointer === path);
    if (existing) return existing.id;
    const id = `P${pointers.length + 1}`;
    pointers.push({ id, source, pointer: path, value: structuredClone(value),
      quote: JSON.stringify(value), source_hash: origin.hash });
    return id;
  };
  const fact = (text, pointerIds, lookupIds = []) => facts.push({ id: `F${facts.length + 1}`, text,
    pointer_ids: [...new Set(pointerIds)], ...(lookupIds.length ? { lookup_ids: lookupIds } : {}) });
  const wholeInventory = pointer('INVENTORY', '');
  fact('The review uses this inventory observation and supplied component identity fields; inventory observation time and source record time are separate.', [wholeInventory]);
  fact('Running state remains unknown under the conservative first-slice policy; installation does not prove the running build or restart.', [wholeInventory]);
  for (const id of ids.filter(id => !admitted.some(source => source.id === id))) {
    unknowns.push(`Admitted source ${id} is unavailable; coverage cannot be established from that source.`);
  }
  let state = 'INSUFFICIENT_IDENTITY';
  let vendor = 'not established';
  const candidateMatches = [];

  // Preserve both representations only for the projection's declared CVE and scope.
  const projection = admitted.find(source => source.document.kind === 'research_authored_factual_projection'
    && source.document.cve === advisoryId);
  if (projection) {
    const doc = projection.document;
    const representations = doc.representations ?? [];
    const htmlIndex = representations.findIndex(item => typeof item.source_quote === 'string');
    let cnaIndex = -1;
    let entryIndex = -1;
    representations.forEach((representation, index) => {
      const found = (representation.affected_entries ?? []).findIndex(entry => entry.cpe === inventory.cpe
        && entry.packageName === inventory.component && entry.defaultStatus === 'affected');
      if (found >= 0) { cnaIndex = index; entryIndex = found; }
    });
    if (htmlIndex >= 0 && cnaIndex >= 0 && inventory.cpe && inventory.component) {
      state = 'CONFLICTING_SOURCES';
      const html = pointer(projection.id, `/representations/${htmlIndex}/source_quote`);
      const cna = pointer(projection.id, `/representations/${cnaIndex}/affected_entries/${entryIndex}`);
      const status = pointer(projection.id, `/representations/${cnaIndex}/affected_entries/${entryIndex}/defaultStatus`);
      fact('The admitted projection preserves the vendor HTML statement and the CNA affected representation for this CPE/component. No affected or unaffected conclusion is selected.', [wholeInventory, html, cna, status]);
      const scope = [pointer(projection.id, '/kind'), pointer(projection.id, '/not_authoritative_vex'), pointer(projection.id, '/cve')];
      fact('This is a research-authored factual projection, not authoritative VEX. Fetch time establishes no precedence between its representations.', scope);
      unknowns.push('Dated authoritative vendor/CNA reconciliation and exact artifact version remain missing.');
    } else {
      unknowns.push('The projection does not establish an exact CPE/component scope for this inventory.');
    }
  } else {
    const identity = ubuntuIdentity(inventory.product_purl);
    const inventoryIdentity = Object.hasOwn(inventory, 'product_purl')
      ? pointer('INVENTORY', '/product_purl') : wholeInventory;
    const releaseContradiction = identity.kind === 'ubuntu' && typeof inventory.reported_release === 'string'
      && inventory.reported_release !== identity.distro;
    const unknownScope = identity.kind === 'ubuntu' && inventory.field_scope === 'unknown'
      && Object.hasOwn(inventory, 'reported_release');
    // No access to documents outside admitted: filtering is complete before lookup.
    for (const source of admitted) {
      const statements = source.document.statements;
      if (!Array.isArray(statements)) continue;
      const eligible = [];
      statements.forEach((statement, si) => {
        const vulnerability = statement.vulnerability ?? {};
        const current = /^CVE-/.test(vulnerability.name ?? '') && vulnerability.name === advisoryId;
        const aliasIndex = /^USN-/.test(vulnerability.name ?? '')
          ? (vulnerability.aliases ?? []).indexOf(advisoryId) : -1;
        if (current || aliasIndex >= 0) eligible.push({ statement, si, historical: !current, aliasIndex });
      });
      const matches = [];
      for (const item of eligible) {
        (item.statement.products ?? []).forEach((product, pi) => {
          if (typeof inventory.product_purl === 'string' && product['@id'] === inventory.product_purl) {
            matches.push({ ...item, source, pi });
          }
        });
      }
      const candidateCount = eligible.reduce((count, item) => count + (item.statement.products ?? []).length, 0);
      const lookupId = `L${lookupReceipts.length + 1}`;
      lookupReceipts.push({ id: lookupId, source: source.id, source_hash: source.hash,
        collection_path: '/statements', advisory_id: advisoryId, inventory_hash: inventoryHash,
        inventory_pointer: Object.hasOwn(inventory, 'product_purl') ? '/product_purl' : '',
        match_rule: 'literal_complete_purl_and_explicit_advisory_identity',
        eligible_statement_count: eligible.length, candidate_count: candidateCount, exact_match_count: matches.length });
      if (matches.length === 0) {
        // Absence is a computed search result, not a fabricated product/scalar
        // pointer. The receipt records the inspectable collection and snapshot.
        const grounding = [inventoryIdentity];
        for (const item of eligible) grounding.push(pointer(source.id, `/statements/${item.si}/vulnerability/name`));
        if (Object.hasOwn(source.document, 'timestamp')) grounding.push(pointer(source.id, '/timestamp'));
        fact(`Literal complete PURL lookup in ${source.id}: ${candidateCount} candidate product entries, 0 exact matches. Coverage remains unresolved; absence supplies no affected or not-affected status.`, grounding, [lookupId]);
      }
      candidateMatches.push(...matches);
      if (matches.length === 0 && identity.kind === 'ubuntu') {
        unknowns.push(`No exact product/advisory match in admitted ${source.id}; this snapshot's coverage remains unresolved.`);
      }
    }
    // Prefer a matching current-CVE statement to a related historical record, but
    // never settle contradictory statuses by record/retrieval chronology.
    const statuses = new Set(candidateMatches.map(item => item.statement.status));
    const chosen = candidateMatches.find(item => !item.historical) ?? candidateMatches[0];
    for (const item of candidateMatches) {
      const base = `/statements/${item.si}`;
      const grounding = [inventoryIdentity, pointer(item.source.id, `${base}/products/${item.pi}/@id`),
        pointer(item.source.id, `${base}/status`), pointer(item.source.id, `${base}/vulnerability/name`)];
      if (item.historical) grounding.push(pointer(item.source.id, `${base}/vulnerability/aliases/${item.aliasIndex}`));
      if (Object.hasOwn(item.statement, 'justification')) grounding.push(pointer(item.source.id, `${base}/justification`));
      if (Object.hasOwn(item.statement, 'timestamp')) grounding.push(pointer(item.source.id, `${base}/timestamp`));
      if (Object.hasOwn(item.source.document, 'timestamp')) grounding.push(pointer(item.source.id, '/timestamp'));
      if (Object.hasOwn(item.source.document, 'version')) grounding.push(pointer(item.source.id, '/version'));
      const justification = Object.hasOwn(item.statement, 'justification')
        ? ` Vendor justification: ${JSON.stringify(item.statement.justification)}.` : '';
      fact(`${item.source.id} states ${JSON.stringify(item.statement.status)} for the literal package identity supplied in inventory and ${item.historical ? 'historical notice with an explicit alias to' : 'current vulnerability named'} ${advisoryId}.${justification} Applicability is limited to that identity and advisory.`, grounding);
    }
    if (identity.kind === 'missing') {
      unknowns.push('Complete vendor package identity, including version, architecture and release, is missing.');
    } else if (identity.kind === 'outside') {
      state = 'OUTSIDE_VENDOR_IDENTITY';
      unknowns.push('The identity is outside the Ubuntu archive namespace; no vendor build equivalence is established.');
      fact('The supplied identity is outside the Ubuntu archive package namespace; software name or upstream version cannot transfer a vendor statement.', [inventoryIdentity]);
    } else if (unknownScope) {
      state = 'INSUFFICIENT_IDENTITY';
      unknowns.push('Inventory release fields have unknown scope; applicability requires their component/environment relationship.');
      fact('The release-field scope is explicitly unknown. Applicability remains unresolved without assuming a host/container relationship.', [inventoryIdentity, pointer('INVENTORY', '/reported_release'), pointer('INVENTORY', '/field_scope')]);
    } else if (releaseContradiction) {
      state = 'CONFLICTING_INVENTORY_IDENTITY';
      vendor = chosen ? `conditional ${chosen.statement.status} candidate only` : 'not established';
      unknowns.push('Reconcile the PURL release and reported release for the same component/environment before deciding applicability.');
      fact(`The complete PURL release ${JSON.stringify(identity.distro)} conflicts with reported release ${JSON.stringify(inventory.reported_release)} in the same component/environment scope. Any matching vendor statement is conditional.`, [inventoryIdentity, pointer('INVENTORY', '/reported_release')]);
    } else if (statuses.size > 1) {
      state = 'CONFLICTING_SOURCES';
      unknowns.push('Admitted exact-product statements disagree; authoritative reconciliation remains missing.');
    } else if (chosen) {
      state = chosen.historical ? 'HISTORICAL_ADVISORY_EXACT_MATCH' : 'EXACT_MATCH';
      vendor = chosen.statement.status;
      if (inventory.running_banner) {
        state = 'EXACT_INSTALLED_MATCH_RUNNING_UNRESOLVED';
        const upstream = identity.version.replace(/^\d+:/, '').split('-')[0];
        const compatible = inventory.running_banner === `OpenSSH_${upstream}`;
        fact(compatible
          ? `The banner ${JSON.stringify(inventory.running_banner)} is compatible with the installed upstream ${JSON.stringify(upstream)}. It lacks the Debian revision and cannot establish the exact running package build, restart or running fix state.`
          : 'The supplied banner does not establish the exact running package build, restart or running fix state.',
        [inventoryIdentity, pointer('INVENTORY', '/running_banner')]);
        unknowns.push('The observed banner lacks evidence of the exact running Debian package revision; restart and running fix state remain unknown.');
      }
    } else {
      state = admitted.length === 0 ? 'INSUFFICIENT_EVIDENCE' : 'NO_EXACT_MATCH';
      unknowns.push(admitted.length === 0
        ? 'No admitted source snapshot is available; no package/advisory lookup could be completed.'
        : 'No exact admitted package/advisory statement is established; coverage remains unresolved.');
    }
  }
  const result = {
    case_id: caseId ?? null,
    inventory_id: inventory.inventory_id ?? null,
    advisory_id: advisoryId,
    source_ids: admitted.map(source => source.id),
    source_snapshot_hashes: Object.fromEntries(admitted.map(source => [source.id, source.hash])),
    source_metadata: Object.fromEntries(admitted.map(source => [source.id, structuredClone(source.metadata ?? {})])),
    identity_or_coverage_state: state,
    vendor_statement: vendor,
    source_pointers: pointers,
    running_state: 'unknown',
    unknowns: [...new Set(unknowns)],
    review_required: true,
    inventory_hash: inventoryHash,
    facts,
    lookup_receipts: lookupReceipts,
  };
  return { ...result, evidence_fingerprint: sha256(canonicalJSON(result)) };
}
