"""Reading one Vellis v1 system snapshot into a v2 first-use candidate.

Realizes ``RTG::'Recovery Candidate'``, ``RTG::'Recovery Finding'``,
``RTG::'Recovery Report'``, ``Vellis::'V1 JSON System Snapshot'``,
``Vellis::'V1 Import Preview'``, and the analysis half of
``VellisRequirements::v1SnapshotCompatibility``.

Everything here is transient. Analysis produces a candidate and a report bound to the
exact snapshot that produced them; nothing is established until an owner has seen that
pair and said yes, and the pair is not an operation on an existing system — there is no
merge and no replacement anywhere in this module.

Two rules shape the whole translation. Graph content is carried across unchanged: every
identifier, kind, type key, name, nested value, and piece of metadata arrives as it was
stored, and where v1 content cannot be carried the import is refused rather than
repaired. Vocabulary, by contrast, is translated — v1 says some things v2 cannot say —
and every place a rule narrowed, a refinement fell away, or a definition was left out is
named in the report. What is never done is inventing meaning to fill a gap: a v1 rule
this cannot express is removed and said out loud, not approximated.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import Enum
from hashlib import sha256

from vellis.canonical import CanonicalState
from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    DirectAssociationEnd,
    DirectAssociationMultiplicityConstraint,
    EndpointConstraint,
    GraphDefinitionSet,
    LinkEnd,
    LinkMultiplicityConstraint,
    LinkTypeDefinition,
    PropertyConstraint,
    RelationshipConstraint,
    StringPattern,
    ValueRange,
    relationship_identity,
    relationship_label,
)
from vellis.graph import (
    Anchor,
    AssociatedDataObject,
    Graph,
    Link,
    MetadataError,
    SystemMetadata,
)
from vellis.json_value import (
    JsonKind,
    JsonValue,
    JsonValueError,
    dumps,
    json_equal,
    json_kind,
    normalize,
)
from vellis.patterns import PatternError, compile_pattern
from vellis.replay import state_findings

__all__ = [
    "ImportPreview",
    "RecoveryCandidate",
    "RecoveryDisposition",
    "RecoveryFinding",
    "RecoveryReport",
    "SnapshotError",
    "analyze_v1_snapshot",
    "looks_like_v1_snapshot",
    "recovery_summary",
    "snapshot_identity",
]

# The four sections a v1 system snapshot carries. A v1 snapshot names no format and no
# version, so this is the only thing that identifies one; a file missing any of them is
# something else and is not read as a snapshot.
V1_SECTIONS = ("graph", "schema", "constraints", "migration")

# How a v1 value kind is said in v2. Two v1 kinds land on one v2 kind: v1 separates
# whole numbers from the rest, and writes a UUID as the string it is stored as. Neither
# distinction is a v2 kind, so both are ordinary translation rather than loss.
_VALUE_KINDS = {
    "string": JsonKind.STRING,
    "integer": JsonKind.NUMBER,
    "number": JsonKind.NUMBER,
    "boolean": JsonKind.BOOLEAN,
    "null": JsonKind.NULL,
    "object": JsonKind.OBJECT,
    "list": JsonKind.ARRAY,
    "uuid": JsonKind.STRING,
}

# The v1 property conditions this carries across. Everything else a rule says — a format,
# a nested field rule, anything a later v1 added — is reported as a condition that did not
# come with it. Named this way round because the list of things v2 can say is knowable and
# the list of things v1 might say is not.
_CARRIED_FIELD_KEYS = frozenset(
    {"required", "value_kinds", "allowed_values", "minimum", "maximum", "pattern", "description"}
)


class RecoveryDisposition(Enum):
    """What became of one piece of v1 meaning.

    Exactly the four the model names. A narrowing, a refinement that fell away, and a
    description written where v1 had none are all one disposition — the meaning arrived
    simplified — and which of them it was is what the summary is for.
    """

    PRESERVED = "preserved"
    SIMPLIFIED = "simplified"
    OMITTED = "omitted"
    BLOCKING = "blocking"


class SnapshotError(ValueError):
    """Raised when a document cannot be read as a v1 system snapshot at all.

    Distinct from a blocking finding: a finding is something true about a snapshot this
    could read, and belongs in a report an owner sees. This is the document not being
    one, which there is nothing to report about.
    """


@dataclass(frozen=True, slots=True)
class RecoveryFinding:
    """One thing the owner is told about their import before they confirm it."""

    disposition: RecoveryDisposition
    summary: str


@dataclass(frozen=True, slots=True)
class RecoveryCandidate:
    """The transient graph and vocabulary an accepted import would establish."""

    graph: Graph
    active_definitions: GraphDefinitionSet


@dataclass(frozen=True, slots=True)
class RecoveryReport:
    """The complete account of one candidate: what it holds and what it cost."""

    candidate: RecoveryCandidate
    findings: tuple[RecoveryFinding, ...] = ()

    @property
    def blocking_findings(self) -> tuple[RecoveryFinding, ...]:
        return tuple(
            each for each in self.findings if each.disposition is RecoveryDisposition.BLOCKING
        )


@dataclass(frozen=True, slots=True)
class ImportPreview:
    """One report, bound to the exact snapshot that produced it.

    The binding is the whole point of the identity: an owner confirms this preview, not
    "an import", and a snapshot that changed underneath is a different preview that has
    not been confirmed. The candidate is read through the report rather than held beside
    it, so there is no arrangement in which the two could describe different things.
    """

    source_identity: str
    report: RecoveryReport

    @property
    def candidate(self) -> RecoveryCandidate:
        return self.report.candidate

    @property
    def is_acceptable(self) -> bool:
        return not self.report.blocking_findings


def looks_like_v1_snapshot(content: JsonValue) -> bool:
    """Say whether a document presents itself as a v1 system snapshot."""
    return isinstance(content, dict) and all(section in content for section in V1_SECTIONS)


def snapshot_identity(content: JsonValue) -> str:
    """Return a stable identity for the exact snapshot content.

    Taken over the canonical serialization rather than the file's bytes, so that
    reformatting is not treated as a changed snapshot and a changed value always is.
    """
    return sha256(dumps(normalize(content)).encode("utf-8")).hexdigest()


def recovery_summary(preview: ImportPreview) -> str:
    """Return the bounded sentence an accepted import records permanently."""
    graph = preview.candidate.graph
    definitions = preview.candidate.active_definitions
    return (
        f"first-use recovery from a Vellis v1 snapshot ({preview.source_identity[:12]}) "
        f"with {_counted(len(graph.anchors), 'anchor')}, "
        f"{_counted(len(graph.associated_data), 'associated-data object')}, "
        f"{_counted(len(graph.links), 'link')}, "
        f"{_counted(len(definitions.anchor_types), 'anchor type')}, "
        f"{_counted(len(definitions.associated_data_types), 'associated-data type')}, and "
        f"{_counted(len(definitions.link_types), 'link type')}"
    )


def _counted(total: int, noun: str) -> str:
    """Say how many of something there are, in the words that fit that many."""
    return f"{total} {noun}" if total == 1 else f"{total} {noun}s"


def analyze_v1_snapshot(content: JsonValue) -> ImportPreview:
    """Read one complete v1 snapshot into a candidate and a report bound to it.

    Analysis always produces a preview. A snapshot this cannot import produces one whose
    report carries blocking findings, because an owner is owed the reason as much as the
    refusal; only a document that is not a snapshot at all raises.
    """
    if not looks_like_v1_snapshot(content):
        raise SnapshotError(
            "this is not a Vellis v1 system snapshot: a snapshot carries " + ", ".join(V1_SECTIONS)
        )
    assert isinstance(content, dict)
    findings: list[RecoveryFinding] = []
    graph = Graph()
    definitions = GraphDefinitionSet()
    complete = True
    try:
        graph = _recovered_graph(_section(content, "graph"), findings)
        translation = _Translation()
        _read_definitions(_section(content, "schema"), graph, translation, findings)
        _report_untranslatable_sections(content, translation, findings)
        definitions = _translated_vocabulary(translation, graph, findings)
    except SnapshotError as unreadable:
        # A section this cannot read stops the reading but not the report: what was
        # already understood stays in it, and the reason it stopped joins it.
        complete = False
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.BLOCKING,
                summary=f"this snapshot cannot be read past that point: {unreadable}",
            )
        )
    candidate = RecoveryCandidate(graph=graph, active_definitions=definitions)
    if complete:
        # Only what was read whole can be held to what it says. Asking a half-read
        # vocabulary whether it describes the graph would say the owner's own content is
        # wrong, when what is wrong is that the reading stopped.
        findings.extend(_conformance_findings(candidate))
    if not any(each.disposition is RecoveryDisposition.BLOCKING for each in findings):
        findings.insert(0, _preserved_finding(candidate))
    report = RecoveryReport(candidate=candidate, findings=tuple(findings))
    return ImportPreview(source_identity=snapshot_identity(content), report=report)


# --- Reading the document -----------------------------------------------------------


def _section(content: Mapping[str, JsonValue], name: str) -> Mapping[str, JsonValue]:
    section = content.get(name)
    if not isinstance(section, dict):
        raise SnapshotError(f"the snapshot's {name} section is not an object")
    return section


def _entries(section: Mapping[str, JsonValue], name: str) -> tuple[Mapping[str, JsonValue], ...]:
    entries = section.get(name, [])
    if not isinstance(entries, list):
        raise SnapshotError(f"the snapshot's {name} is not a list")
    read: list[Mapping[str, JsonValue]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise SnapshotError(f"an entry in {name} is not an object")
        read.append(entry)
    return tuple(read)


def _text(entry: Mapping[str, JsonValue], name: str, *, where: str) -> str:
    value = entry.get(name)
    if not isinstance(value, str) or not value:
        raise SnapshotError(f"{where} has no {name}")
    return value


def _is_live(entry: Mapping[str, JsonValue]) -> bool:
    """Say whether a v1 record is live. A record that does not say is."""
    system = entry.get("system", {})
    if not isinstance(system, dict):
        raise SnapshotError("a v1 record's system metadata is not an object")
    live = system.get("live", True)
    if not isinstance(live, bool):
        raise SnapshotError("a v1 record's system.live is not a boolean")
    return live


def _metadata(entry: Mapping[str, JsonValue]) -> SystemMetadata:
    system = entry.get("system", {})
    assert isinstance(system, dict)
    try:
        return SystemMetadata(members=dict(system))
    except (MetadataError, JsonValueError) as error:
        raise SnapshotError(f"a v1 record's system metadata cannot be carried: {error}") from error


# --- Graph --------------------------------------------------------------------------


def _recovered_graph(section: Mapping[str, JsonValue], findings: list[RecoveryFinding]) -> Graph:
    """Carry every live object across unchanged, and say what was left behind."""
    anchors = _entries(section, "anchors")
    data_objects = _entries(section, "data_objects")
    links = _entries(section, "links")
    index = section.get("anchor_data_index", {})
    if not isinstance(index, dict):
        raise SnapshotError("the snapshot's anchor_data_index is not an object")
    for anchor_uuid, data_uuids in index.items():
        if not isinstance(data_uuids, list):
            raise SnapshotError(
                f"the associations recorded for anchor {anchor_uuid} are not a list"
            )

    live_anchors = _live(anchors, "anchor", findings)
    live_data = _live(data_objects, "associated-data object", findings)
    live_links = _live(links, "link", findings)

    recovered_anchors = tuple(
        each
        for each in (_read(_recovered_anchor, entry, findings) for entry in live_anchors)
        if each is not None
    )
    # An association to an anchor v1 retired is not a live relationship, and only those
    # become memory. Leaving it out is what live filtering means here, not repair: an
    # association to an anchor the snapshot never had is dangling, and still refuses.
    retired = {each for each in _uuids(anchors) if each not in _uuids(live_anchors)}
    recovered_data = tuple(
        each
        for each in (
            _read(_recovered_data_object, entry, findings, index, retired) for entry in live_data
        )
        if each is not None
    )
    recovered_links = tuple(
        each
        for each in (_read(_recovered_link, entry, findings) for entry in live_links)
        if each is not None
    )
    return Graph(anchors=recovered_anchors, associated_data=recovered_data, links=recovered_links)


def _read[T](
    reader: Callable[..., T],
    entry: Mapping[str, JsonValue],
    findings: list[RecoveryFinding],
    *rest: object,
) -> T | None:
    """Read one graph record, or say why it could not be read and carry on.

    A record this cannot read makes the import impossible, but not the account of it: the
    owner is owed every reason at once, not the first one in file order.
    """
    try:
        return reader(entry, findings, *rest)
    except SnapshotError as unreadable:
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.BLOCKING,
                summary=f"a v1 record cannot be read: {unreadable}",
            )
        )
        return None


def _live(
    entries: Sequence[Mapping[str, JsonValue]], kind: str, findings: list[RecoveryFinding]
) -> tuple[Mapping[str, JsonValue], ...]:
    live: list[Mapping[str, JsonValue]] = []
    for entry in entries:
        try:
            is_live = _is_live(entry)
        except SnapshotError as unreadable:
            findings.append(
                RecoveryFinding(
                    disposition=RecoveryDisposition.BLOCKING,
                    summary=f"a v1 {kind} cannot be read: {unreadable}",
                )
            )
            continue
        if is_live:
            live.append(entry)
            continue
        identity = entry.get("type_key") or entry.get("uuid")
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.OMITTED,
                summary=(
                    f"the non-live {kind} {identity} is not imported; only live v1 content "
                    "becomes memory"
                ),
            )
        )
    return tuple(live)


def _recovered_anchor(entry: Mapping[str, JsonValue], findings: list[RecoveryFinding]) -> Anchor:
    uuid = _text(entry, "uuid", where="an anchor")
    type_key = _text(entry, "type", where=f"anchor {uuid}")
    stored = entry.get("display_name")
    if isinstance(stored, str):
        display_name = stored
    else:
        # Built from the two values the anchor does carry, and marked plainly so nobody
        # mistakes it for a name their owner chose.
        display_name = f"[recovered] {type_key} {uuid}"
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.SIMPLIFIED,
                summary=f"anchor {uuid} had no display name and is called {display_name!r}",
            )
        )
    return Anchor(
        uuid=uuid,
        type_key=type_key,
        display_name=display_name,
        system_metadata=_metadata(entry),
    )


def _uuids(entries: Sequence[Mapping[str, JsonValue]]) -> set[str]:
    """The uuids of the records that have one, for asking which of them are still here."""
    found = (each.get("uuid") for each in entries)
    return {each for each in found if isinstance(each, str)}


def _recovered_data_object(
    entry: Mapping[str, JsonValue],
    findings: list[RecoveryFinding],
    index: Mapping[str, JsonValue],
    retired: set[str],
) -> AssociatedDataObject:
    uuid = _text(entry, "uuid", where="an associated-data object")
    type_key = _text(entry, "type", where=f"associated-data object {uuid}")
    properties = entry.get("properties", {})
    if not isinstance(properties, dict):
        raise SnapshotError(f"associated-data object {uuid} has properties that are not an object")
    recorded = sorted(
        anchor_uuid
        for anchor_uuid, data_uuids in index.items()
        if isinstance(data_uuids, list) and uuid in data_uuids
    )
    grounded = tuple(each for each in recorded if each not in retired)
    for anchor_uuid in recorded:
        if anchor_uuid not in retired:
            continue
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.OMITTED,
                summary=(
                    f"associated-data object {uuid} was grounded by the anchor {anchor_uuid} "
                    "in v1, which is not live and does not become memory, so that grounding "
                    "is left out with it"
                ),
            )
        )
    try:
        return AssociatedDataObject(
            uuid=uuid,
            type_key=type_key,
            anchor_uuids=grounded,
            properties=dict(properties),
            system_metadata=_metadata(entry),
        )
    except JsonValueError as error:
        raise SnapshotError(
            f"associated-data object {uuid} holds a value that cannot be stored: {error}"
        ) from error


def _recovered_link(
    entry: Mapping[str, JsonValue],
    findings: list[RecoveryFinding],  # noqa: ARG001 - read the same way as its siblings
) -> Link:
    uuid = _text(entry, "uuid", where="a link")
    return Link(
        uuid=uuid,
        type_key=_text(entry, "type", where=f"link {uuid}"),
        source_uuid=_text(entry, "source_uuid", where=f"link {uuid}"),
        target_uuid=_text(entry, "target_uuid", where=f"link {uuid}"),
        system_metadata=_metadata(entry),
    )


# --- Vocabulary ---------------------------------------------------------------------


@dataclass
class _Translation:
    """The vocabulary being built, and the anchors each data type may be grounded by."""

    anchors: list[AnchorTypeDefinition] = field(default_factory=list)
    data_types: dict[str, AssociatedDataTypeDefinition] = field(default_factory=dict)
    links: list[LinkTypeDefinition] = field(default_factory=list)
    constraints: list[RelationshipConstraint] = field(default_factory=list)
    # The most any rule about one thing asked for, split by whether v1's own join could
    # reach a count of none. A floor v1 reached only where a group formed is not settled
    # until every rule about that thing is in: another may require a group to always form,
    # and then the floor was in force after all.
    limited_floors: dict[tuple[object, ...], int] = field(default_factory=dict)
    # The rules v1 always reached that require at least one of what they count. One of
    # these is what can make a join-limited floor have been in force after all.
    guarantees: list[RelationshipConstraint] = field(default_factory=list)
    # What each rule would be reported as having carried whole, held until the vocabulary
    # settles. A rule that counts a type this vocabulary leaves out goes with it, and a
    # claim that it arrived would be untrue of the candidate the owner confirms.
    carried_whole: dict[tuple[object, ...], list[str]] = field(default_factory=dict)
    permitted_anchors: dict[str, list[str]] = field(default_factory=dict)


def _read_definitions(
    section: Mapping[str, JsonValue],
    graph: Graph,
    translation: _Translation,
    findings: list[RecoveryFinding],
) -> None:
    """Read the live v1 vocabulary into a translation, saying what each reading cost."""
    definitions = _entries(section, "definitions")
    live = _live(definitions, "definition", findings)
    for entry in live:
        try:
            _translate_definition(entry, graph, translation, findings)
        except SnapshotError as unreadable:
            # One definition this cannot read does not stop the analysis. An owner is owed
            # the whole account of their snapshot, and a refusal they can act on needs the
            # rest of it as much as this.
            findings.append(
                RecoveryFinding(
                    disposition=RecoveryDisposition.BLOCKING,
                    summary=f"a v1 definition cannot be read: {unreadable}",
                )
            )


def _translated_vocabulary(
    translation: _Translation, graph: Graph, findings: list[RecoveryFinding]
) -> GraphDefinitionSet:
    """Settle the vocabulary, leaving out what nothing in it can reach."""
    data_types: list[AssociatedDataTypeDefinition] = []
    for each in translation.data_types.values():
        declared = set(translation.permitted_anchors.get(each.type_key, []))
        grounding = _grounding_types(graph, each.type_key)
        if grounding - declared:
            findings.append(
                RecoveryFinding(
                    disposition=RecoveryDisposition.SIMPLIFIED,
                    summary=(
                        f"v1 let {each.type_key} facts be grounded by any anchor, and "
                        + ", ".join(sorted(grounding - declared))
                        + " ground some of the imported ones; v2 says which anchor types "
                        "may, so those are named alongside the ones v1 declared"
                    ),
                )
            )
        permitted = tuple(sorted(declared | grounding))
        if not permitted:
            used = any(stored.type_key == each.type_key for stored in graph.associated_data)
            findings.append(
                RecoveryFinding(
                    disposition=(
                        RecoveryDisposition.BLOCKING if used else RecoveryDisposition.OMITTED
                    ),
                    summary=(
                        f"no anchor type carries the v1 type {each.type_key}, so nothing in "
                        "this vocabulary can reach it"
                        + (
                            ", and imported objects of that type have no way to be grounded"
                            if used
                            else " and it is left out"
                        )
                    ),
                )
            )
            continue
        data_types.append(
            AssociatedDataTypeDefinition(
                type_key=each.type_key,
                permitted_anchor_type_keys=permitted,
                property_constraints=each.property_constraints,
                description=each.description,
            )
        )

    # What this vocabulary describes, kind by kind. A v1 system may retire a type and leave
    # the definitions that mention it, so what is left of them has to be settled against
    # what is actually here rather than against what v1 once had — and against the kind of
    # thing each name is used as, since v1 accepted names nothing of that kind ever had.
    anchor_keys = {each.type_key for each in translation.anchors}
    data_keys = {each.type_key for each in data_types}
    # Only these can be at the end of a link: v1 refused a link as an endpoint too.
    endpoints = anchor_keys | data_keys
    for type_key in sorted(set(translation.permitted_anchors) - set(translation.data_types)):
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.OMITTED,
                summary=(
                    f"anchor types name {type_key} as facts they may carry, but no live v1 "
                    "definition describes it, so that permission is left out"
                ),
            )
        )
    links: list[LinkTypeDefinition] = []
    left_out: set[str] = set()
    for each in translation.links:
        narrowed = _joins_described(each, endpoints, findings)
        if narrowed is not None:
            links.append(narrowed)
            continue
        left_out.add(each.type_key)
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.OMITTED,
                summary=(
                    f"the v1 link type {each.type_key} may join nothing this vocabulary "
                    "describes, so nothing could be at either end of one and it is left out"
                ),
            )
        )
    link_keys = {each.type_key for each in links}
    kept_counts = [
        each
        for each in translation.constraints
        if _counts_only(each, anchor_keys, data_keys, endpoints, link_keys)
    ]
    for dropped_count in translation.constraints:
        if dropped_count in kept_counts:
            continue
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.OMITTED,
                summary=(
                    f"the v1 rule counting {_counted_phrase(dropped_count)} counts a type "
                    "this vocabulary left out, so it is left out with it"
                ),
            )
        )
    return GraphDefinitionSet(
        anchor_types=tuple(translation.anchors),
        associated_data_types=tuple(data_types),
        link_types=tuple(links),
        relationship_constraints=_settled_counts(kept_counts, translation, findings),
    )


def _grounding_types(graph: Graph, type_key: str) -> set[str]:
    """Return the anchor types that ground imported objects of one associated-data type.

    v1's required and optional lists say which facts an anchor must or may have; nothing
    there decided which anchors could ground a fact group, and v1 enforced no such rule.
    v2 does, so the rule has to come from somewhere: what the owner's own graph does.
    """
    anchors = {each.uuid: each.type_key for each in graph.anchors}
    return {
        anchors[uuid]
        for stored in graph.associated_data
        if stored.type_key == type_key
        for uuid in stored.anchor_uuids
        if uuid in anchors
    }


def _joins_described(
    link: LinkTypeDefinition, endpoints: set[str], findings: list[RecoveryFinding]
) -> LinkTypeDefinition | None:
    """Return the link type with only the ends this vocabulary describes, or nothing.

    A v1 system retires a type by making it non-live and leaves the definitions naming it.
    Nothing retired can be at the end of a live link, so dropping that name loses no
    meaning — but dropping the whole link type would lose the links that do use it.
    """
    ends = link.endpoint_constraint
    sources = tuple(each for each in ends.permitted_source_type_keys if each in endpoints)
    targets = tuple(each for each in ends.permitted_target_type_keys if each in endpoints)
    if not sources or not targets:
        return None
    if len(sources) == len(ends.permitted_source_type_keys) and len(targets) == len(
        ends.permitted_target_type_keys
    ):
        return link
    findings.append(
        RecoveryFinding(
            disposition=RecoveryDisposition.SIMPLIFIED,
            summary=(
                f"the v1 link type {link.type_key} named types no live v1 definition "
                "describes among its ends; nothing retired can be at the end of a live link, "
                "so those names are left out and the rest of the type is kept"
            ),
        )
    )
    return replace(
        link,
        endpoint_constraint=replace(
            ends, permitted_source_type_keys=sources, permitted_target_type_keys=targets
        ),
    )


def _counts_only(
    constraint: RelationshipConstraint,
    anchor_keys: set[str],
    data_keys: set[str],
    endpoints: set[str],
    link_keys: set[str],
) -> bool:
    """Say whether a rule counts things this vocabulary describes, each as what it is.

    A v1 query could name any type key anywhere, and one naming something of the wrong kind
    counted nothing there. Kept here it would be a rule about something that cannot exist.
    """
    if isinstance(constraint, DirectAssociationMultiplicityConstraint):
        return (
            set(constraint.anchor_type_keys) <= anchor_keys
            and set(constraint.associated_data_type_keys) <= data_keys
        )
    return (
        constraint.link_type_key in link_keys
        and set(constraint.constrained_endpoint_type_keys) <= endpoints
        and set(constraint.opposite_endpoint_type_keys) <= endpoints
    )


def _bounds(constraint: RelationshipConstraint) -> str:
    """Say a rule's range the way v1 wrote it, with a star for no ceiling."""
    ceiling = "*" if constraint.upper_bound is None else constraint.upper_bound
    return f"{constraint.lower_bound}..{ceiling}"


