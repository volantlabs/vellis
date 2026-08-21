"""Preview and atomically publish one exact streamed v1 initialization."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from vellis.audit import audit_connection
from vellis.canonical_encoding import (
    ZERO_HASH,
    CanonicalHeader,
    RowDescriptor,
    canonical_record_hash_members,
    descriptor_member,
)
from vellis.database import connect_database, create_schema
from vellis.definition_repository import insert_definition_version, load_definitions
from vellis.domain import ObjectKind, ResolvedState, parse_timestamp
from vellis.effective_validation import effective_findings
from vellis.graph_repository import insert_graph_version
from vellis.operations import _bounded_summary, _flush_directory, _flush_file, _utc_now
from vellis.search_repository import insert_search_versions
from vellis.v1_association_conversion import convert_associations
from vellis.v1_candidate import iter_definitions, iter_objects
from vellis.v1_candidate_validation import staged_candidate_findings
from vellis.v1_definition_conversion import convert_definitions
from vellis.v1_graph_conversion import convert_graph
from vellis.v1_identity import scan_identity_reservations
from vellis.v1_import_domain import (
    V1Counts,
    V1Disposition,
    V1DispositionCounts,
    V1ImportError,
    V1ImportPreview,
    V1ImportResult,
    V1PublicationDurabilityError,
)
from vellis.v1_provenance import finding_source_pointer, finding_targets
from vellis.v1_report import (
    add_disposition,
    disposition_counts,
    render_machine_report,
    write_human_report,
)
from vellis.v1_stage import STAGE_RELATION, create_stage, stage_source


def preview_v1_import(
    source: Path,
    *,
    report_out: Path | None = None,
    human_report_out: Path | None = None,
    recorded_at: str | None = None,
) -> V1ImportPreview:
    """Analyze one source without publishing a Vellis database."""
    with tempfile.TemporaryDirectory(prefix="vellis-v1-preview-") as directory:
        root = Path(directory)
        built = _build_candidate(
            source.resolve(),
            root / "candidate.db",
            root / "report.json",
            root / "report.txt",
            recorded_at,
        )
        if report_out is not None:
            _copy_report(root / "report.json", report_out.resolve())
        if human_report_out is not None:
            _copy_report(root / "report.txt", human_report_out.resolve())
        return V1ImportPreview(
            built.source_path,
            built.source_sha256,
            built.source_byte_count,
            built.candidate_sha256,
            built.report_sha256,
            built.candidate_counts,
            built.disposition_counts,
            built.acceptable,
            report_out.resolve() if report_out is not None else None,
        )


def initialize_from_v1(
    source: Path,
    database_path: Path,
    *,
    confirmed_source_sha256: str,
    confirmed_report_sha256: str,
    recorded_at: str | None = None,
) -> V1ImportResult:
    """Rebuild the preview and publish only when both exact digests still match."""
    destination = database_path.resolve()
    _prepare_empty_destination(destination)
    publication_root = _private_publication_root(destination.parent)
    database_temp = publication_root / destination.name
    report_temp = publication_root / "v1-import-report.json"
    human_temp = publication_root / "v1-import-report.txt"
    report_destination = destination.parent / report_temp.name
    try:
        built = _build_candidate(
            source.resolve(), database_temp, report_temp, human_temp, recorded_at
        )
        if built.source_sha256 != confirmed_source_sha256:
            raise V1ImportError("the v1 source digest does not match the confirmed preview")
        if built.report_sha256 != confirmed_report_sha256:
            raise V1ImportError("the v1 report digest does not match the confirmed preview")
        if not built.acceptable:
            raise V1ImportError("the v1 report contains blocking dispositions")
        human_temp.unlink()
        os.chmod(database_temp, 0o600)
        _flush_file(database_temp)
        _flush_file(report_temp)
        _flush_directory(publication_root)
        _publish_directory(publication_root, destination.parent)
        _flush_directory_after_publication(destination.parent.parent)
        return V1ImportResult(
            destination,
            report_destination,
            built.lineage_uuid,
            built.source_sha256,
            built.report_sha256,
        )
    finally:
        for path in (database_temp, report_temp, human_temp):
            _remove_family(path)
        try:
            publication_root.rmdir()
        except FileNotFoundError:
            pass


def _build_candidate(source, database, report, human_report, recorded_at):
    connection = connect_database(database)
    try:
        create_schema(connection)
        create_stage(connection)
        connection.execute("BEGIN IMMEDIATE")
        source_sha256, source_bytes = stage_source(connection, source)
        _begin_revision_zero(connection, recorded_at)
        scan_identity_reservations(connection)
        convert_associations(connection)
        convert_definitions(connection)
        convert_graph(connection)
        candidate_digest = _candidate_digest(connection)
        counts = _candidate_counts(connection)
        if disposition_counts(connection).blocking == 0:
            _record_candidate_findings(connection, staged_candidate_findings(connection))
        if disposition_counts(connection).blocking == 0:
            _insert_candidate(connection)
            _record_candidate_findings(
                connection, effective_findings(connection, ResolvedState(0), draft=False)
            )
        report_digest = render_machine_report(
            connection,
            report,
            source_sha256=source_sha256,
            source_byte_count=source_bytes,
            candidate_sha256=candidate_digest,
            counts=counts,
        )
        write_human_report(
            connection,
            human_report,
            source_sha256=source_sha256,
            candidate_sha256=candidate_digest,
        )
        summary = disposition_counts(connection)
        lineage_uuid = _lineage_uuid(connection)
        if summary.blocking == 0:
            _seal_revision_zero(connection, counts, bytes.fromhex(report_digest))
            connection.execute(f"DROP TABLE {STAGE_RELATION}")
            audit = audit_connection(connection)
            if not audit.clean:
                raise V1ImportError(f"unpublished v1 candidate failed audit: {audit.findings[0]}")
            connection.commit()
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        else:
            connection.rollback()
        return _BuiltCandidate(
            source,
            source_sha256,
            source_bytes,
            candidate_digest,
            report_digest,
            counts,
            summary,
            summary.blocking == 0,
            lineage_uuid,
        )
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


@dataclass(frozen=True, slots=True)
class _BuiltCandidate:
    source_path: Path
    source_sha256: str
    source_byte_count: int
    candidate_sha256: str
    report_sha256: str
    candidate_counts: V1Counts
    disposition_counts: V1DispositionCounts
    acceptable: bool
    lineage_uuid: str


def _record_candidate_findings(connection, findings):
    for finding in findings:
        target_uuid, target_type_key, target_property = finding_targets(connection, finding)
        add_disposition(
            connection,
            V1Disposition.BLOCKING,
            "candidate-nonconforming",
            finding_source_pointer(connection, finding),
            finding.summary,
            target_type_key=target_type_key,
            target_uuid=target_uuid,
            target_property=target_property,
        )


def _begin_revision_zero(connection, recorded_at):
    lineage_uuid = str(uuid.uuid4())
    timestamp = parse_timestamp(recorded_at or _utc_now())
    connection.execute(
        """INSERT INTO canonical_record(
            revision,recorded_at,recorded_epoch_seconds,recorded_nanosecond,
            initiator,source,transition_kind,summary,affected_type_keys,affected_uuids,
            previous_hash,record_hash)
            VALUES(0,?,?,?,'owner','vellis setup: v1 import','initialization',
                   'unsealed v1 candidate','[]','[]',?,?)""",
        (timestamp.canonical, timestamp.epoch_seconds, timestamp.nanosecond, ZERO_HASH, ZERO_HASH),
    )
    connection.execute(
        "INSERT INTO metadata_setting(singleton,lineage_uuid,head_revision) VALUES(1,?,0)",
        (lineage_uuid,),
    )


def _insert_candidate(connection):
    try:
        for kind in ("anchor", "associatedData", "link"):
            for definition in (
                value for value in iter_definitions(connection) if value.kind.value == kind
            ):
                descriptors = insert_definition_version(connection, definition, 0)
                _store_descriptors(connection, descriptors)
        object_kinds = (
            ObjectKind.ANCHOR.value,
            ObjectKind.ASSOCIATED_DATA.value,
            ObjectKind.LINK.value,
        )
        for kind in object_kinds:
            for value in iter_objects(connection, kind):
                definitions = load_definitions(connection, ResolvedState(0), (value.type_key,))
                descriptors = insert_graph_version(connection, value, definitions, 0)
                _store_descriptors(connection, descriptors)
                insert_search_versions(connection, (value,), 0)
    except (sqlite3.IntegrityError, ValueError) as error:
        raise V1ImportError(
            "validated candidate could not be persisted in the unpublished database"
        ) from error


def _store_descriptors(connection, values: tuple[RowDescriptor, ...]):
    ordinal = int(
        connection.execute(
            f"SELECT count(*) FROM {STAGE_RELATION} WHERE category='descriptor'"
        ).fetchone()[0]
    )
    for value in values:
        identity, member = descriptor_member(value)
        connection.execute(
            f"""INSERT INTO {STAGE_RELATION}(
                category,natural_key,ordinal,source_pointer,sort_key,member)
                VALUES('descriptor',?,?, '',?,?)""",
            (value.relation_name, ordinal, identity, member),
        )
        ordinal += 1


def _seal_revision_zero(connection, counts, report_digest):
    timestamp = parse_timestamp(
        str(connection.execute("SELECT recorded_at FROM canonical_record").fetchone()[0])
    )
    lineage_uuid = _lineage_uuid(connection)
    summary = _bounded_summary(
        "Imported Vellis v1 snapshot: "
        f"definitions={counts.definitions}, graphObjects="
        f"{counts.anchors + counts.associated_data + counts.links}"
    )
    header = CanonicalHeader(
        lineage_uuid,
        0,
        timestamp,
        "owner",
        "vellis setup: v1 import",
        "initialization",
        summary,
        report_digest,
    )
    payload_length = int(
        connection.execute(
            f"SELECT coalesce(sum(8+length(member)),0) FROM {STAGE_RELATION} "
            "WHERE category='descriptor'"
        ).fetchone()[0]
    )
    members = (
        bytes(row[0])
        for row in connection.execute(
            f"SELECT member FROM {STAGE_RELATION} WHERE category='descriptor' "
            "ORDER BY natural_key,sort_key"
        )
    )
    record_hash = canonical_record_hash_members(ZERO_HASH, header, payload_length, members, 0, ())
    connection.execute(
        """UPDATE canonical_record SET summary=?,affected_type_keys=?,affected_uuids=?,
            record_hash=?,v1_report_digest=? WHERE revision=0""",
        (
            summary,
            _affected_json(connection, "definition_version", "type_key"),
            _affected_json(connection, "graph_object_version", "uuid"),
            record_hash,
            report_digest,
        ),
    )


def _candidate_digest(connection):
    digest = hashlib.sha256()
    rows = connection.execute(
        f"SELECT category,natural_key,payload FROM {STAGE_RELATION} "
        "WHERE category IN ('candidateDefinition','candidateObject') "
        "ORDER BY category,natural_key"
    )
    for category, key, payload in rows:
        for value in (str(category), str(key), str(payload)):
            encoded = value.encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
    return digest.hexdigest()


def _candidate_counts(connection):
    def count(category, kind):
        return int(
            connection.execute(
                f"SELECT count(*) FROM {STAGE_RELATION} WHERE category=? "
                "AND json_extract(payload,'$.kind')=?",
                (category, kind),
            ).fetchone()[0]
        )

    return V1Counts(
        count("candidateDefinition", "anchor")
        + count("candidateDefinition", "associatedData")
        + count("candidateDefinition", "link"),
        count("candidateObject", "anchor"),
        count("candidateObject", "associatedData"),
        count("candidateObject", "link"),
    )


def _lineage_uuid(connection):
    return str(
        connection.execute(
            "SELECT lineage_uuid FROM metadata_setting WHERE singleton=1"
        ).fetchone()[0]
    )


def _affected_json(connection, relation, column):
    value = connection.execute(
        f"SELECT json_group_array(value) FROM "
        f"(SELECT DISTINCT {column} AS value FROM {relation} ORDER BY value)"
    ).fetchone()[0]
    return str(value)


def _prepare_empty_destination(destination):
    if destination.exists():
        raise FileExistsError(f"v1 destination already exists: {destination}")
    parent = destination.parent
    if not parent.exists():
        parent.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    elif not parent.is_dir():
        raise NotADirectoryError(f"v1 destination parent is not a directory: {parent}")
    elif any(parent.iterdir()):
        raise FileExistsError(f"v1 initialization destination is not empty: {parent}")
    if parent.exists() and os.name == "posix" and stat.S_IMODE(parent.stat().st_mode) != 0o700:
        raise PermissionError("v1 initialization destination must use owner-private mode 0700")


def _private_publication_root(destination):
    value = Path(tempfile.mkdtemp(prefix=f".{destination.name}.v1-", dir=destination.parent))
    os.chmod(value, 0o700)
    return value


def _private_temp(destination, suffix):
    descriptor, name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=suffix, dir=destination.parent
    )
    os.fchmod(descriptor, 0o600)
    os.close(descriptor)
    return Path(name)


def _copy_report(source, destination):
    if destination.exists():
        raise FileExistsError(f"report destination already exists: {destination}")
    if not destination.parent.is_dir():
        raise FileNotFoundError(f"report directory does not exist: {destination.parent}")
    temporary = _private_temp(destination, ".report-copy")
    try:
        with source.open("rb") as reader, temporary.open("wb") as writer:
            while block := reader.read(1024 * 1024):
                writer.write(block)
            writer.flush()
            os.fsync(writer.fileno())
        os.link(temporary, destination)
        temporary.unlink()
    finally:
        temporary.unlink(missing_ok=True)


def _publish_directory(temporary, destination):
    try:
        os.rename(temporary, destination)
    except FileExistsError as error:
        raise FileExistsError(
            f"v1 destination changed during publication: {destination}"
        ) from error


def _flush_directory_after_publication(path):
    try:
        _flush_directory(path)
    except OSError as error:
        raise V1PublicationDurabilityError(
            "v1 database and report are published, but directory durability is unconfirmed"
        ) from error


def _remove_family(path):
    for value in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        value.unlink(missing_ok=True)
