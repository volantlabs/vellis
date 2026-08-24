# Vellis v2 simplification baseline

This is Phase 0 evidence for evolution vellis-2-simplification-rebaseline. It records the
pre-change implementation at Git checkpoint
5196bb01fedb90c815ae15f40cddb041fc915d01; it is not product authority or a design document.
Phase 8 compares the successor against the same measurements.

## Size and complexity

| Measure | Baseline |
| --- | ---: |
| Authored SysML lines | 4,750 |
| Product Python lines under vellis/ | 23,854 |
| Test Python lines | 28,692 |
| Product C901 findings above complexity 10 | 37 |
| Repository C901 findings above complexity 10 | 53 |
| Active evolution-validator C901 findings | 4 |
| Persistent application tables | 39 |
| Distinct named temporary relations | 38 |
| Product private FastMCP _mcp_server references | 4 |
| Test files referring to internal connections | 17 |

Product modules above 800 lines were store.py (7,610), streaming.py (1,715),
normalized.py (1,541), v1.py (1,518), system.py (1,439), query.py (1,267),
setup.py (1,100), definitions.py (1,011), v1_streaming.py (916), and mcp.py (871).
CanonicalStore exposed 40 public methods and RTGSystem exposed 18.

The directly visible definition-resolution paths were
normalized.load_definition_set, CanonicalStore._load_definition_set,
CanonicalStore._definition_source_map_unlocked, and
CanonicalStore._definition_selection_context_unlocked.

## Persistent relations

The 39 application tables were:

activity_record, canonical_definition_event, canonical_definition_proposal_event,
canonical_graph_event, canonical_proposal_event, canonical_record,
current_assessment, current_definition_relationship_source,
current_definition_type_source, definition_anchor_permission,
definition_endpoint_permission, definition_endpoint_rule,
definition_multiplicity_participant, definition_multiplicity_rule,
definition_permitted_value, definition_property_rule, definition_set,
definition_set_overlay, definition_set_relationship_override,
definition_set_type_override, definition_type, graph_presence_interval, ledger,
object_anchor, object_metadata, object_property, object_value,
proposal_definition_relationship, proposal_definition_state,
proposal_definition_type, proposal_entry, proposal_overlay_count,
proposal_overlay_state, schema_meta, state_head, validation_assessment,
validation_finding, validation_finding_definition, and validation_finding_object.

## Temporary relations

The 38 distinct named temporary relations were:

assessment_changed_multiplicity_rule, assessment_definition_relationship,
assessment_definition_type, assessment_effective_object,
assessment_materialized_uuid, assessment_structural_relationship,
assessment_structural_type, assessment_endpoint_membership_change,
assessment_validation_uuid, multiplicity_association_seed,
multiplicity_effective_data_anchor, multiplicity_effective_object,
multiplicity_impact_reason, multiplicity_incident_link, multiplicity_link_seed,
multiplicity_lookup_uuid, multiplicity_rule_subject_type,
multiplicity_subject_seed, multiplicity_subject_type_seed,
multiplicity_type_filter, multiplicity_work, normalized_definition_entry,
query_aggregate_sum_term, query_answer, query_selector_member,
recovery_anchor, recovery_association, recovery_object,
recovery_translation_entry, recovery_translation_map_key,
recovery_translation_value, replay_expected, restore_candidate,
restore_current, restore_target, tail_definition_id, tail_object_id, and
tail_object_map.

## Coupling and stale process surface

Seventeen Vellis test/support files referenced internal connection state:
characterization.py, evolution_support.py, oracle.py, test_activity_history.py,
test_current_work.py, test_definition_discovery.py, test_fresh_initialization.py,
test_graph_changes.py, test_graph_queries.py, test_historical_restore.py,
test_historical_selection.py, test_population_local_work.py,
test_query_contract_v2.py, test_semantic_work_locality.py,
test_sqlite_prospective_state.py, test_store_integrity.py, and
test_streaming_lifecycle.py.

The ordinary just check still ran the completed implementation-campaign validator. README,
SECURITY, CONTRIBUTING, and realization/locality documents still described proposal assessments,
snapshot/tail/replay, preserve and serve-mcp, exact old tool inventories, and completed campaign
handoffs. Those are removal/synchronization evidence for Phase 8, not requirements to preserve.

## Portable forward-test disposition

Two fresh context-isolated agents exercised the changed portable evolution schema and pure
invariants without receiving an expected conclusion. Prompts, transcripts, and temporary records
were kept outside the repository.