def _both(held: RelationshipConstraint, arriving: RelationshipConstraint) -> RelationshipConstraint:
    """Return the one rule that says everything two rules about the same thing said.

    Not whichever of them says more — that would drop what the other said. Two rules are
    both in force in v1, so the rule that means the same here is the narrowest one they
    jointly allow.
    """
    uppers = [each for each in (held.upper_bound, arriving.upper_bound) if each is not None]
    return replace(
        held,
        lower_bound=max(held.lower_bound, arriving.lower_bound),
        upper_bound=min(uppers) if uppers else None,
        description=held.description or arriving.description,
    )


def _always_forms(
    constraint: RelationshipConstraint, guarantees: Sequence[RelationshipConstraint]
) -> bool:
    """Say whether v1 required at least one of what this counts, of every one that has it.

    A count v1 could only reach where a group had formed still said what it said of every
    one of them when nothing could have none. That is not a question about this rule alone:
    a v1 rule counting Person and Robot together is universal when Person and Robot each
    require the thing counted, whichever rules happened to say so.
    """
    if isinstance(constraint, DirectAssociationMultiplicityConstraint):
        counted = frozenset(constraint.associated_data_type_keys)
        return all(
            any(
                anchor in each.anchor_type_keys
                and frozenset(each.associated_data_type_keys) == counted
                for each in guarantees
                if isinstance(each, DirectAssociationMultiplicityConstraint)
            )
            for anchor in constraint.anchor_type_keys
        )
    opposite = frozenset(constraint.opposite_endpoint_type_keys)
    return all(
        any(
            endpoint in each.constrained_endpoint_type_keys
            and each.link_type_key == constraint.link_type_key
            and each.constrained_end is constraint.constrained_end
            and frozenset(each.opposite_endpoint_type_keys) == opposite
            for each in guarantees
            if isinstance(each, LinkMultiplicityConstraint)
        )
        for endpoint in constraint.constrained_endpoint_type_keys
    )


