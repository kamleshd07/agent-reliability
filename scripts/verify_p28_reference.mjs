// Independent data-only contract check. No Python/package imports or dependencies.
import fs from 'node:fs';
import { createHash } from 'node:crypto';
const root = new URL('../tests/fixtures/p28/', import.meta.url);
const read = name => JSON.parse(fs.readFileSync(new URL(name, root), 'utf8'));
const fields = {
  run_lifecycle: ['status', 'occurred_at', 'exception_type'],
  evaluation_outcome: ['evaluation_id', 'indicator', 'outcome', 'recorded_at', 'provenance', 'reason_code'],
  evaluation_execution_failure: ['evaluation_id', 'indicator', 'stage', 'exception_type', 'occurred_at', 'evaluator_name', 'evaluator_version', 'evaluator_configuration_id'],
  measurement_health: ['measurement_id', 'health', 'reasons', 'observed_at'],
};
function instant(value) {
  const fraction = (value.match(/\.(\d{1,6})/)?.[1] ?? '').padEnd(6, '0');
  const seconds = new Date(value).toISOString().slice(0, 19);
  return seconds + (fraction === '000000' ? '' : '.' + fraction) + '+00:00';
}
function ordered(value) {
  if (value === null || typeof value !== 'object') return value;
  if (Array.isArray(value)) return value.map(ordered);
  return Object.fromEntries(Object.keys(value).sort().map(key => [key, ordered(value[key])]));
}
function canonical(wire) {
  const payload = Object.fromEntries(fields[wire.payload.kind].map(key => [key, wire.payload[key] ?? null]));
  for (const key of ['occurred_at', 'recorded_at', 'observed_at']) {
    if (key in payload) payload[key] = instant(payload[key]);
  }
  if ('reasons' in payload) payload.reasons = [...new Set(payload.reasons)].sort().join(',');
  if (payload.provenance) payload.provenance = Object.fromEntries(
    ['name', 'version', 'configuration_id', 'deterministic'].map(key => [key, payload.provenance[key] ?? null])
  );
  const result = Object.fromEntries(['schema_version', 'source', 'event_id', 'producer_run_id', 'deployment_id'].map(key => [key, wire[key]]));
  Object.assign(result, { payload, producer_timestamp: instant(wire.producer_timestamp), parent_producer_run_id: wire.parent_producer_run_id ?? null });
  if (wire.schema_version === 2) result.producer_identity = wire.producer_identity;
  return JSON.stringify(ordered(result)).replace(/[\u007f-\uffff]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
}
let digests = 0;
for (const name of ['v1_digest_vectors.json', 'v2_digest_vectors_specification_only.json']) {
  for (const vector of read(name).vectors) {
    const bytes = canonical(vector.wire_input);
    const digest = createHash('sha256').update(bytes, 'utf8').digest('hex');
    if (bytes !== vector.canonical_utf8_text || digest !== vector.sha256_lowercase_hex) throw Error(vector.id);
    digests++;
  }
}
function classify(status, bytes, sent) {
  if (![200, 201].includes(status)) return 'other_2xx_transient';
  let value;
  try {
    const text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
    if (text.startsWith('\ufeff')) return 'not_ack:response_unparseable';
    value = JSON.parse(text);
  } catch { return 'not_ack:response_unparseable'; }
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return 'not_ack:response_unparseable';
  if (value.event_id === sent && typeof value.run_id === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value.run_id)
    && value.status === (status === 201 ? 'accepted' : 'duplicate') && value.durability === 'committed') return status === 201 ? 'ack:COMMITTED' : 'ack:DUPLICATE';
  return 'not_ack:acknowledgement_mismatch';
}
const operational = read('operational_vectors.json');
let acknowledgements = 0;
for (const group of ['acknowledgement_vectors', 'acknowledgement_byte_vectors', 'acknowledgement_escape_vectors', 'acknowledgement_extra_member_vectors']) {
  for (const vector of operational[group].vectors) {
    const bytes = vector.body_hex ? Buffer.from(vector.body_hex, 'hex') : Buffer.from(vector.body_text, 'utf8');
    const result = classify(vector.http_status, bytes, vector.sent_event_id);
    if (!(vector.allowed ?? [vector.expected]).includes(result)) throw Error(vector.id + ': ' + result);
    acknowledgements++;
  }
}
console.log(`Node reference: ${digests} canonical byte/digest vectors; ${acknowledgements} acknowledgement vectors passed`);