- Stateless transformation: a CSV-to-JSON command-line tool carried one reproduced escaping defect
  and one reversible internal buffering decision in one active correction item. Schema and pure
  invariants accepted the neutral record; wrong ownership and pending approval on active work were
  rejected. No material finding; clean disposition.
- Interactive stateful workflow: an appointment-booking system kept a double-booking defect ready
  while a cancellation-meaning change and its dependent implementation remained approval-gated.
  Schema and pure invariants accepted that mixed frontier; premature dependency execution, pending
  approval execution, and an inconsistent lifecycle roll-up were rejected. No material finding;
  clean disposition.

Both scenarios used generic authority and baseline identities. They confirmed that Git and Vellis
evidence checks remain project bindings rather than portable record invariants.

## Phase 0 review-convergence audit

After three non-clean review pairs, one bounded audit traced the recurring defect class to evidence
that accidentally depended on ambient repository shape: live-record fixtures, a compatibility alias
instead of the called Git function, a static regex that missed dynamic names, and an approval
projection broader than the gated consequence.

The root-cause sweep found exactly one committed-record read, no positional finding/decision/work
selection, no repository import in the pure invariant module, scoped evolution and work-item
approval projections with positive and negative evidence, 38 mechanically reproduced temporary
relations, and no changed model or product path. Portable validation was added because the schema is
a portable workflow asset. No further Phase 0 obligation was widened.

## Reproduction

Run the measurements against an extracted copy of the exact checkpoint so later working-tree or
tooling changes cannot affect the source population:

~~~sh
baseline_dir=$(mktemp -d)
git archive 5196bb01fedb90c815ae15f40cddb041fc915d01 | tar -x -C "$baseline_dir"
wc -l "$baseline_dir"/model/*.sysml
wc -l "$baseline_dir"/vellis/*.py
wc -l "$baseline_dir"/tests/*.py "$baseline_dir"/tests/vellis/*.py
uv run ruff check "$baseline_dir/vellis" "$baseline_dir/tools" \
  --select C901 --output-format concise
rg '^CREATE (VIRTUAL )?TABLE ' "$baseline_dir/vellis/store.py"
(
  rg -o 'CREATE TEMP(?:ORARY)? TABLE(?: IF NOT EXISTS)? [A-Za-z_][A-Za-z0-9_]*' \
    "$baseline_dir/vellis" -g '*.py' \
    | sed -E 's/.* TABLE( IF NOT EXISTS)? //' \
    | rg -v '^IF$'
  printf '%s\n' assessment_validation_uuid assessment_endpoint_membership_change
) | sort -u
rg -n '_mcp_server' "$baseline_dir/vellis" -g '*.py'
rg -l '(_store\.)?_connection|\.connection\b|check_same_thread' \
  "$baseline_dir/tests/vellis" -g '*.py'
rg -n '^def load_definition_set|^    def _load_definition_set|^    def _definition_source_map_unlocked|^    def _definition_selection_context_unlocked' \
  "$baseline_dir/vellis/normalized.py" "$baseline_dir/vellis/store.py"
uv run python - "$baseline_dir" <<'PY'
import ast
import sys
from pathlib import Path

for path in sorted((Path(sys.argv[1]) / "vellis").glob("*.py")):
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    classes = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        public = sum(
            isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not child.name.startswith("_")
            for child in node.body
        )
        if public:
            classes.append(f"{node.name}:{public}")
    if len(source.splitlines()) > 800 or classes:
        print(path.name, len(source.splitlines()), *classes)
PY
~~~

The line totals are the final total rows from the three wc commands. The C901 total is Ruff's
reported error count (53). Persistent relation names are the unique names from the CREATE TABLE
search. Temporary relation names are unique exact names after removing CREATE TEMP TABLE and IF NOT
EXISTS. The dynamically formatted assessment family adds assessment_validation_uuid and
assessment_endpoint_membership_change. SQLite-owned FTS shadow tables were not present and are not
counted.

Module sizes use wc on each product file. Public-method counts were produced by parsing each product
file with Python's ast module and counting direct FunctionDef or AsyncFunctionDef children of each
top-level class whose name does not begin with an underscore. Stale process terms were located with:

~~~sh
rg -n 'snapshot|tail|replay|assessment|proposal|preserve|serve-mcp|implementation-campaign-check' \
  "$baseline_dir/README.md" "$baseline_dir/CONTRIBUTING.md" \
  "$baseline_dir/SECURITY.md" "$baseline_dir/docs" "$baseline_dir/justfile" \
  "$baseline_dir/pyproject.toml"
~~~