def _settled_counts(
    constraints: Sequence[RelationshipConstraint],
    translation: _Translation,
    findings: list[RecoveryFinding],
) -> tuple[RelationshipConstraint, ...]:
    """Leave one rule per thing counted, saying everything the rules about it said.

    v1 says requiredness on the anchor and may also carry a cardinality rule about the
    same association. Both are in force there, and v2 states one rule per association, so
    the one that means the same is the narrowest range they jointly allow.
    """
    settled: dict[tuple[object, ...], RelationshipConstraint] = {}
    for constraint in constraints:
        identity = relationship_identity(constraint)
        held = settled.get(identity)
        if held is None:
            settled[identity] = constraint
            continue
        merged = _both(held, constraint)
        settled[identity] = merged
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.SIMPLIFIED,
                summary=(
                    f"two v1 rules count the same thing ({relationship_label(constraint)}); "
                    f"they are one rule here, bounded {_bounds(merged)}, which is what both "
                    f"of them said ({_bounds(held)} and {_bounds(constraint)})"
                ),
            )
        )
    lowered: set[tuple[object, ...]] = set()
    for identity, floor in translation.limited_floors.items():
        held = settled.get(identity)
        if held is None or floor == 0:
            continue
        if _always_forms(held, translation.guarantees):
            # Other rules require at least one of these of every one of those, so the count
            # v1 took never had an empty group to miss and its floor was in force after all.
            continue
        lowered.add(identity)
        settled[identity] = replace(held, lower_bound=0)
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.SIMPLIFIED,
                summary=(
                    f"the v1 rule counting {_counted_phrase(held)} asked for at least "
                    f"{floor} only of those that had any, which v2 cannot say of some and "
                    "not others; the ceiling is kept and the floor is not"
                ),
            )
        )
    for identity, held in list(settled.items()):
        if held.upper_bound is None or held.lower_bound <= held.upper_bound:
            continue
        # Two v1 rules that nothing can satisfy at once. v1 held both and only refused a
        # system that had one of these to refuse; v2 says one rule per thing counted, and
        # there is no one rule here. Saying either of them would be choosing for the owner.
        del settled[identity]
        lowered.add(identity)
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.BLOCKING,
                summary=(
                    f"v1 rules counting {_counted_phrase(held)} cannot all be met: one asks "
                    f"for at least {held.lower_bound} and another for at most "
                    f"{held.upper_bound}, so there is no one rule here that says what they "
                    "said"
                ),
            )
        )
    for identity in settled:
        if identity in lowered:
            # Its floor was left behind, and the finding above says so. Saying here that it
            # arrived as it stands would say the opposite in the same report.
            continue
        findings.extend(
            RecoveryFinding(disposition=RecoveryDisposition.PRESERVED, summary=summary)
            for summary in translation.carried_whole.get(identity, ())
        )
    return tuple(_counted_description(each, findings) for each in settled.values())


