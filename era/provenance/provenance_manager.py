import hashlib
from dataclasses import replace, asdict
from era.provenance.provenance_audit import ProvenanceAudit
from era.provenance.provenance_models import ProvenanceRecord
from era.provenance.provenance_enums import EvidenceStatus
from era.provenance import provenance_errors as errors
from era.shared.persistence import PersistenceError
class EvidenceProvenanceManager:
    """
    C4 rollout, step 3: pass `store=` (era.shared.persistence.SqliteStore)
    to make the provenance chain survive process exit. Pass nothing and
    behavior is unchanged -- in-memory only, exactly as before.

    Persistence error handling: register_evidence() can touch two
    records in one call -- the new one, and (when previous_evidence_id
    is given) the prior record it supersedes. Both in-memory mutations
    are rolled back together if either durable write fails, so a
    superseded-but-not-actually-persisted record can never exist.
    """
    TABLE = "provenance_records"
    def __init__(self, audit=None, store=None):
        self.records = {}
        self.audit = audit or ProvenanceAudit()
        self.store = store
        if self.store:
            self._load_from_store()
    def _load_from_store(self):
        for data in self.store.list_records(self.TABLE):
            record = self._from_dict(data)
            self.records[record.evidence_id] = record
    def _persist(self, record: ProvenanceRecord, conn=None) -> bool:
        if not self.store:
            return True
        try:
            self.store.save_record(self.TABLE, record.evidence_id, self._to_dict(record), conn=conn)
            return True
        except PersistenceError:
            return False
    @staticmethod
    def _to_dict(record: ProvenanceRecord) -> dict:
        data = asdict(record)
        data["status"] = record.status.value
        return data
    @staticmethod
    def _from_dict(data: dict) -> ProvenanceRecord:
        data = dict(data)
        data["status"] = EvidenceStatus(data["status"])
        return ProvenanceRecord(**data)
    def compute_evidence_hash(self, item):
        fields = [
            str(item.evidence_id),
            str(item.property_id),
            str(item.canonical_field),
            str(item.canonical_value),
            str(item.original_value),
            str(item.provider_id),
            str(item.legal_basis),
            str(item.source_reference),
            str(item.retrieved_at),
            str(item.connector_version),
            str(item.adapter_version),
            str(item.normalization_version),
            str(item.previous_evidence_id),
        ]
        trace_fields = [
            str(getattr(item, "artifact_sha256", "")),
            str(getattr(item, "package_id", "")),
            str(getattr(item, "execution_id", "")),
            str(getattr(item, "canonical_source_id", "")),
            str(getattr(item, "parser_id", "")),
            str(getattr(item, "parser_version", "")),
            str(getattr(item, "schema_profile_id", "")),
            str(getattr(item, "schema_profile_version", "")),
            str(getattr(item, "source_location", "")),
            str(getattr(item, "trace_contract_version", "")),
        ]
        integration_fields = [
            str(getattr(item, "candidate_id", "")),
            str(getattr(item, "candidate_validation_status", "")),
            str(getattr(item, "artifact_algorithm", "")),
            str(getattr(item, "artifact_digest", "")),
            str(getattr(item, "artifact_byte_length", "")) if getattr(item, "artifact_byte_length", 0) else "",
            str(getattr(item, "artifact_media_type", "")),
            str(getattr(item, "artifact_content_uri", "")),
            str(getattr(item, "original_lexical_value", "")),
            str(getattr(item, "parsed_value", "")),
            str(getattr(item, "proposed_value_type", "")),
        ]
        if any(trace_fields):
            fields.extend(["TRACE-1", *trace_fields])
        if any(integration_fields):
            fields.extend(["EIA-WIRE-1", *integration_fields])
        payload = "|".join(fields)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    def register_evidence(self, item, conn=None):
        if not item.evidence_id:
            return errors.MISSING_EVIDENCE_ID, None
        if not item.property_id:
            return errors.MISSING_PROPERTY_ID, None
        if not item.provider_id or not item.provider_name:
            return errors.MISSING_PROVIDER, None
        if not item.legal_basis:
            return errors.MISSING_LEGAL_BASIS, None
        if not item.source_reference:
            return errors.MISSING_SOURCE_REFERENCE, None
        if item.evidence_id in self.records:
            return errors.DUPLICATE_EVIDENCE_ID, None
        computed_hash = self.compute_evidence_hash(item)
        if item.evidence_hash and item.evidence_hash != computed_hash:
            return errors.INVALID_HASH, None
        chain_position = 1
        previous = None
        superseded_previous = None
        if item.previous_evidence_id:
            previous = self.records.get(item.previous_evidence_id)
            if previous is None:
                return errors.PREVIOUS_EVIDENCE_NOT_FOUND, None
            if previous.property_id != item.property_id or previous.canonical_field != item.canonical_field:
                return errors.CHAIN_INTEGRITY_FAILURE, None
            chain_position = previous.chain_position + 1
            superseded_previous = replace(
                previous,
                status=EvidenceStatus.SUPERSEDED,
                superseded_by=item.evidence_id,
            )
        record = ProvenanceRecord(
            evidence_id=item.evidence_id,
            property_id=item.property_id,
            canonical_field=item.canonical_field,
            canonical_value=item.canonical_value,
            original_value=item.original_value,
            provider_id=item.provider_id,
            provider_name=item.provider_name,
            legal_basis=item.legal_basis,
            source_reference=item.source_reference,
            retrieved_at=item.retrieved_at,
            connector_version=item.connector_version,
            adapter_version=item.adapter_version,
            normalization_version=item.normalization_version,
            evidence_hash=computed_hash,
            previous_evidence_id=item.previous_evidence_id,
            superseded_by=None,
            chain_position=chain_position,
            status=EvidenceStatus.ACTIVE,
            artifact_sha256=getattr(item, "artifact_sha256", ""),
            package_id=getattr(item, "package_id", ""),
            execution_id=getattr(item, "execution_id", ""),
            canonical_source_id=getattr(item, "canonical_source_id", ""),
            parser_id=getattr(item, "parser_id", ""),
            parser_version=getattr(item, "parser_version", ""),
            schema_profile_id=getattr(item, "schema_profile_id", ""),
            schema_profile_version=getattr(item, "schema_profile_version", ""),
            source_location=getattr(item, "source_location", ""),
            trace_contract_version=getattr(item, "trace_contract_version", ""),
            candidate_id=getattr(item, "candidate_id", ""),
            candidate_validation_status=getattr(item, "candidate_validation_status", ""),
            artifact_algorithm=getattr(item, "artifact_algorithm", ""),
            artifact_digest=getattr(item, "artifact_digest", ""),
            artifact_byte_length=getattr(item, "artifact_byte_length", 0),
            artifact_media_type=getattr(item, "artifact_media_type", ""),
            artifact_content_uri=getattr(item, "artifact_content_uri", ""),
            original_lexical_value=getattr(item, "original_lexical_value", ""),
            parsed_value=getattr(item, "parsed_value", ""),
            proposed_value_type=getattr(item, "proposed_value_type", ""),
        )
        # Apply both in-memory mutations together, then persist both.
        # If either durable write fails, roll both back so the chain
        # can never end up superseded-on-disk-but-not-in-memory (or the
        # reverse) -- this two-record update is treated as one unit.
        if superseded_previous is not None:
            self.records[item.previous_evidence_id] = superseded_previous
        self.records[item.evidence_id] = record
        persisted_previous = self._persist(superseded_previous, conn=conn) if superseded_previous is not None else True
        persisted_record = self._persist(record, conn=conn) if persisted_previous else False
        if not (persisted_previous and persisted_record):
            if superseded_previous is not None:
                self.records[item.previous_evidence_id] = previous
            del self.records[item.evidence_id]
            self.audit.publish("PROVENANCE_BLOCKED", {
                "reason": errors.PERSISTENCE_WRITE_FAILED,
                "evidence_id": item.evidence_id,
            })
            return errors.PERSISTENCE_WRITE_FAILED, None
        self.audit.publish("PROVENANCE_REGISTERED", {
            "evidence_id": record.evidence_id,
            "property_id": record.property_id,
            "field": record.canonical_field,
            "provider_id": record.provider_id,
            "chain_position": record.chain_position,
            "status": record.status.value,
        })
        return errors.PASS, record
    def get_record(self, evidence_id):
        return self.records.get(evidence_id)
    def get_chain(self, evidence_id):
        record = self.records.get(evidence_id)
        if record is None:
            return []
        chain = [record]
        while chain[0].previous_evidence_id:
            previous = self.records.get(chain[0].previous_evidence_id)
            if previous is None:
                break
            chain.insert(0, previous)
        return chain
    def attempt_write(self):
        self.audit.publish("PROVENANCE_BLOCKED", {
            "reason": errors.READ_ONLY_PROVENANCE,
        })
        return False, errors.READ_ONLY_PROVENANCE
    def assign_confidence(self):
        self.audit.publish("PROVENANCE_BLOCKED", {
            "reason": errors.CONFIDENCE_AUTHORITY_VIOLATION,
        })
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