def _counted_description(
    constraint: RelationshipConstraint, findings: list[RecoveryFinding]
) -> RelationshipConstraint:
    """Write the words v2 requires for a count, where no v1 rule about it had any."""
    if constraint.description:
        return constraint
    counted = _counted_phrase(constraint)
    return replace(
        constraint,
        description=_described(
            None,
            f"how many {counted}, as v1 said",
            where=f"the rule counting {counted}",
            findings=findings,
        ),
    )


def _counted_phrase(constraint: RelationshipConstraint) -> str:
    """Say what a rule counts, in the owner's own type keys rather than in v2's terms."""
    if isinstance(constraint, DirectAssociationMultiplicityConstraint):
        carried = ", ".join(constraint.associated_data_type_keys)
        carrying = ", ".join(constraint.anchor_type_keys)
        return f"{carried} facts a {carrying} carries"
    ends = ", ".join(constraint.constrained_endpoint_type_keys)
    return f"{constraint.link_type_key} links a {ends} is the {constraint.constrained_end.value} of"


def _translate_definition(
    entry: Mapping[str, JsonValue],
    graph: Graph,
    translation: _Translation,
    findings: list[RecoveryFinding],
) -> None:
    type_key = _text(entry, "type_key", where="a definition")
    kind = _text(entry, "kind", where=f"definition {type_key}")
    where = f"the v1 type {type_key}"
    payload = entry.get("payload", {})
    if not isinstance(payload, dict):
        raise SnapshotError(f"definition {type_key} has a payload that is not an object")

    if kind == "anchor":
        if _already_described(type_key, translation, findings):
            return
        _report_uncarried(where, payload, {"required_data_types", "optional_data_types"}, findings)
        translation.anchors.append(
            AnchorTypeDefinition(type_key=type_key, description=_type_description(entry, findings))
        )
        _translate_anchor_payload(type_key, payload, translation, findings)
        return
    if kind == "data_object":
        if _already_described(type_key, translation, findings):
            return
        _report_uncarried(where, payload, {"properties"}, findings)
        translation.data_types[type_key] = AssociatedDataTypeDefinition(
            type_key=type_key,
            property_constraints=_translated_properties(type_key, payload, graph, findings),
            description=_type_description(entry, findings),
        )
        translation.permitted_anchors.setdefault(type_key, [])
        return
    if kind == "link":
        if _already_described(type_key, translation, findings):
            return
        _report_uncarried(
            where, payload, {"allowed_source_types", "allowed_target_types"}, findings
        )
        translation.links.append(
            LinkTypeDefinition(
                type_key=type_key,
                endpoint_constraint=EndpointConstraint(
                    permitted_source_type_keys=_type_keys(payload, "allowed_source_types"),
                    permitted_target_type_keys=_type_keys(payload, "allowed_target_types"),
                    description=_described(
                        None,
                        f"which types a {type_key} link may join, as v1 allowed",
                        where=f"the endpoints of {type_key}",
                        findings=findings,
                    ),
                ),
                description=_type_description(entry, findings),
            )
        )
        return
    raise SnapshotError(f"definition {type_key} has an unknown kind {kind!r}")


def _described(
    stored: JsonValue,
    written: str,
    *,
    where: str,
    findings: list[RecoveryFinding],
) -> str:
    """Keep the owner's own words, or write the ones v2 requires and say that they were.

    A description is how a rule reads to its owner, not what it permits, so writing one
    where v1 had none adds nothing to the vocabulary. Replacing one the owner wrote would
    be the opposite, which is why the stored text wins whenever there is any.
    """
    if isinstance(stored, str) and stored:
        return stored
    findings.append(
        RecoveryFinding(
            disposition=RecoveryDisposition.SIMPLIFIED,
            summary=(f"{where} had no readable description in v1 and is described as {written!r}"),
        )
    )
    return written


def _type_description(entry: Mapping[str, JsonValue], findings: list[RecoveryFinding]) -> str:
    type_key = entry.get("type_key")
    return _described(
        entry.get("description"),
        f"a {type_key}, recovered from Vellis v1",
        where=f"the v1 type {type_key}",
        findings=findings,
    )


def _report_uncarried(
    where: str,
    payload: Mapping[str, JsonValue],
    carried: set[str],
    findings: list[RecoveryFinding],
) -> None:
    """Name everything a v1 payload said that this does not carry across."""
    for uncarried in sorted(set(payload) - carried):
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.SIMPLIFIED,
                summary=(
                    f"{where} had a v1 {uncarried} rule, which this cannot say and will not "
                    "approximate"
                ),
            )
        )


def _already_described(
    type_key: str, translation: _Translation, findings: list[RecoveryFinding]
) -> bool:
    """Say whether this type key has already been described, and report it if it has.

    v1 refuses two live definitions for one type key itself, so a snapshot holding both
    has been edited since. Picking one would decide which of the owner's rules to keep,
    which is not a decision this gets to make.
    """
    described = (
        any(each.type_key == type_key for each in translation.anchors)
        or type_key in translation.data_types
        or any(each.type_key == type_key for each in translation.links)
    )
    if described:
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.BLOCKING,
                summary=f"two live v1 definitions describe {type_key}; one type is described once",
            )
        )
    return described


def _type_keys(payload: Mapping[str, JsonValue], name: str) -> tuple[str, ...]:
    """Return the types a v1 list names, each once.

    A list of type keys names a set. Saying one twice names the same set, and refusing an
    otherwise compatible system over a redundant entry would be refusing meaning that came
    across intact.
    """
    values = payload.get(name, [])
    if not isinstance(values, list):
        raise SnapshotError(f"a definition's {name} is not a list")
    named: list[str] = []
    for each in values:
        if not isinstance(each, str):
            raise SnapshotError(f"a definition's {name} names something that is not a type")
        if each not in named:
            named.append(each)
    return tuple(named)


def _translate_anchor_payload(
    type_key: str,
    payload: Mapping[str, JsonValue],
    translation: _Translation,
    findings: list[RecoveryFinding],
) -> None:
    """Carry which data types may ground this anchor, and which it must have.

    v1 says requiredness on the anchor; v2 says which anchors a data type permits, plus a
    multiplicity rule when one is required. Same meaning, said from the other end.
    """
    for name in ("required_data_types", "optional_data_types"):
        for data_type in dict.fromkeys(_type_keys(payload, name)):
            translation.permitted_anchors.setdefault(data_type, []).append(type_key)
        if name == "optional_data_types":
            continue
        for data_type in dict.fromkeys(_type_keys(payload, name)):
            translation.constraints.append(
                _counting(
                    DirectAssociationMultiplicityConstraint(
                        constrained_end=DirectAssociationEnd.ANCHOR,
                        anchor_type_keys=(type_key,),
                        associated_data_type_keys=(data_type,),
                        lower_bound=1,
                        # Left unwritten until every rule about this association is in
                        # hand: if the owner wrote one of them, their words are the ones
                        # to keep.
                        description=None,
                    ),
                    # v1 requires this of every anchor of the type, not only of those that
                    # already have some, so nothing about a join keeps it from reaching.
                    False,
                    translation,
                )
            )
            _carried_whole(
                translation.constraints[-1],
                (
                    f"{type_key} requires {data_type}, carried across as a multiplicity "
                    "rule on the association"
                ),
                translation,
            )


def _translated_properties(
    type_key: str,
    payload: Mapping[str, JsonValue],
    graph: Graph,
    findings: list[RecoveryFinding],
) -> tuple[PropertyConstraint, ...]:
    fields = payload.get("properties", {})
    if not isinstance(fields, dict):
        raise SnapshotError(f"definition {type_key} has properties that are not an object")
    constraints: list[PropertyConstraint] = []
    for name, rule in sorted(fields.items()):
        if not isinstance(rule, dict):
            raise SnapshotError(
                f"definition {type_key} has a rule for {name} that is not an object"
            )
        try:
            constraint = _translated_property(type_key, name, rule, graph, findings)
        except SnapshotError as unreadable:
            # One rule this cannot read is a reason the import cannot happen, not a reason
            # to stop reading the type it belongs to.
            findings.append(
                RecoveryFinding(
                    disposition=RecoveryDisposition.BLOCKING,
                    summary=f"{type_key}.{name} cannot be read: {unreadable}",
                )
            )
            continue
        if constraint is not None:
            constraints.append(constraint)
    return tuple(constraints)


def _translated_property(
    type_key: str,
    name: str,
    rule: Mapping[str, JsonValue],
    graph: Graph,
    findings: list[RecoveryFinding],
) -> PropertyConstraint | None:
    where = f"{type_key}.{name}"
    kind = _single_kind(where, rule, graph, type_key, name, findings)
    if kind is None:
        return None
    for unsupported in sorted(set(rule) - _CARRIED_FIELD_KEYS):
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.SIMPLIFIED,
                summary=(
                    f"{where} had a v1 {unsupported} rule, which this cannot say and will "
                    "not approximate"
                ),
            )
        )
    required = rule.get("required")
    if not isinstance(required, bool):
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.BLOCKING,
                summary=(
                    f"{where} does not say whether it is required; a rule this cannot read "
                    "is not one to guess at"
                ),
            )
        )
        return None
    description = _described(
        rule.get("description"),
        f"the {name} of a {type_key}, recovered from Vellis v1",
        where=where,
        findings=findings,
    )
    try:
        pattern = _translated_pattern(where, rule, kind, findings)
        return PropertyConstraint(
            property_name=name,
            required=required,
            json_kind=kind,
            description=description,
            value_range=_matchable(
                _translated_range(where, rule, kind, findings), pattern, where, findings
            ),
            pattern=pattern,
        )
    except (SnapshotError, JsonValueError) as error:
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.BLOCKING,
                summary=f"{where} cannot be carried across: {error}",
            )
        )
        return None


def _single_kind(
    where: str,
    rule: Mapping[str, JsonValue],
    graph: Graph,
    type_key: str,
    name: str,
    findings: list[RecoveryFinding],
) -> JsonKind | None:
    """Decide the one JSON kind this property holds, or say why it cannot be kept.

    A v2 property is of one kind. Where a v1 rule already means one, that is the answer.
    Where it means several, the values the owner actually stored decide: one kind among
    them narrows the rule to what their memory says, several is a property this cannot
    represent at all, and none means nothing depends on the rule and it can be left out.
    """
    declared = rule.get("value_kinds", [])
    if not isinstance(declared, list) or not declared:
        raise SnapshotError(f"{where} does not say what kind of value it holds")
    kinds: list[JsonKind] = []
    for each in declared:
        if not isinstance(each, str) or each not in _VALUE_KINDS:
            raise SnapshotError(f"{where} names an unknown v1 value kind {each!r}")
        if _VALUE_KINDS[each] not in kinds:
            kinds.append(_VALUE_KINDS[each])
    if len(kinds) == 1:
        _report_lost_refinements(where, declared, kinds[0], findings)
        return kinds[0]
    stored = _stored_kinds(graph, type_key, name)
    if stored - set(kinds):
        # v1 refused what these objects hold, so what they hold cannot be what the rule
        # meant. Reading a rule off them would state one the owner never wrote.
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.BLOCKING,
                summary=(
                    f"{where} allowed several value kinds, none of them "
                    + ", ".join(sorted(each.value for each in stored - set(kinds)))
                    + ", which imported objects hold; a rule cannot be read off values v1 "
                    "itself would not have allowed"
                ),
            )
        )
        return None
    if len(stored) == 1:
        settled = next(iter(stored))
        _report_lost_refinements(where, declared, settled, findings)
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.SIMPLIFIED,
                summary=(
                    f"{where} allowed {len(kinds)} value kinds in v1 and is narrowed to "
                    f"{settled.value}, which is what every imported value is"
                ),
            )
        )
        return settled
    if not stored:
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.OMITTED,
                summary=(
                    f"{where} allowed several value kinds and no imported object uses it, "
                    "so the rule is left out rather than narrowed by guesswork"
                ),
            )
        )
        return None
    findings.append(
        RecoveryFinding(
            disposition=RecoveryDisposition.BLOCKING,
            summary=(
                f"{where} allowed several value kinds and imported objects use "
                + ", ".join(sorted(each.value for each in stored))
                + "; one property holds one kind"
            ),
        )
    )
    return None


# v1 kinds that say more than the v2 kind they land on. Both are removed refinements: v2
# has one number and one string, and approximating "whole" or "a UUID" as a bound or a
# pattern would put a rule in the owner's vocabulary that they never wrote.
_NARROWER_KINDS = {
    "integer": "only whole numbers",
    "uuid": "only text shaped like a UUID",
}


def _report_lost_refinements(
    where: str, declared: Sequence[JsonValue], settled: JsonKind, findings: list[RecoveryFinding]
) -> None:
    """Name each v1 kind that said more than the v2 kind the rule settled on."""
    wider = {
        each
        for each in declared
        if isinstance(each, str) and each in _VALUE_KINDS and each not in _NARROWER_KINDS
    }
    if any(_VALUE_KINDS[each] is settled for each in wider):
        # The same rule already permitted everything the settled kind holds, so the
        # narrower way of saying it alongside took nothing away.
        return
    for each in declared:
        if not isinstance(each, str) or each not in _NARROWER_KINDS:
            continue
        if _VALUE_KINDS[each] is not settled:
            continue
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.SIMPLIFIED,
                summary=(
                    f"{where} was a v1 {each}, which permitted {_NARROWER_KINDS[each]}; "
                    f"this holds {settled.value} and will not invent a rule for the rest"
                ),
            )
        )


def _stored_kinds(graph: Graph, type_key: str, name: str) -> set[JsonKind]:
    return {
        json_kind(each.properties[name])
        for each in graph.associated_data
        if each.type_key == type_key and name in each.properties
    }


def _translated_range(
    where: str,
    rule: Mapping[str, JsonValue],
    kind: JsonKind,
    findings: list[RecoveryFinding],
) -> ValueRange | None:
    lower = rule.get("minimum")
    upper = rule.get("maximum")
    permitted = rule.get("allowed_values", [])
    if not isinstance(permitted, list):
        raise SnapshotError(f"{where} has allowed_values that are not a list")
    bounds = [each for each in (lower, upper) if each is not None]
    if bounds and kind is not JsonKind.NUMBER:
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.SIMPLIFIED,
                summary=(
                    f"{where} carried numeric bounds on a {kind.value}, which say nothing "
                    "about the values it holds"
                ),
            )
        )
        lower = upper = None
    kept: list[JsonValue] = []
    for value in permitted:
        if json_kind(normalize(value)) is kind:
            if not any(json_equal(normalize(value), normalize(each)) for each in kept):
                kept.append(value)
            continue
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.SIMPLIFIED,
                summary=(
                    f"{where} permitted the value {value!r} in v1, which a {kind.value} "
                    "cannot hold, so it is no longer one of the values allowed here"
                ),
            )
        )
    if lower is None and upper is None and not kept:
        return None
    return ValueRange(
        lower_bound=None if lower is None else _number(lower, where),
        upper_bound=None if upper is None else _number(upper, where),
        permitted_values=tuple(kept),
    )


def _matchable(
    permitted: ValueRange | None,
    pattern: StringPattern | None,
    where: str,
    findings: list[RecoveryFinding],
) -> ValueRange | None:
    """Leave out permitted values the same v1 rule's pattern would never have matched.

    v1 required both, so a permitted value its pattern rejects was one no v1 object could
    ever hold. Carrying it across says the property allows what it also forbids, which is
    not something to hold a recovered system to.
    """
    if permitted is None or pattern is None or not permitted.permitted_values:
        return permitted
    matches = compile_pattern(pattern.expression).matches
    kept = tuple(
        each for each in permitted.permitted_values if isinstance(each, str) and matches(each)
    )
    if len(kept) == len(permitted.permitted_values):
        return permitted
    for each in permitted.permitted_values:
        if each in kept:
            continue
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.SIMPLIFIED,
                summary=(
                    f"{where} permitted the value {each!r} in v1 and required its pattern "
                    "too, so nothing could ever be that; it is no longer one of the values "
                    "allowed here"
                ),
            )
        )
    if kept:
        return replace(permitted, permitted_values=kept)
    if permitted.lower_bound is None and permitted.upper_bound is None:
        return None
    return replace(permitted, permitted_values=())


def _number(value: JsonValue, where: str) -> Decimal:
    normalized = normalize(value)
    if not isinstance(normalized, Decimal):
        raise SnapshotError(f"{where} has a bound that is not a number")
    return normalized


def _translated_pattern(
    where: str,
    rule: Mapping[str, JsonValue],
    kind: JsonKind,
    findings: list[RecoveryFinding],
) -> StringPattern | None:
    expression = rule.get("pattern")
    if expression is None:
        return None
    if not isinstance(expression, str):
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.SIMPLIFIED,
                summary=f"{where} carried a pattern that is not text, which matches nothing",
            )
        )
        return None
    if kind is not JsonKind.STRING:
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.SIMPLIFIED,
                summary=f"{where} carried a pattern on a {kind.value}, which no value can match",
            )
        )
        return None
    # v1 asked whether the expression appeared anywhere in the value; v2 asks whether it
    # describes the whole of it. Said plainly in v2's terms, "appears anywhere" is the
    # expression with anything permitted either side — which leaves an anchored v1
    # expression anchored, because nothing can precede the start of the text. The
    # dot-matches-newline flag is scoped to the parts this added, so the owner's own
    # expression still means there what it meant in v1.
    anywhere = f"(?s:.*)(?:{expression})(?s:.*)"
    try:
        compile_pattern(anywhere)
    except PatternError as error:
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.SIMPLIFIED,
                summary=f"{where} carried a pattern this cannot evaluate: {error}",
            )
        )
        return None
    return StringPattern(expression=anywhere)


# --- What is left out, and what is left ---------------------------------------------


def _report_untranslatable_sections(
    content: Mapping[str, JsonValue],
    translation: _Translation,
    findings: list[RecoveryFinding],
) -> None:
    """Carry what the constraints section says that v2 can say, and name the rest."""
    for entry in _live(
        _entries(_section(content, "constraints"), "constraints"), "constraint", findings
    ):
        _translate_constraint(entry, translation, findings)
    migrations = _entries(_section(content, "migration"), "migrations")
    if migrations:
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.OMITTED,
                summary=(
                    f"{_counted(len(migrations), 'v1 migration record')} describe how that "
                    "system changed and are not memory; they are left out"
                ),
            )
        )
    carried_over = [
        name
        for name in ("last_ledger_position", "last_transaction_id", "last_transaction_timestamp")
        if content.get(name) is not None
    ]
    if carried_over:
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.OMITTED,
                summary=(
                    "the v1 ledger position and transaction metadata are left out; this is a "
                    "new lineage and claims none of that history"
                ),
            )
        )


def _translate_constraint(
    entry: Mapping[str, JsonValue],
    translation: _Translation,
    findings: list[RecoveryFinding],
) -> None:
    """Carry one v1 constraint if v2 can say it, and say why when it cannot.

    v1 states a constraint over a query; v2 states one over types. Where the query is
    simply "these types, joined this way" the two say the same thing and the rule comes
    across with its own counts. Where the query says more than that, there is no rule of
    v2's that means it, and inventing a looser one would be worse than saying so.
    """
    kind = entry.get("kind")
    named = entry.get("display_name") or entry.get("uuid")
    if kind == "query_pattern":
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.OMITTED,
                summary=(
                    f"the v1 query-pattern constraint {named} is a rule about what a query "
                    "must find, which is not something v2 says; it is left out rather than "
                    "approximated"
                ),
            )
        )
        return
    if kind != "cardinality":
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.OMITTED,
                summary=(
                    f"the v1 constraint {named} is of kind {kind!r}, which this does not "
                    "recognise, so there is nothing to translate and it is left out"
                ),
            )
        )
        return
    before = len(findings)
    try:
        carried = _translated_cardinality(entry, translation, findings)
    except SnapshotError as unreadable:
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.BLOCKING,
                summary=f"the v1 constraint {named} cannot be read: {unreadable}",
            )
        )
        return
    if carried is None:
        if len(findings) > before:
            # Already said, in the words of the reason it could not come across.
            return
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.OMITTED,
                summary=(
                    f"the v1 cardinality constraint {named} counts what a query selected "
                    "rather than what a type is, and v2 counts by type; it is left out "
                    "rather than approximated"
                ),
            )
        )
        return
    translation.constraints.append(carried)
    if len(findings) == before:
        _carried_whole(
            carried,
            f"the v1 cardinality constraint {named} is carried across as it stands",
            translation,
        )


def _named(entry: Mapping[str, JsonValue]) -> str:
    """Return the name a part of a v1 query goes by.

    Every part of a query spec is named, because the count and the grouping refer to those
    names. One that is not named is a query this cannot follow, and following it wrongly
    would mean carrying a rule that binds more than the owner's did.
    """
    name = entry.get("name")
    if not isinstance(name, str) or not name:
        raise SnapshotError("a part of a v1 query has no name")
    return name


def _bucket_types(entry: Mapping[str, JsonValue]) -> tuple[str, ...]:
    values = entry.get("anchor_type_keys", [])
    if not isinstance(values, list):
        raise SnapshotError("a v1 query names anchor types that are not a list")
    named: list[str] = []
    for each in values:
        if not isinstance(each, str):
            raise SnapshotError("a v1 query names an anchor type that is not a type")
        if each not in named:
            named.append(each)
    return tuple(named)


def _carried_whole(
    constraint: RelationshipConstraint, summary: str, translation: _Translation
) -> None:
    """Hold what would be said of a rule that arrived whole until the vocabulary settles."""
    translation.carried_whole.setdefault(relationship_identity(constraint), []).append(summary)


def _counting(
    constraint: RelationshipConstraint, limited: bool, translation: _Translation
) -> RelationshipConstraint:
    """Carry a count, remembering whether v1's own join could reach a count of none.

    Two v1 rules about one thing are both in force, so what they jointly asked for is the
    most either asked for — on each side of that split separately. Whether the joint floor
    can be said here is settled once every rule about the thing has arrived.
    """
    if limited:
        identity = relationship_identity(constraint)
        floors = translation.limited_floors
        floors[identity] = max(floors.get(identity, 0), constraint.lower_bound)
    elif constraint.lower_bound >= 1:
        translation.guarantees.append(constraint)
    return constraint


def _join_limited(requirement: Mapping[str, JsonValue], *, reaches_empty: bool) -> bool:
    """Say whether v1's own query kept a floor from ever reaching an empty count.

    v1 counts the rows a query returned, and a required part of that query keeps only the
    rows it matched. So a floor over a required part never reached anything that had none
    of what it counted — it said "of those that have any, at least this many". Counting an
    optional link by its target end is the same story: the row v1 keeps for a target with
    no link is the row that no longer names that target, so it forms no group either.
    """
    return not (reaches_empty and requirement.get("required", True) is False)


def _bucket(
    entry: Mapping[str, JsonValue], name: str, buckets: Mapping[str, tuple[str, ...]]
) -> str:
    """Return the name of a set of types a v1 query part refers to.

    A part that refers to a set the query never declares is a query this cannot follow.
    Carrying it anyway would state a rule about no types at all, which is not what the
    owner wrote and is not something to report as preserved.
    """
    referred = entry.get(name)
    if not isinstance(referred, str) or referred not in buckets:
        raise SnapshotError(f"a v1 count refers to {referred!r}, which its query does not name")
    return referred


def _stored_description(entry: Mapping[str, JsonValue]) -> str | None:
    """Return the owner's own words for a v1 constraint, or nothing where they wrote none."""
    described = entry.get("description")
    return described if isinstance(described, str) and described else None


def _whole(value: JsonValue) -> int | None:
    """Return a v1 count as the whole number it is, or nothing when it is not one.

    JSON text arrives as exact decimals rather than machine integers, so a bound read from
    a file is a ``Decimal`` and a bound read from a Python mapping is an ``int``. Both say
    the same thing, and a rule an owner wrote must not depend on which door it came in.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    return None


def _summarized(query: Mapping[str, JsonValue]) -> bool:
    """Say whether a v1 query asked for a summary rather than the rows a count would read."""
    shape = query.get("return_spec")
    if not isinstance(shape, dict):
        return False
    return bool(shape.get("aggregations"))


def _translated_cardinality(
    entry: Mapping[str, JsonValue], translation: _Translation, findings: list[RecoveryFinding]
) -> RelationshipConstraint | None:
    """Return the v2 rule this v1 cardinality constraint means, or nothing.

    Two shapes say something about types rather than about a query: how many facts of one
    type an anchor type carries, and how many links of one type join two endpoint types.
    Anything else — a filtered selection, several joins, a count of something the group is
    not about — means only what the query meant, and v2 has no way to say that.
    """
    payload = entry.get("payload")
    if not isinstance(payload, dict):
        raise SnapshotError("a v1 constraint's payload is not an object")
    query = payload.get("query_spec")
    counted = payload.get("counted_binding")
    grouped = payload.get("group_by_bindings")
    lower, upper = payload.get("minimum"), payload.get("maximum")
    lower_bound = 0 if lower is None else _whole(lower)
    upper_bound = None if upper is None else _whole(upper)
    if lower_bound is None or (upper is not None and upper_bound is None):
        raise SnapshotError("a v1 count is bounded by something that is not a whole number")
    if not isinstance(query, dict):
        raise SnapshotError("a v1 count names a query that is not an object")
    if not isinstance(counted, str) or not counted:
        raise SnapshotError("a v1 count does not say what it counts")
    if not isinstance(grouped, list) or not all(isinstance(each, str) for each in grouped):
        raise SnapshotError("a v1 count does not say what it counts by")
    if _summarized(query):
        # v1 returned a summary instead of the rows, and its count read the rows. So this
        # rule counted nothing there, whatever it says; enforcing it here would be a rule
        # the owner never had rather than the one they wrote.
        named = entry.get("display_name") or entry.get("uuid")
        findings.append(
            RecoveryFinding(
                disposition=RecoveryDisposition.OMITTED,
                summary=(
                    f"the v1 cardinality constraint {named} asks its query for a summary "
                    "rather than for what it counts, so it "
                    "counted nothing in v1 and is left out rather than newly enforced"
                ),
            )
        )
        return None
    buckets = {_named(each): _bucket_types(each) for each in _entries(query, "anchor_buckets")}
    links = {_named(each): each for each in _entries(query, "link_requirements")}
    facts = {_named(each): each for each in _entries(query, "data_requirements")}

    if counted in facts and not links and len(buckets) == 1 and len(facts) == 1:
        fact = facts[counted]
        anchor_bucket = _bucket(fact, "anchor_bucket", buckets)
        data_type = fact.get("data_type_key")
        if not isinstance(data_type, str):
            raise SnapshotError("a v1 count names facts that are not of one type")
        if fact.get("predicates") or grouped != [anchor_bucket]:
            return None
        return _counting(
            DirectAssociationMultiplicityConstraint(
                description=_stored_description(entry),
                constrained_end=DirectAssociationEnd.ANCHOR,
                anchor_type_keys=buckets[anchor_bucket],
                associated_data_type_keys=(data_type,),
                lower_bound=lower_bound,
                upper_bound=upper_bound,
            ),
            _join_limited(fact, reaches_empty=True),
            translation,
        )
    if counted in links and not facts and len(buckets) == 2 and len(links) == 1:
        link = links[counted]
        source = _bucket(link, "source_bucket", buckets)
        target = _bucket(link, "target_bucket", buckets)
        if source == target:
            # One of the two sets the query declared is joined to nothing, so what the
            # query reached depended on that set having members. v2 says nothing of the
            # kind, and would count every link of the type instead.
            return None
        types = link.get("link_type_keys")
        if not isinstance(types, list) or len(types) != 1 or not isinstance(types[0], str):
            return None
        if grouped == [source]:
            end, constrained, opposite = LinkEnd.SOURCE, source, target
        elif grouped == [target]:
            end, constrained, opposite = LinkEnd.TARGET, target, source
        else:
            return None
        return _counting(
            LinkMultiplicityConstraint(
                description=_stored_description(entry),
                link_type_key=types[0],
                constrained_end=end,
                constrained_endpoint_type_keys=buckets[constrained],
                opposite_endpoint_type_keys=buckets[opposite],
                lower_bound=lower_bound,
                upper_bound=upper_bound,
            ),
            _join_limited(link, reaches_empty=end is LinkEnd.SOURCE),
            translation,
        )
    return None


def _preserved_finding(candidate: RecoveryCandidate) -> RecoveryFinding:
    graph = candidate.graph
    return RecoveryFinding(
        disposition=RecoveryDisposition.PRESERVED,
        summary=(
            f"{_counted(len(graph.anchors), 'anchor')}, "
            f"{_counted(len(graph.associated_data), 'associated-data object')}, and "
            f"{_counted(len(graph.links), 'link')} arrive exactly as v1 stored them"
        ),
    )


def _conformance_findings(candidate: RecoveryCandidate) -> tuple[RecoveryFinding, ...]:
    """Ask the questions first use itself would ask, before an owner is asked anything.

    The import is refused as a whole or not at all, so every reason it would be refused
    belongs in the report the owner reads rather than in the failure after they agreed.
    """
    state = CanonicalState(
        graph=candidate.graph,
        active_definitions=candidate.active_definitions,
        revision=0,
        definition_delta=None,
    )
    return tuple(
        RecoveryFinding(
            disposition=RecoveryDisposition.BLOCKING,
            summary=f"the v1 content does not form a system this can hold: {each.summary}",
        )
        for each in state_findings(state)
    )
