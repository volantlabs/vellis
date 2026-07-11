from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = ROOT / "model"
COMPONENT_MODEL_ROOT = MODEL_ROOT / "bibliotek" / "components"
GENERATED_DOC_ROOT = ROOT / "docs" / "model" / "generated"
GENERATED_COMPONENT_DOC_ROOT = GENERATED_DOC_ROOT / "components"
GENERATED_MANIFEST = ROOT / "apps" / "rtg_knowledge_graph" / "resources" / "model_app_manifest.json"
IMPLEMENTATION_DRIFT_PATH = MODEL_ROOT / "implementation-drift.yaml"

EXPECTED_VELLIS_ROLES: dict[str, str] = {
    "documentStorage": "component.storage.json_file",
    "ledgerStorage": "component.storage.sql",
    "graphStore": "component.rtg.graph",
    "schemaRegistry": "component.rtg.schema",
    "constraintRegistry": "component.rtg.constraints",
    "migrationStore": "component.rtg.migration",
    "queryEngine": "component.rtg.query",
    "changeValidator": "component.rtg.change_validation",
    "controller": "component.rtg.controller",
}

RUNTIME_ROLE_NAMES: dict[str, str] = {
    "documentStorage": "document_storage",
    "ledgerStorage": "controller_ledger_storage",
    "graphStore": "graph_store",
    "schemaRegistry": "schema_registry",
    "constraintRegistry": "constraint_registry",
    "migrationStore": "migration_store",
    "queryEngine": "query_engine",
    "changeValidator": "change_validator",
    "controller": "rtg_system_controller",
}

RUNTIME_MANIFEST_ROLE_ORDER = (
    "documentStorage",
    "ledgerStorage",
    "controller",
    "graphStore",
    "schemaRegistry",
    "constraintRegistry",
    "migrationStore",
    "changeValidator",
    "queryEngine",
)


@dataclass(frozen=True)
class Finding:
    path: Path
    message: str
    line: int | None = None

    def render(self) -> str:
        relative = self.path.relative_to(ROOT)
        location = f"{relative}:{self.line}" if self.line else str(relative)
        return f"{location}: {self.message}"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _sysml_files(scope: str) -> list[Path]:
    roots = {
        "foundation": [MODEL_ROOT / "foundation"],
        "bibliotek": [MODEL_ROOT / "foundation", MODEL_ROOT / "bibliotek"],
        "vellis": [MODEL_ROOT / "foundation", MODEL_ROOT / "bibliotek", MODEL_ROOT / "vellis"],
        "all": [MODEL_ROOT],
    }[scope]
    return sorted(path for root in roots for path in root.rglob("*.sysml"))


def _without_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)


def _balanced_delimiters(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    scrubbed = _without_comments(text)
    pairs = {"}": "{", "]": "[", ")": "("}
    stack: list[tuple[str, int]] = []
    in_string = False
    escaped = False
    line = 1
    for char in scrubbed:
        if char == "\n":
            line += 1
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[(":
            stack.append((char, line))
        elif char in "}])":
            if not stack or stack[-1][0] != pairs[char]:
                findings.append(Finding(path, f"unmatched {char}", line))
            else:
                stack.pop()
    for delimiter, delimiter_line in stack:
        findings.append(Finding(path, f"unclosed {delimiter}", delimiter_line))
    return findings


def _component_model_statuses() -> dict[str, str]:
    statuses: dict[str, str] = {}
    for path in sorted(COMPONENT_MODEL_ROOT.glob("component.*.sysml")):
        text = path.read_text(encoding="utf-8")
        match = re.search(
            r"@SpecIdentity\s*\{[^}]*id\s*=\s*\"(component\.[^\"]+)\";"
            r"[^}]*lifecycleStatus\s*=\s*SpecLifecycle::(\w+);",
            text,
            flags=re.DOTALL,
        )
        if match:
            statuses[match.group(1)] = match.group(2)
    return statuses


def _extract_braced_block(text: str, start: int) -> str:
    brace = text.find("{", start)
    semicolon = text.find(";", start)
    if brace < 0 or (semicolon >= 0 and semicolon < brace):
        return text[start : semicolon + 1 if semicolon >= 0 else len(text)]
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return text[start:]


def _definition_block(text: str, kind: str, name: str) -> str:
    match = re.search(rf"\b{re.escape(kind)}\s+(?:def\s+)?{re.escape(name)}\b", text)
    return _extract_braced_block(text, match.start()) if match else ""


def _component_definition_name(text: str) -> str | None:
    for match in re.finditer(r"\bpart def\s+(\w+)(?:\s*:>\s*\w+)?\s*\{", text):
        block = _extract_braced_block(text, match.start())
        if re.search(r'@SpecIdentity\s*\{[^}]*id\s*=\s*"component\.', block, re.DOTALL):
            return match.group(1)
    return None


def _component_id(text: str) -> str | None:
    match = re.search(r'@SpecIdentity\s*\{[^}]*id\s*=\s*"(component\.[^"]+)"', text, re.DOTALL)
    return match.group(1) if match else None


def _protocol_methods(component_id: str) -> set[str]:
    code_root = ROOT / "components" / Path(*component_id.removeprefix("component.").split("."))
    protocol_path = code_root / "protocol.py"
    if not protocol_path.exists():
        return set()
    tree = ast.parse(protocol_path.read_text(encoding="utf-8"))
    methods: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(
            (isinstance(base, ast.Name) and base.id == "Protocol")
            or (isinstance(base, ast.Attribute) and base.attr == "Protocol")
            for base in node.bases
        ):
            continue
        methods.update(
            member.name
            for member in node.body
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not member.name.startswith("_")
        )
    return methods


def _words(value: str) -> list[str]:
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return [word.lower() for word in re.split(r"[^A-Za-z0-9]+", snake) if word]


def _model_action_for_method(component_id: str, method: str, actions: set[str]) -> str | None:
    aliases = {
        ("component.storage.sql", "execute"): "ExecuteSql",
        ("component.storage.sql", "query"): "QuerySql",
        ("component.storage.sql", "transaction"): "ExecuteSqlTransaction",
        ("component.rtg.query", "execute"): "ExecuteRtgQuery",
        ("component.rtg.migration", "from_migration"): "BuildMigrationCutoverPlan",
        ("component.rtg.constraints", "list_constraints"): "ListConstraints",
        ("component.rtg.constraints", "list_constraints_by_target"): "ListConstraintsByTarget",
        ("component.rtg.change_validation", "validate_batch"): "ValidateRtgChangeBatch",
        ("component.rtg.change_validation", "validate_graph_state"): "ValidateRtgGraphState",
    }
    alias = aliases.get((component_id, method))
    if alias:
        return alias if alias in actions else None
    method_words = set(_words(method))
    if method == "empty":
        return next((action for action in actions if action.startswith("CreateEmpty")), None)
    if method == "import_snapshot":
        return next(
            (
                action
                for action in actions
                if action.startswith("Import") and action.endswith("Snapshot")
            ),
            None,
        )
    noise = set(_words(component_id)) | {"rtg"}
    target = method_words - noise
    matches: list[tuple[int, int, str]] = []
    for action in actions:
        candidate = set(_words(action)) - noise
        if target and target <= candidate:
            matches.append((len(candidate - target), len(candidate), action))
    return min(matches)[2] if matches else None


def _method_has_model_action(component_id: str, method: str, actions: set[str]) -> bool:
    return _model_action_for_method(component_id, method, actions) is not None


def _check_protocol_action_coverage() -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(COMPONENT_MODEL_ROOT.glob("component.*.sysml")):
        text = path.read_text(encoding="utf-8")
        component_id = _component_id(text)
        if not component_id or component_id == "component.rtg.discovery":
            continue
        actions = set(re.findall(r"\baction def\s+(\w+)", text))
        missing = sorted(
            method
            for method in _protocol_methods(component_id)
            if not _method_has_model_action(component_id, method, actions)
        )
        if missing:
            findings.append(
                Finding(path, f"public protocol operations lack model actions: {missing}")
            )
    return findings


def _protocol_method_parameters(component_id: str) -> dict[str, tuple[str, ...]]:
    code_root = ROOT / "components" / Path(*component_id.removeprefix("component.").split("."))
    protocol_path = code_root / "protocol.py"
    if not protocol_path.exists():
        return {}
    tree = ast.parse(protocol_path.read_text(encoding="utf-8"))
    parameters: dict[str, tuple[str, ...]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or not any(
            (isinstance(base, ast.Name) and base.id == "Protocol")
            or (isinstance(base, ast.Attribute) and base.attr == "Protocol")
            for base in node.bases
        ):
            continue
        for member in node.body:
            if not isinstance(
                member, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) or member.name.startswith("_"):
                continue
            arguments = [*member.args.posonlyargs, *member.args.args, *member.args.kwonlyargs]
            parameters[member.name] = tuple(
                argument.arg for argument in arguments if argument.arg not in {"self", "cls"}
            )
    return parameters


def _protocol_signature_drift_is_acknowledged(component_id: str, method: str) -> bool:
    try:
        value = yaml.safe_load(IMPLEMENTATION_DRIFT_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return False
    component_module = component_id.removeprefix("component.")
    for entry in value.get("findings", []) if isinstance(value, dict) else []:
        if not isinstance(entry, dict):
            continue
        symbol = str(entry.get("implementation_symbol", ""))
        if (
            symbol.startswith(f"components.{component_module}.protocol.")
            and symbol.endswith(f".{method}")
        ):
            return True
    return False


def _check_protocol_action_signatures() -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(COMPONENT_MODEL_ROOT.glob("component.*.sysml")):
        text = path.read_text(encoding="utf-8")
        component_id = _component_id(text)
        if not component_id or component_id == "component.rtg.discovery":
            continue
        action_blocks = {
            match.group(1): _extract_braced_block(text, match.start())
            for match in re.finditer(r"\baction def\s+(\w+)\s*\{", text)
        }
        actions = set(action_blocks)
        for method, protocol_parameters in _protocol_method_parameters(component_id).items():
            action = _model_action_for_method(component_id, method, actions)
            if not action:
                continue
            model_parameters = tuple(
                name
                for name in re.findall(
                    r"\bin\s+(?:ref\s+)?(?:part\s+|item\s+)?(\w+)(?:\[[^]]+\])?\s*:",
                    action_blocks[action],
                )
            )
            normalized_protocol = tuple(_normalized_name(name) for name in protocol_parameters)
            normalized_model = tuple(_normalized_name(name) for name in model_parameters)
            signature_drift_acknowledged = _protocol_signature_drift_is_acknowledged(
                component_id, method
            )
            if normalized_protocol != normalized_model and not signature_drift_acknowledged:
                findings.append(
                    Finding(
                        path,
                        f"{method}/{action} input names or order differ: "
                        f"protocol={protocol_parameters}, model={model_parameters}",
                    )
                )
    return findings


def _check_empty_public_definitions(files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    pattern = re.compile(
        r"(?m)^\s*(?:attribute|item|part|action|state|calc|constraint) def\s+(\w+)\s*;"
    )
    for path in files:
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            findings.append(Finding(path, f"unexplained empty public definition {match.group(1)}"))
    return findings


def _check_native_modeling_style(files: list[Path]) -> list[Finding]:
    """Reject project-profile patterns that duplicate or misuse native SysML semantics."""
    findings: list[Finding] = []
    foundation = MODEL_ROOT / "foundation" / "SoftwareComponentModeling.sysml"
    for path in files:
        text = path.read_text(encoding="utf-8")
        if re.search(r"\bContractKind\b|@ContractRole\b", text):
            findings.append(
                Finding(path, "provided/required roles must use native perform/reference semantics")
            )
        if path.parent == COMPONENT_MODEL_ROOT and "@ImplementationBinding" in text:
            findings.append(
                Finding(path, "logical component definitions must not contain realization bindings")
            )
        for match in re.finditer(
            r"dependency\s+\w+\s+from\s+\w+\s+to\s+(required\w+)\s*\{(.*?)\}",
            text,
            flags=re.DOTALL,
        ):
            if "@StateAccess" in match.group(2):
                findings.append(
                    Finding(
                        path,
                        f"capability dependency to {match.group(1)} misuses StateAccess",
                    )
                )
    if foundation in files:
        foundation_text = foundation.read_text(encoding="utf-8")
        if re.search(r"\bMcp\w*\b|\bTransportKind\b", foundation_text):
            findings.append(
                Finding(foundation, "application/transport vocabulary leaked into the foundation")
            )
    return findings


def _check_component_contract_completeness() -> list[Finding]:
    """Reject structurally present but semantically empty component contracts."""
    findings: list[Finding] = []
    all_model_text = "\n".join(path.read_text(encoding="utf-8") for path in _sysml_files("all"))
    known_definitions = set(
        re.findall(
            r"\b(?:attribute|item|part|action|state|calc|constraint) def\s+(\w+)",
            all_model_text,
        )
    )
    for path in sorted(COMPONENT_MODEL_ROOT.glob("component.*.sysml")):
        text = path.read_text(encoding="utf-8")
        component_name = _component_definition_name(text)
        component_block = (
            _definition_block(text, "part def", component_name) if component_name else ""
        )

        for match in re.finditer(r"\baction def\s+(\w+)\s*\{", text):
            action_name = match.group(1)
            block = _extract_braced_block(text, match.start())
            if not _documentation(block):
                findings.append(Finding(path, f"public action {action_name} lacks semantics doc"))
            failure = re.search(r"@FailureContract\s*\{(.*?)\}", block, re.DOTALL)
            if not failure:
                findings.append(Finding(path, f"public action {action_name} lacks FailureContract"))
                continue
            for error_id in re.findall(r'"([A-Za-z]\w+)"', failure.group(1)):
                if error_id not in known_definitions:
                    findings.append(
                        Finding(path, f"action {action_name} names unknown failure {error_id}")
                    )

        if component_block:
            for match in re.finditer(
                r"perform action\s+(\w+)\[[^]]+\]\s*:\s*(\w+)", component_block
            ):
                feature, action_name = match.groups()
                feature_block = _extract_braced_block(component_block, match.start())
                direct_access = "@StateAccess" in feature_block
                dependency_access = bool(
                    re.search(
                        rf"dependency\s+\w+\s+from\s+{re.escape(feature)}\s+to\s+"
                        r"[\w.]+\s*\{[^}]*(?:@StateAccess|@CapabilityUse)",
                        component_block,
                        re.DOTALL,
                    )
                )
                if not direct_access and not dependency_access:
                    findings.append(
                        Finding(
                            path,
                            f"provided action {feature}:{action_name} lacks "
                            "state/capability effect",
                        )
                    )

        requirement_names: set[str] = set()
        for match in re.finditer(r"\brequirement\s+(\w+)\s*\{", text):
            name = match.group(1)
            requirement_names.add(name)
            block = _extract_braced_block(text, match.start())
            if not re.search(r'@StableId\s*\{[^}]*id\s*=\s*"[^\"]+"', block, re.DOTALL):
                findings.append(Finding(path, f"requirement {name} lacks StableId"))
            if not _documentation(block):
                findings.append(Finding(path, f"requirement {name} lacks normative text"))
        verified = set(re.findall(r"\bverify\s+(\w+)\s*;", text))
        for name in sorted(requirement_names - verified):
            findings.append(Finding(path, f"requirement {name} lacks verification objective"))
    return findings


def _normalized_name(value: str) -> str:
    return "".join(_words(value))


def _markdown_sections(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"(?m)^###\s+`([^`]+)`\s*$", text))
    return [
        (
            match.group(1),
            text[
                match.end() : matches[index + 1].start() if index + 1 < len(matches) else len(text)
            ],
        )
        for index, match in enumerate(matches)
    ]


def _modeled_public_fields(
    text: str, definition_name: str, seen: set[str] | None = None
) -> set[str]:
    seen = set() if seen is None else seen
    if definition_name in seen:
        return set()
    seen.add(definition_name)
    match = re.search(
        rf"\b(?:attribute|item) def\s+{re.escape(definition_name)}"
        r"(?:\s*:>\s*(\w+))?\s*\{",
        text,
    )
    if not match:
        return set()
    block = _extract_braced_block(text, match.start())
    fields = {
        _normalized_name(name)
        for name in re.findall(r"\b(?:attribute|item|part)\s+(\w+)(?:\[[^]]+\])?\s*:", block)
    }
    parent = match.group(1)
    if parent:
        fields.update(_modeled_public_fields(text, parent, seen))
    return fields


def _check_shadow_contract_parity() -> list[Finding]:
    """Keep accepted Markdown meaning visible while this repository remains in shadow mode."""
    findings: list[Finding] = []
    all_model_text = "\n".join(path.read_text(encoding="utf-8") for path in _sysml_files("all"))
    all_definitions = set(
        re.findall(r"\b(?:attribute|item|part|action) def\s+(\w+)", all_model_text)
    )
    for model_path in sorted(COMPONENT_MODEL_ROOT.glob("component.*.sysml")):
        model_text = model_path.read_text(encoding="utf-8")
        component_id = _component_id(model_text)
        if not component_id:
            continue
        markdown_path = ROOT / "docs" / "components" / f"{component_id}.md"
        if not markdown_path.exists():
            continue
        markdown_text = markdown_path.read_text(encoding="utf-8")
        action_blocks = {
            match.group(1): _extract_braced_block(model_text, match.start())
            for match in re.finditer(r"\baction def\s+(\w+)\s*\{", model_text)
        }
        action_names = set(action_blocks)

        markdown_invariants = set(re.findall(r"(?m)^###\s+`(invariant\.[^`]+)`\s*$", markdown_text))
        model_invariants = set(re.findall(r'id\s*=\s*"(invariant\.[^"]+)"', model_text))
        for invariant in sorted(markdown_invariants - model_invariants):
            findings.append(Finding(model_path, f"accepted invariant omitted: {invariant}"))

        for heading, section in _markdown_sections(markdown_text):
            if "." in heading:
                method_name = heading.rsplit(".", 1)[-1]
                action_name = _model_action_for_method(component_id, method_name, action_names)
                if action_name:
                    action_block = action_blocks[action_name]
                    inputs_match = re.search(
                        r"(?ms)^Inputs:\s*(.*?)(?=^[A-Z][A-Za-z ]+:\s*$|\Z)", section
                    )
                    if inputs_match:
                        raw_markdown_inputs = re.findall(
                            r"(?m)^-\s+`([^`]+)`", inputs_match.group(1)
                        )
                        markdown_inputs = tuple(
                            _normalized_name(name.split(" |", 1)[0])
                            for name in raw_markdown_inputs
                        )
                        model_inputs = tuple(
                            _normalized_name(name)
                            for name in re.findall(
                                r"\bin\s+(?:ref\s+)?(?:part\s+|item\s+)?(\w+)"
                                r"(?:\[[^]]+\])?\s*:",
                                action_block,
                            )
                        )
                        markdown_lists_only_a_type = (
                            len(raw_markdown_inputs) == 1
                            and raw_markdown_inputs[0][:1].isupper()
                        )
                        if not markdown_lists_only_a_type and markdown_inputs != model_inputs:
                            findings.append(
                                Finding(
                                    model_path,
                                    f"{heading} input contract differs: "
                                    f"markdown={markdown_inputs}, model={model_inputs}",
                                )
                            )

            fields_match = re.search(
                r"(?ms)^Fields:\s*(.*?)"
                r"(?=^[A-Z][A-Za-z ]+:\s*$|^Semantics:\s*$|^Validation:\s*$|\Z)",
                section,
            )
            if fields_match:
                definition_name = heading.rsplit(".", 1)[-1]
                definition_block = ""
                for kind in ("attribute def", "item def"):
                    definition_block = _definition_block(model_text, kind, definition_name)
                    if definition_block:
                        break
                if not definition_block:
                    findings.append(
                        Finding(model_path, f"accepted public value omitted: {definition_name}")
                    )
                else:
                    expected = {
                        _normalized_name(name)
                        for name in re.findall(r"(?m)^-\s+`([A-Za-z_]\w*)`", fields_match.group(1))
                    }
                    modeled = _modeled_public_fields(model_text, definition_name)
                    missing = sorted(expected - modeled)
                    if missing:
                        findings.append(
                            Finding(
                                model_path,
                                f"{definition_name} omits accepted fields: {missing}",
                            )
                        )

            errors_match = re.search(
                r"(?ms)^Errors:\s*(.*?)(?=^[A-Z][A-Za-z ]+:\s*$|^Semantics:\s*$|\Z)",
                section,
            )
            if errors_match:
                expected_errors = set(
                    re.findall(r"(?m)^-\s+`([A-Za-z]\w+)`", errors_match.group(1))
                )
                for error_name in expected_errors:
                    if error_name not in all_definitions:
                        findings.append(
                            Finding(model_path, f"accepted failure omitted: {error_name}")
                        )
                if "." in heading:
                    method_name = heading.rsplit(".", 1)[-1]
                    action_name = _model_action_for_method(
                        component_id, method_name, action_names
                    )
                    if action_name:
                        failure = re.search(
                            r"@FailureContract\s*\{(.*?)\}",
                            action_blocks[action_name],
                            re.DOTALL,
                        )
                        modeled_errors = (
                            set(re.findall(r'"([A-Za-z]\w+)"', failure.group(1)))
                            if failure
                            else set()
                        )
                        missing_action_errors = expected_errors - modeled_errors
                        if missing_action_errors:
                            findings.append(
                                Finding(
                                    model_path,
                                    f"{heading} omits accepted action failures: "
                                    f"{sorted(missing_action_errors)}",
                                )
                            )
    return findings


def _check_implementation_drift_file() -> list[Finding]:
    try:
        value = yaml.safe_load(IMPLEMENTATION_DRIFT_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        return [
            Finding(IMPLEMENTATION_DRIFT_PATH, f"invalid implementation drift artifact: {error}")
        ]
    if not isinstance(value, dict) or not isinstance(value.get("findings"), list):
        return [Finding(IMPLEMENTATION_DRIFT_PATH, "findings must be a list")]
    findings: list[Finding] = []
    seen: set[str] = set()
    required = {
        "id",
        "model_element",
        "implementation_symbol",
        "observed",
        "expected",
        "verification",
    }
    model_text = "\n".join(path.read_text(encoding="utf-8") for path in _sysml_files("all"))
    for entry in value["findings"]:
        if not isinstance(entry, dict) or not required <= set(entry):
            findings.append(Finding(IMPLEMENTATION_DRIFT_PATH, "drift entry lacks required fields"))
            continue
        drift_id = str(entry["id"])
        if drift_id in seen:
            findings.append(Finding(IMPLEMENTATION_DRIFT_PATH, f"duplicate drift ID {drift_id}"))
        seen.add(drift_id)
        if str(entry["model_element"]) not in model_text:
            findings.append(
                Finding(
                    IMPLEMENTATION_DRIFT_PATH,
                    f"drift {drift_id} references unknown model element {entry['model_element']}",
                )
            )
        symbol = str(entry["implementation_symbol"])
        if not _python_symbol_exists(ROOT, symbol):
            findings.append(
                Finding(
                    IMPLEMENTATION_DRIFT_PATH,
                    f"drift {drift_id} references unknown symbol {symbol}",
                )
            )
    return findings


def _check_verification_closure() -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(COMPONENT_MODEL_ROOT.glob("component.*.sysml")):
        text = path.read_text(encoding="utf-8")
        component_id = _component_id(text) or path.stem
        status = _component_model_statuses().get(component_id)
        verification = re.search(r"\bverification def\s+\w+\s*\{", text)
        if not verification:
            findings.append(Finding(path, "component lacks a boundary verification definition"))
            continue
        block = _extract_braced_block(text, verification.start())
        if not re.search(r"\bobjective\s*\{.*?\bverify\s+\w+", block, re.DOTALL):
            findings.append(Finding(path, "boundary verification has no modeled objective"))
        evidence = re.search(r'evidenceId\s*=\s*"([^"]+)"', block)
        if not evidence:
            findings.append(Finding(path, "boundary verification lacks evidence binding"))
        elif status != "draft" and not (ROOT / evidence.group(1)).exists():
            findings.append(
                Finding(path, f"boundary evidence does not resolve: {evidence.group(1)}")
            )
    return findings


def _check_vellis_use_cases() -> list[Finding]:
    path = MODEL_ROOT / "vellis" / "use-cases" / "VellisUseCases.sysml"
    text = path.read_text(encoding="utf-8")
    definitions = set(re.findall(r"\buse case def\s+(\w+)", text))
    usages = {
        type_name for _, type_name in re.findall(r"\buse case\s+(?!def\b)(\w+)\s*:\s*(\w+)", text)
    }
    findings: list[Finding] = []
    if definitions != usages:
        findings.append(
            Finding(
                path,
                "use-case definitions and realized usages differ: "
                f"defs={definitions}, usages={usages}",
            )
        )
    for match in re.finditer(r"\buse case def\s+\w+\s*\{", text):
        block = _extract_braced_block(text, match.start())
        if not re.search(r"actor\s+users\[1\.\.\*]\s*:\s*VellisUser", block):
            findings.append(Finding(path, "use case must bind one or more VellisUser actors"))
    return findings


def _python_tool_names() -> tuple[str, ...]:
    source_path = ROOT / "apps" / "rtg_knowledge_graph" / "mcp_toolset.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "TOOL_NAMES" and node.value is not None:
                value = ast.literal_eval(node.value)
                return tuple(str(item) for item in value)
    raise ValueError("TOOL_NAMES was not found in mcp_toolset.py")


def _python_tool_parameters() -> dict[str, tuple[tuple[str, bool, Any], ...]]:
    source_path = ROOT / "apps" / "rtg_knowledge_graph" / "mcp_toolset.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    parameters: dict[str, tuple[tuple[str, bool, Any], ...]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "RtgMcpToolset":
            continue
        for member in node.body:
            if not isinstance(
                member, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) or not member.name.startswith("rtg_"):
                continue
            arguments = member.args.args[1:]
            required_count = len(arguments) - len(member.args.defaults)
            defaults: list[Any] = [None] * required_count + [
                ast.literal_eval(default) for default in member.args.defaults
            ]
            parameters[member.name] = tuple(
                (argument.arg, index >= required_count, defaults[index])
                for index, argument in enumerate(arguments)
            )
    return parameters


def _model_default(value: str | None) -> Any:
    if value is None:
        return None
    value = value.strip()
    if value == "true":
        return True
    if value == "false":
        return False
    if "::" in value:
        return value.rsplit("::", 1)[-1]
    try:
        return ast.literal_eval(value)
    except ValueError, SyntaxError:
        return value


def _model_tool_parameters() -> dict[str, tuple[tuple[str, bool, Any], ...]]:
    text = _without_comments(
        (MODEL_ROOT / "vellis" / "VellisOperations.sysml").read_text(encoding="utf-8")
    )
    parameters: dict[str, tuple[tuple[str, bool, Any], ...]] = {}
    start_pattern = re.compile(r"action def\s+\w+\s*\{")
    for match in start_pattern.finditer(text):
        depth = 0
        end = match.end()
        for index in range(match.end() - 1, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        block = text[match.start() : end]
        identity = re.search(r'id\s*=\s*"operation\.vellis\.([^"]+)"', block)
        if not identity:
            continue
        action_parameters = []
        for parameter, multiplicity, default in re.findall(
            r"\bin\s+(\w+)\s*:\s*\w+(\[[^]]+\])?(?:\s*=\s*([^;{}]+))?",
            block,
        ):
            action_parameters.append(
                (parameter, multiplicity == "[0..1]", _model_default(default or None))
            )
        parameters[identity.group(1)] = tuple(action_parameters)
    return parameters


def _python_tool_description_names() -> set[str]:
    source_path = ROOT / "apps" / "rtg_knowledge_graph" / "mcp_toolset.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "TOOL_DESCRIPTIONS" and node.value is not None:
                value = ast.literal_eval(node.value)
                return {str(key) for key in value}
    raise ValueError("TOOL_DESCRIPTIONS was not found in mcp_toolset.py")


def _model_tool_names() -> tuple[str, ...]:
    text = (MODEL_ROOT / "vellis" / "realizations" / "VellisMcpPython.sysml").read_text(
        encoding="utf-8"
    )
    return tuple(re.findall(r'toolName\s*=\s*"([^"]+)"', text))


def _model_operation_ids() -> tuple[str, ...]:
    text = (MODEL_ROOT / "vellis" / "VellisOperations.sysml").read_text(encoding="utf-8")
    return tuple(re.findall(r'id\s*=\s*"(operation\.vellis\.[^"]+)"', text))


def _model_operation_blocks() -> dict[str, str]:
    text = (MODEL_ROOT / "vellis" / "VellisOperations.sysml").read_text(encoding="utf-8")
    blocks: dict[str, str] = {}
    for match in re.finditer(r"\baction def\s+\w+\s*\{", text):
        block = _extract_braced_block(text, match.start())
        identity = re.search(r'id\s*=\s*"operation\.vellis\.([^"]+)"', block)
        if identity:
            blocks[identity.group(1)] = block
    return blocks


def _check_vellis_contract_completeness() -> list[Finding]:
    operations_path = MODEL_ROOT / "vellis" / "VellisOperations.sysml"
    realization_path = MODEL_ROOT / "vellis" / "realizations" / "VellisMcpPython.sysml"
    findings: list[Finding] = []
    blocks = _model_operation_blocks()
    for tool_name in _model_tool_names():
        block = blocks.get(tool_name)
        if not block:
            findings.append(Finding(operations_path, f"MCP tool {tool_name} lacks typed action"))
            continue
        if not _documentation(block):
            findings.append(Finding(operations_path, f"Vellis action {tool_name} lacks semantics"))
        if "@FailureContract" not in block:
            findings.append(
                Finding(operations_path, f"Vellis action {tool_name} lacks failure semantics")
            )

    operations_text = operations_path.read_text(encoding="utf-8")
    for contract_id in (
        "contract.vellis.facade.failures",
        "contract.vellis.facade.implementation_freedom",
        "contract.vellis.facade.usage_guides",
        "contract.vellis.facade.schema_migration_compilation",
        "contract.vellis.facade.anchor_record_compilation",
        "contract.vellis.facade.query_semantics",
        "contract.vellis.facade.snapshot_semantics",
        "contract.vellis.facade.controller_forwarding",
    ):
        if contract_id not in operations_text:
            findings.append(Finding(operations_path, f"Vellis facade omits {contract_id}"))
    facade_block = _definition_block(
        operations_text, "part def", "VellisApplicationFacade"
    )
    for performance in re.finditer(
        r"perform action\s+(\w+)\[[^]]+\]\s*:\s*(\w+)", facade_block
    ):
        feature = performance.group(1)
        performance_has_effect = False
        body_start = facade_block.find("{", performance.end())
        statement_end = facade_block.find(";", performance.end())
        if body_start != -1 and (statement_end == -1 or body_start < statement_end):
            performance_body = _extract_braced_block(facade_block, body_start)
            performance_has_effect = (
                "@StateAccess" in performance_body or "@CapabilityUse" in performance_body
            )
        dependency_has_effect = bool(
            re.search(
                rf"dependency\s+\w+\s+from\s+{re.escape(feature)}\s+to\s+\w+\s*\{{"
                r".*?@CapabilityUse",
                facade_block,
                flags=re.DOTALL,
            )
        )
        if not performance_has_effect and not dependency_has_effect:
            findings.append(
                Finding(
                    operations_path,
                    f"Vellis facade action {feature} lacks required-capability/effect semantics",
                )
            )

    realization_text = realization_path.read_text(encoding="utf-8")
    for construct in (
        "item def McpToolInvocation",
        "item def McpToolResponse",
        "port def McpEndpoint {",
        "interface def McpToolExchange {",
        "flow clientEndpoint.invocation to adapterEndpoint.invocation",
        "flow adapterEndpoint.response to clientEndpoint.response",
    ):
        if construct not in realization_text:
            findings.append(
                Finding(realization_path, f"MCP connected interaction omits {construct}")
            )
    for contract_id in (
        "contract.vellis.mcp.description_authority",
        "contract.vellis.mcp.input_encoding",
        "contract.vellis.mcp.result_encoding",
        "contract.vellis.mcp.failure_encoding",
        "contract.vellis.mcp.transport_equivalence",
    ):
        if contract_id not in realization_text:
            findings.append(Finding(realization_path, f"MCP surface omits {contract_id}"))

    controller_text = (
        MODEL_ROOT / "bibliotek" / "components" / "component.rtg.controller.sysml"
    ).read_text(encoding="utf-8")
    required_controller_terms = (
        "enum strict; enum skip;",
        "enum record; enum skip;",
        'name = "restore_pre_cutover_snapshot"',
        'name = "cutover_applied"',
        'name = "ledger_failures_flushed"',
        "contract.rtg.controller.operation_results",
        "contract.rtg.controller.replay_selection",
    )
    for term in required_controller_terms:
        if term not in controller_text:
            findings.append(Finding(operations_path, f"controller black-box profile omits {term}"))
    return findings


def _vellis_roles() -> dict[str, str]:
    text = (MODEL_ROOT / "vellis" / "Vellis.sysml").read_text(encoding="utf-8")
    role_types = dict(
        re.findall(
            r"(?m)^\s*part\s+(\w+)\s*:\s*"
            r"(JsonFileStorage|SqlStorage|RtgGraph|RtgSchema|RtgConstraints|RtgMigration|"
            r"RtgQueryEngine|RtgChangeValidator|RtgController)\s*;",
            text,
        )
    )
    type_to_id = {
        "JsonFileStorage": "component.storage.json_file",
        "SqlStorage": "component.storage.sql",
        "RtgGraph": "component.rtg.graph",
        "RtgSchema": "component.rtg.schema",
        "RtgConstraints": "component.rtg.constraints",
        "RtgMigration": "component.rtg.migration",
        "RtgQueryEngine": "component.rtg.query",
        "RtgChangeValidator": "component.rtg.change_validation",
        "RtgController": "component.rtg.controller",
    }
    return {role: type_to_id[type_name] for role, type_name in role_types.items()}


def _component_contracts() -> tuple[
    dict[tuple[str, str], tuple[str, int, int]], dict[tuple[str, str], str]
]:
    required: dict[tuple[str, str], tuple[str, int, int]] = {}
    provided: dict[tuple[str, str], str] = {}
    parents: dict[str, str] = {}
    contract_paths = list(COMPONENT_MODEL_ROOT.glob("*.sysml"))
    vellis_operations = MODEL_ROOT / "vellis" / "VellisOperations.sysml"
    if vellis_operations.exists():
        contract_paths.append(vellis_operations)
    for path in contract_paths:
        text = path.read_text(encoding="utf-8")
        for component_match in re.finditer(r"\bpart def\s+(\w+)(?:\s*:>\s*(\w+))?\s*\{", text):
            component_type = component_match.group(1)
            parent = component_match.group(2)
            if parent:
                parents[component_type] = parent
            block = _extract_braced_block(text, component_match.start())
            for reference in re.finditer(
                r"ref action\s+(\w+)\[[^]]+\]\s*:\s*(\w+)(.*?)"
                r"(?=\n\s*(?:ref|perform|dependency|item|attribute|part|})|$)",
                block,
                flags=re.DOTALL,
            ):
                metadata = reference.group(3)
                lower = re.search(r"providerLowerBound\s*=\s*(\d+)", metadata)
                upper = re.search(r"providerUpperBound\s*=\s*(\d+)", metadata)
                if lower and upper:
                    required[(component_type, reference.group(1))] = (
                        reference.group(2),
                        int(lower.group(1)),
                        int(upper.group(1)),
                    )
                else:
                    required[(component_type, reference.group(1))] = (reference.group(2), -1, -1)
            for performance in re.finditer(r"perform action\s+(\w+)\[[^]]+\]\s*:\s*(\w+)", block):
                provided[(component_type, performance.group(1))] = performance.group(2)

    for component_type, parent in parents.items():
        for (owner, feature), action_type in list(provided.items()):
            if owner == parent:
                provided.setdefault((component_type, feature), action_type)
    return required, provided


def _check_contract_satisfaction() -> list[Finding]:
    path = MODEL_ROOT / "vellis" / "Vellis.sysml"
    text = path.read_text(encoding="utf-8")
    role_types = dict(re.findall(r"(?m)^\s*part\s+(\w+)\s*:\s*(\w+)\s*;", text))
    required, provided = _component_contracts()
    relationships = re.findall(r"\bfrom\s+(\w+)\.(\w+)\s+to\s+(\w+)\.(\w+)", text, flags=re.DOTALL)
    findings: list[Finding] = []
    counts: dict[tuple[str, str], int] = {}
    for consumer_role, required_feature, provider_role, provided_feature in relationships:
        consumer_type = role_types.get(consumer_role)
        provider_type = role_types.get(provider_role)
        required_contract = required.get((consumer_type or "", required_feature))
        provided_contract = provided.get((provider_type or "", provided_feature))
        if required_contract is None:
            findings.append(
                Finding(path, f"unknown required feature {consumer_role}.{required_feature}")
            )
            continue
        counts[(consumer_role, required_feature)] = (
            counts.get((consumer_role, required_feature), 0) + 1
        )
        if provided_contract is None:
            findings.append(
                Finding(path, f"unknown provided feature {provider_role}.{provided_feature}")
            )
        elif provided_contract != required_contract[0]:
            findings.append(
                Finding(
                    path,
                    f"contract type mismatch: {consumer_role}.{required_feature} requires "
                    f"{required_contract[0]}, but {provider_role}.{provided_feature} provides "
                    f"{provided_contract}",
                )
            )
    view_relationships = re.findall(
        r"\bfrom\s+(\w+)\.(\w+)\s+to\s+(\w+)\s*\{", text, flags=re.DOTALL
    )
    for consumer_role, required_feature, provider_role in view_relationships:
        consumer_type = role_types.get(consumer_role)
        provider_type = role_types.get(provider_role)
        required_part: tuple[str, int, int] | None = None
        for component_path in COMPONENT_MODEL_ROOT.glob("*.sysml"):
            component_text = component_path.read_text(encoding="utf-8")
            component_name = _component_definition_name(component_text)
            if component_name is None or component_name != consumer_type:
                continue
            component_block = _definition_block(component_text, "part def", component_name)
            match = re.search(
                rf"ref part\s+{re.escape(required_feature)}\s*:\s*(\w+)\s*\{{(.*?)\}}",
                component_block,
                flags=re.DOTALL,
            )
            if match:
                lower = re.search(r"providerLowerBound\s*=\s*(\d+)", match.group(2))
                upper = re.search(r"providerUpperBound\s*=\s*(\d+)", match.group(2))
                required_part = (
                    match.group(1),
                    int(lower.group(1)) if lower else -1,
                    int(upper.group(1)) if upper else -1,
                )
            break
        if required_part is None:
            findings.append(
                Finding(path, f"unknown required feature {consumer_role}.{required_feature}")
            )
            continue
        provider_definition = ""
        for component_path in COMPONENT_MODEL_ROOT.glob("*.sysml"):
            candidate_text = component_path.read_text(encoding="utf-8")
            if _component_definition_name(candidate_text) == provider_type:
                provider_definition = _definition_block(
                    candidate_text, "part def", provider_type or ""
                )
                break
        required_type, lower, upper = required_part
        compatible = provider_type == required_type or bool(
            re.search(
                rf"part def\s+{re.escape(provider_type or '')}\s*:>\s*{re.escape(required_type)}",
                provider_definition,
            )
        )
        if not compatible:
            findings.append(
                Finding(
                    path,
                    f"contract type mismatch: {consumer_role}.{required_feature} requires "
                    f"{required_type}, but {provider_role} is {provider_type}",
                )
            )
        if not (lower <= 1 <= upper):
            findings.append(
                Finding(
                    path,
                    f"provider cardinality for {consumer_role}.{required_feature} is 1; "
                    f"expected {lower}..{upper}",
                )
            )
    for (component_type, feature), (_, lower, upper) in required.items():
        if lower < 0 or upper < 0:
            findings.append(
                Finding(
                    COMPONENT_MODEL_ROOT,
                    f"{component_type}.{feature} lacks explicit provider cardinality",
                )
            )
            continue
        matching_roles = [
            role for role, role_type in role_types.items() if role_type == component_type
        ]
        for role in matching_roles:
            count = counts.get((role, feature), 0)
            if not lower <= count <= upper:
                findings.append(
                    Finding(
                        path,
                        f"provider cardinality for {role}.{feature} is {count}; expected "
                        f"{lower}..{upper}",
                    )
                )
    return findings


def _check_allowed_profile(files: list[Path]) -> list[Finding]:
    profile_path = MODEL_ROOT / "allowed-constructs.json"
    try:
        profile = _read_json(profile_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return [Finding(profile_path, f"invalid allowed-construct profile: {error}")]
    patterns = profile.get("forbidden_patterns", [])
    if not isinstance(patterns, list):
        return [Finding(profile_path, "forbidden_patterns must be a list")]
    findings: list[Finding] = []
    for path in files:
        text = _without_comments(path.read_text(encoding="utf-8"))
        for pattern in patterns:
            if isinstance(pattern, str) and re.search(pattern, text):
                findings.append(
                    Finding(path, f"construct is outside the baseline profile: {pattern}")
                )
    return findings


def _python_symbol_exists(code_root: Path, symbol: str) -> bool:
    pieces = symbol.split(".")
    leaf = pieces[-1]
    parent = pieces[-2] if len(pieces) > 1 else None
    for path in code_root.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except OSError, SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == leaf:
                    return True
                if isinstance(node, ast.ClassDef) and node.name == parent:
                    if any(
                        isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and member.name == leaf
                        for member in node.body
                    ):
                        return True
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if any(
                    (alias.asname or alias.name.rsplit(".", 1)[-1]) == leaf for alias in node.names
                ):
                    return True
    return False


def _check_implementation_bindings(files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for block in re.findall(r"@ImplementationBinding\s*\{(.*?)\}", text, re.DOTALL):
            code_root_match = re.search(r'codeRoot\s*=\s*"([^"]*)"', block)
            symbol_match = re.search(r'symbol\s*=\s*"([^"]*)"', block)
            realization_match = re.search(r'realization\s*=\s*"([^"]*)"', block)
            if not code_root_match or not symbol_match:
                findings.append(Finding(path, "incomplete implementation binding"))
                continue
            code_root = ROOT / code_root_match.group(1)
            symbol = symbol_match.group(1)
            realization = realization_match.group(1) if realization_match else ""
            if realization == "unimplemented" and not symbol:
                continue
            if not code_root.is_dir():
                findings.append(
                    Finding(path, f"implementation code root does not exist: {code_root}")
                )
            elif not symbol or not _python_symbol_exists(code_root, symbol):
                findings.append(Finding(path, f"implementation symbol does not exist: {symbol}"))
    return findings


def _check_forbidden_component_imports() -> list[Finding]:
    findings: list[Finding] = []
    for model_path in COMPONENT_MODEL_ROOT.glob("component.*.sysml"):
        text = model_path.read_text(encoding="utf-8")
        identity = re.search(r'@SpecIdentity\s*\{[^}]*id\s*=\s*"([^"]+)"', text, re.DOTALL)
        policy = re.search(
            r"@DependencyPolicy\s*\{.*?forbiddenComponentIds\s*=\s*\((.*?)\);",
            text,
            re.DOTALL,
        )
        if not identity or not policy:
            continue
        component_id = identity.group(1)
        code_root = ROOT / "components" / Path(*component_id.removeprefix("component.").split("."))
        if not code_root.is_dir():
            continue
        forbidden_modules = {
            "components." + forbidden.removeprefix("component.")
            for forbidden in re.findall(r'"(component\.[^"]+)"', policy.group(1))
        }
        for python_path in code_root.rglob("*.py"):
            try:
                tree = ast.parse(python_path.read_text(encoding="utf-8"))
            except OSError, SyntaxError:
                continue
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module)
            violations = sorted(
                imported
                for imported in imports
                if any(
                    imported == forbidden or imported.startswith(forbidden + ".")
                    for forbidden in forbidden_modules
                )
            )
            if violations:
                findings.append(
                    Finding(
                        python_path,
                        f"{component_id} imports forbidden component modules: {violations}",
                    )
                )
    return findings


def check(scope: str = "all", *, require_external: bool = False) -> list[Finding]:
    findings: list[Finding] = []
    files = _sysml_files(scope)
    if not files:
        return [Finding(MODEL_ROOT, f"no SysML files found for {scope}")]

    findings.extend(_check_allowed_profile(files))
    findings.extend(_check_implementation_bindings(files))
    findings.extend(_check_empty_public_definitions(files))
    findings.extend(_check_native_modeling_style(files))

    stable_ids: dict[str, Path] = {}
    for path in files:
        text = path.read_text(encoding="utf-8")
        findings.extend(_balanced_delimiters(path, text))
        for line_number, line in enumerate(text.splitlines(), 1):
            if re.search(r"\b(?:perform|ref)\s+action\s+\w+\s*:", line):
                findings.append(
                    Finding(path, "invocable action usage lacks explicit multiplicity", line_number)
                )
            scrubbed_line = _without_comments(line)
            if re.search(r"\bbind\b", scrubbed_line) and re.search(
                r"required|provided", scrubbed_line, re.IGNORECASE
            ):
                findings.append(
                    Finding(
                        path,
                        "binding cannot satisfy a provided/required software contract",
                        line_number,
                    )
                )
        for stable_id in re.findall(
            r"@(?>SpecIdentity|StableId)\s*\{[^}]*\bid\s*=\s*\"([^\"]+)\"",
            text,
            flags=re.DOTALL,
        ):
            if stable_id in stable_ids:
                findings.append(
                    Finding(
                        path, f"duplicate stable ID {stable_id} (also in {stable_ids[stable_id]})"
                    )
                )
            stable_ids[stable_id] = path

    lock_path = MODEL_ROOT / "model.lock.json"
    try:
        lock = _read_json(lock_path)
        language = lock.get("language", {})
        if (
            not isinstance(language, dict)
            or language.get("sysml") != "2.0"
            or language.get("kerml") != "1.0"
        ):
            findings.append(Finding(lock_path, "baseline must remain SysML 2.0 and KerML 1.0"))
        libraries = lock.get("libraries", {})
        artifacts = libraries.get("artifacts", []) if isinstance(libraries, dict) else []
        if len(artifacts) != 4 or any(
            not isinstance(artifact, dict)
            or not re.fullmatch(r"[0-9a-f]{64}", str(artifact.get("sha256", "")))
            for artifact in artifacts
        ):
            findings.append(
                Finding(lock_path, "four formal KPAR artifacts must be checksum-pinned")
            )
        grammar = lock.get("grammar", {})
        grammar_artifacts = list(grammar.values()) if isinstance(grammar, dict) else []
        if len(grammar_artifacts) != 2 or any(
            not isinstance(artifact, dict)
            or not re.fullmatch(r"[0-9a-f]{64}", str(artifact.get("sha256", "")))
            for artifact in grammar_artifacts
        ):
            findings.append(Finding(lock_path, "SysML and KerML grammar sources must be pinned"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        findings.append(Finding(lock_path, f"invalid model lock: {error}"))

    if scope in {"bibliotek", "vellis", "all"}:
        bibliotek_text = "\n".join(
            path.read_text(encoding="utf-8") for path in (MODEL_ROOT / "bibliotek").rglob("*.sysml")
        )
        if re.search(r"\bimport\s+Vellis", bibliotek_text):
            findings.append(Finding(MODEL_ROOT / "bibliotek", "Bibliotek must not import Vellis"))
        models = _component_model_statuses()
        if len(models) != 10:
            findings.append(
                Finding(COMPONENT_MODEL_ROOT, f"expected 10 components, found {len(models)}")
            )
        findings.extend(_check_forbidden_component_imports())
        findings.extend(_check_protocol_action_coverage())
        findings.extend(_check_protocol_action_signatures())
        findings.extend(_check_component_contract_completeness())
        findings.extend(_check_shadow_contract_parity())
        findings.extend(_check_verification_closure())

    if scope in {"vellis", "all"}:
        roles = _vellis_roles()
        if roles != EXPECTED_VELLIS_ROLES:
            findings.append(
                Finding(MODEL_ROOT / "vellis" / "Vellis.sysml", f"Vellis roles differ: {roles}")
            )
        model_tools = _model_tool_names()
        python_tools = _python_tool_names()
        if len(model_tools) != 27 or set(model_tools) != set(python_tools):
            findings.append(
                Finding(
                    MODEL_ROOT / "vellis" / "realizations" / "VellisMcpPython.sysml",
                    f"MCP model/code drift: model={model_tools}, code={python_tools}",
                )
            )
        if _model_tool_parameters() != _python_tool_parameters():
            findings.append(
                Finding(
                    MODEL_ROOT / "vellis" / "VellisOperations.sysml",
                    "Vellis facade parameter names or required/optional multiplicities differ "
                    "from the MCP implementation",
                )
            )
        if _python_tool_description_names() != set(python_tools):
            findings.append(
                Finding(
                    ROOT / "apps" / "rtg_knowledge_graph" / "mcp_toolset.py",
                    "MCP descriptions do not match the exact tool surface",
                )
            )
        realization_text = (
            MODEL_ROOT / "vellis" / "realizations" / "VellisMcpPython.sysml"
        ).read_text(encoding="utf-8")
        binding_blocks = re.findall(r"@McpToolBinding\s*\{(.*?)\}", realization_text, re.DOTALL)
        description_symbols = set(
            re.findall(r'descriptionSymbol\s*=\s*"TOOL_DESCRIPTIONS\.([^"]+)"', realization_text)
        )
        if len(binding_blocks) != 27 or description_symbols != set(python_tools):
            findings.append(
                Finding(
                    MODEL_ROOT / "vellis" / "realizations" / "VellisMcpPython.sysml",
                    "each MCP realization must bind its exact description and mapping policy",
                )
            )
        for block in binding_blocks:
            if not re.search(r'resultMapping\s*=\s*"[^"]+"', block) or not re.search(
                r'errorMapping\s*=\s*"[^"]+"', block
            ):
                findings.append(
                    Finding(
                        MODEL_ROOT / "vellis" / "realizations" / "VellisMcpPython.sysml",
                        "MCP binding lacks result or error mapping",
                    )
                )
                break
        operation_ids = _model_operation_ids()
        if len(operation_ids) != 27 or len(set(operation_ids)) != 27:
            findings.append(
                Finding(
                    MODEL_ROOT / "vellis" / "VellisOperations.sysml",
                    f"expected 27 unique Vellis operation IDs, found {len(set(operation_ids))}",
                )
            )
        findings.extend(_check_vellis_contract_completeness())
        findings.extend(_check_contract_satisfaction())
        findings.extend(_check_vellis_use_cases())

    if scope == "all":
        findings.extend(_check_implementation_drift_file())

    if require_external:
        validator = _read_json(lock_path).get("validator", {})
        command = validator.get("command") if isinstance(validator, dict) else None
        if not command:
            findings.append(
                Finding(lock_path, "external formal validator is not pinned/configured")
            )
        else:
            result = subprocess.run(
                [str(part) for part in command],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode:
                findings.append(
                    Finding(lock_path, f"external validator failed: {result.stdout}{result.stderr}")
                )
    return findings


def _documentation(block: str) -> str:
    match = re.search(r"\bdoc\s*/\*(.*?)\*/", block, flags=re.DOTALL)
    if not match:
        return ""
    return " ".join(match.group(1).split())


def _feature_signature(block: str) -> str:
    features = re.findall(
        r"\b(in|out)\s+(?:ref\s+)?(?:part\s+|item\s+)?(\w+)(\[[^]]+\])?\s*:\s*([\w:]+)(\[[^]]+\])?(?:\s*=\s*([^;{}]+))?",
        block,
    )
    if not features:
        return "—"
    return "; ".join(
        f"{direction} `{name}: {type_name}{before or after or ''}`"
        + (f" = `{default.strip()}`" if default else "")
        for direction, name, before, type_name, after, default in features
    )


def _part_definition_chain(text: str, name: str, seen: set[str] | None = None) -> list[str]:
    seen = set() if seen is None else seen
    if name in seen:
        return []
    seen.add(name)
    match = re.search(rf"\bpart def\s+{re.escape(name)}(?:\s*:>\s*(\w+))?\s*\{{", text)
    if not match:
        return []
    parent = match.group(1)
    blocks = _part_definition_chain(text, parent, seen) if parent else []
    blocks.append(_extract_braced_block(text, match.start()))
    return blocks


def _public_field_signatures(
    text: str, name: str, seen: set[str] | None = None
) -> list[tuple[str, str, str, str]]:
    seen = set() if seen is None else seen
    if name in seen:
        return []
    seen.add(name)
    match = re.search(
        rf"\b(?:attribute|item) def\s+{re.escape(name)}"
        r"(?:\s*:>\s*(\w+))?\s*\{",
        text,
    )
    if not match:
        return []
    parent = match.group(1)
    fields = _public_field_signatures(text, parent, seen) if parent else []
    block = _extract_braced_block(text, match.start())
    fields.extend(
        re.findall(
            r"\b(?:ref\s+)?(?:attribute|item)\s+(\w+)(\[[^]]+\])?\s*:\s*([\w:]+)"
            r"(?:\s*=\s*([^;{}]+))?",
            block,
        )
    )
    return fields


def _component_page(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    component_id = _component_id(text) or path.stem
    component_name = _component_definition_name(text) or path.stem
    component_block = _definition_block(text, "part def", component_name)
    component_contract_blocks = _part_definition_chain(text, component_name)
    complete_component_contract = "\n".join(component_contract_blocks) or component_block
    status = _component_model_statuses().get(component_id, "unknown")
    purpose = _documentation(component_block) or "See the modeled contracts and invariants below."

    action_definitions = {
        match.group(1): _extract_braced_block(text, match.start())
        for match in re.finditer(r"\baction def\s+(\w+)\s*\{", text)
    }
    provided = re.findall(
        r"perform action\s+(\w+)\[[^]]+\]\s*:\s*(\w+)", complete_component_contract
    )
    required = re.findall(
        r"ref (action|part)\s+(\w+)(?:\[[^]]+\])?\s*:\s*(\w+)",
        complete_component_contract,
    )

    action_rows = [
        "| Feature | Contract | Signature | Principal failures | Meaning |",
        "|---|---|---|---|---|",
    ]
    for feature, action_type in provided:
        block = action_definitions.get(action_type, "")
        failures = re.search(r"errorIds\s*=\s*\((.*?)\)", block, flags=re.DOTALL)
        rendered_failures = (
            ", ".join(f"`{name}`" for name in re.findall(r'"([^"]+)"', failures.group(1))) or "None"
            if failures
            else "—"
        )
        action_rows.append(
            f"| `{feature}` | `{action_type}` | {_feature_signature(block)} | "
            f"{rendered_failures} | "
            f"{_documentation(block) or 'Defined by the named action contract.'} |"
        )
    if len(action_rows) == 2:
        action_rows.append("| — | — | — | — | No provided operations. |")

    provided_types = {action_type for _, action_type in provided}
    construction_rows = [
        "| Contract | Signature | Principal failures | Meaning |",
        "|---|---|---|---|",
    ]
    for action_type, block in action_definitions.items():
        if action_type in provided_types or not re.search(
            rf"\bout\s+(?:ref\s+)?part\s+\w+\s*:\s*{re.escape(component_name)}\b", block
        ):
            continue
        failures = re.search(r"errorIds\s*=\s*\((.*?)\)", block, flags=re.DOTALL)
        rendered_failures = (
            ", ".join(f"`{name}`" for name in re.findall(r'"([^"]+)"', failures.group(1))) or "None"
            if failures
            else "—"
        )
        construction_rows.append(
            f"| `{action_type}` | {_feature_signature(block)} | {rendered_failures} | "
            f"{_documentation(block) or 'Construct the component occurrence.'} |"
        )
    if len(construction_rows) == 2:
        construction_rows.append("| — | — | — | No package-level construction action. |")

    required_rows = ["| Feature | Kind | Required contract | Cardinality |", "|---|---|---|---|"]
    for kind, feature, contract in required:
        feature_match = re.search(
            rf"ref {kind}\s+{re.escape(feature)}(?:\[[^]]+\])?\s*:"
            rf"\s*{re.escape(contract)}\s*\{{(.*?)\}}",
            complete_component_contract,
            flags=re.DOTALL,
        )
        metadata = feature_match.group(1) if feature_match else ""
        lower = re.search(r"providerLowerBound\s*=\s*(\d+)", metadata)
        upper = re.search(r"providerUpperBound\s*=\s*(\d+)", metadata)
        cardinality = f"{lower.group(1)}..{upper.group(1)}" if lower and upper else "—"
        required_rows.append(f"| `{feature}` | `{kind}` | `{contract}` | `{cardinality}` |")
    if len(required_rows) == 2:
        required_rows.append("| — | — | — | No required capabilities. |")

    state_rows = [
        "| State feature | Type | Authority | Lifetime | Persistence |",
        "|---|---|---|---|---|",
    ]
    state_pattern = re.compile(
        r"(?m)^\s*(?:ref\s+)?(?:attribute|item|part)\s+(\w+)(?:\[[^]]+\])?\s*:\s*([\w:]+)\s*\{(.*?)\}",
        flags=re.DOTALL,
    )
    for match in state_pattern.finditer(complete_component_contract):
        metadata = match.group(3)
        if "@StateAuthority" not in metadata:
            continue
        values = {
            key: value
            for key, value in re.findall(
                r"(authority|lifetime|persistence)\s*=\s*\w+::(\w+)", metadata
            )
        }
        state_rows.append(
            f"| `{match.group(1)}` | `{match.group(2)}` | `{values.get('authority', '—')}` | "
            f"`{values.get('lifetime', '—')}` | `{values.get('persistence', '—')}` |"
        )
    if len(state_rows) == 2:
        state_rows.append("| — | — | — | — | This component owns no abstract state. |")

    effect_rows = [
        "| Action | State / capability | Access | Contract-significant effect |",
        "|---|---|---|---|",
    ]
    for match in re.finditer(
        r"dependency\s+\w+\s+from\s+(\w+)\s+to\s+([\w.]+)\s*\{(.*?)\}",
        complete_component_contract,
        flags=re.DOTALL,
    ):
        metadata = match.group(3)
        access = re.search(r"kind\s*=\s*StateAccessKind::(\w+)", metadata)
        capability_use = "@CapabilityUse" in metadata
        effect = re.search(r'effect\s*=\s*"([^"]+)"', metadata)
        if access or capability_use:
            effect_rows.append(
                f"| `{match.group(1)}` | `{match.group(2)}` | "
                f"`{access.group(1) if access else 'capability use'}` | "
                f"{effect.group(1) if effect else 'See the action-scoped requirement.'} |"
            )
    for feature, _ in provided:
        feature_match = re.search(
            rf"perform action\s+{re.escape(feature)}\[[^]]+\]\s*:\s*\w+\s*\{{",
            complete_component_contract,
        )
        if not feature_match:
            continue
        metadata = _extract_braced_block(complete_component_contract, feature_match.start())
        access = re.search(r"kind\s*=\s*StateAccessKind::(\w+)", metadata)
        effect = re.search(r'effect\s*=\s*"([^"]+)"', metadata)
        if access and not any(f"| `{feature}` |" in row for row in effect_rows):
            effect_rows.append(
                f"| `{feature}` | — | `{access.group(1)}` | "
                f"{effect.group(1) if effect else 'See the action-scoped requirement.'} |"
            )
    if len(effect_rows) == 2:
        effect_rows.append("| — | — | — | Effects are stated by the requirements below. |")

    requirement_rows = ["| Stable ID | Modeled obligation |", "|---|---|"]
    for match in re.finditer(r"\brequirement\s+\w+\s*\{", text):
        block = _extract_braced_block(text, match.start())
        stable_id = re.search(r'@StableId\s*\{[^}]*id\s*=\s*"([^"]+)"', block, re.DOTALL)
        if stable_id:
            requirement_rows.append(
                f"| `{stable_id.group(1)}` | {_documentation(block) or 'Modeled requirement.'} |"
            )
    if len(requirement_rows) == 2:
        requirement_rows.append("| — | No component-scoped requirements. |")

    value_rows = [
        "| Public definition | Kind | Fields | Meaning |",
        "|---|---|---|---|",
    ]
    for match in re.finditer(r"\b(attribute|item) def\s+(\w+)(?:\s*:>\s*\w+)?\s*\{", text):
        definition_block = _extract_braced_block(text, match.start())
        fields = _public_field_signatures(text, match.group(2))
        rendered_fields = (
            ", ".join(
                f"`{name}{multiplicity}: {type_name}`"
                + (f" = `{default.strip()}`" if default else "")
                for name, multiplicity, type_name, default in fields
            )
            or "—"
        )
        meaning = _documentation(definition_block) or (
            "Defined by its typed fields and action requirements."
        )
        value_rows.append(
            f"| `{match.group(2)}` | `{match.group(1)}` | {rendered_fields} | "
            f"{meaning} |"
        )
    if len(value_rows) == 2:
        value_rows.append("| — | — | — | No component-owned public values. |")

    enum_rows = ["| Enumeration | Model and external values |", "|---|---|"]
    for match in re.finditer(r"\benum def\s+(\w+)\s*\{", text):
        block = _extract_braced_block(text, match.start())
        rendered_values: list[str] = []
        for value_match in re.finditer(r"\benum\s+(\w+)\s*(;|\{)", block):
            model_name = value_match.group(1)
            external_name = "_".join(_words(model_name))
            if value_match.group(2) == "{":
                value_block = _extract_braced_block(block, value_match.start())
                override = re.search(r'@ExternalName\s*\{[^}]*name\s*=\s*"([^"]+)"', value_block)
                if override:
                    external_name = override.group(1)
            rendered_value = (
                f"`{model_name}`"
                if model_name == external_name
                else f"`{model_name}` → `{external_name}`"
            )
            rendered_values.append(rendered_value)
        enum_rows.append(
            f"| `{match.group(1)}` | {', '.join(rendered_values) or '—'} |"
        )
    if len(enum_rows) == 2:
        enum_rows.append("| — | No component-owned public enumerations. |")

    verification_rows = [
        "| Verification | Objectives | Evidence |",
        "|---|---|---|",
    ]
    for match in re.finditer(r"\bverification def\s+(\w+)\s*\{", text):
        block = _extract_braced_block(text, match.start())
        objectives = re.findall(r"\bverify\s+(\w+)\s*;", block)
        evidence = re.search(r'evidenceId\s*=\s*"([^"]+)"', block)
        verification_rows.append(
            f"| `{match.group(1)}` | {', '.join(f'`{name}`' for name in objectives) or '—'} | "
            f"`{evidence.group(1)}` |"
            if evidence
            else (
                f"| `{match.group(1)}` | "
                f"{', '.join(f'`{name}`' for name in objectives) or '—'} | — |"
            )
        )
    if len(verification_rows) == 2:
        verification_rows.append("| — | — | No boundary verification modeled. |")

    return "\n".join(
        [
            f"# {component_id}",
            "",
            "Generated from textual SysML v2 by `just model-render`; do not edit by hand.",
            "",
            f"- Model definition: `{component_name}`",
            f"- Lifecycle: `{status}`",
            f"- Purpose: {purpose}",
            "",
            "## Provided actions",
            "",
            *action_rows,
            "",
            "## Construction actions",
            "",
            *construction_rows,
            "",
            "## Required capabilities",
            "",
            *required_rows,
            "",
            "## Owned state",
            "",
            *state_rows,
            "",
            "## Action and state effects",
            "",
            *effect_rows,
            "",
            "## Invariants and behavioral obligations",
            "",
            *requirement_rows,
            "",
            "## Public values and items",
            "",
            *value_rows,
            "",
            "## Public enumerations",
            "",
            *enum_rows,
            "",
            "## Verification",
            "",
            *verification_rows,
            "",
            "Equivalent private algorithms, helpers, storage layouts, and "
            "implementation-language inheritance remain implementation choices.",
            "",
        ]
    )


def _component_pages() -> dict[Path, str]:
    return {
        GENERATED_COMPONENT_DOC_ROOT / f"{component_id}.md": _component_page(path)
        for path in sorted(COMPONENT_MODEL_ROOT.glob("component.*.sysml"))
        if (component_id := _component_id(path.read_text(encoding="utf-8")))
    }


def _render_component_summary() -> str:
    statuses = _component_model_statuses()
    rows = ["| Component | Status | Generated view |", "|---|---|---|"]
    for component_id, status in sorted(statuses.items()):
        rows.append(
            f"| `{component_id}` | `{status}` | [component view](components/{component_id}.md) |"
        )
    return "\n".join(
        [
            "# Bibliotek component model",
            "",
            "Generated by `just model-render`; do not edit by hand.",
            "",
            *rows,
            "",
        ]
    )


def _render_operation_summary() -> str:
    operation_text = (MODEL_ROOT / "vellis" / "VellisOperations.sysml").read_text(encoding="utf-8")
    operation_blocks: dict[str, str] = {}
    for match in re.finditer(r"\baction def\s+(\w+)\s*\{", operation_text):
        block = _extract_braced_block(operation_text, match.start())
        identity = re.search(r'id\s*=\s*"operation\.vellis\.([^"]+)"', block)
        if identity:
            operation_blocks[identity.group(1)] = block
    rows = [
        "| # | Vellis façade / MCP tool | Signature | Principal failures | Outcome |",
        "|---:|---|---|---|---|",
    ]
    for index, tool in enumerate(_model_tool_names(), 1):
        block = operation_blocks.get(tool, "")
        failure = re.search(r"errorIds\s*=\s*\((.*?)\)", block, flags=re.DOTALL)
        failures = (
            ", ".join(f"`{name}`" for name in re.findall(r'"([^"]+)"', failure.group(1)))
            if failure
            else "—"
        )
        rows.append(
            f"| {index} | `{tool}` | {_feature_signature(block)} | {failures or 'None'} | "
            f"{_documentation(block) or 'See the typed façade action.'} |"
        )
    role_rows = ["| Application role | Bibliotek component |", "|---|---|"]
    role_rows.extend(
        f"| `{role}` | `{component_id}` |" for role, component_id in _vellis_roles().items()
    )
    use_case_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((MODEL_ROOT / "vellis" / "use-cases").glob("*.sysml"))
    )
    use_cases = sorted(set(re.findall(r"\buse case def\s+(\w+)", use_case_text)))
    use_case_rows = ["| Actor-visible use case |", "|---|"]
    use_case_rows.extend(f"| `{name}` |" for name in use_cases)
    return "\n".join(
        [
            "# Vellis operations",
            "",
            "Generated by `just model-render`; do not edit by hand.",
            "",
            "## Application composition",
            "",
            *role_rows,
            "",
            "## Actor-visible use cases",
            "",
            *use_case_rows,
            "",
            "## Façade and transport mappings",
            "",
            "Successful MCP calls encode as `{ok: true, result: <encoded action result>}`. "
            "Failures encode as `{ok: false, error: {type, message, diagnostic?}}`; controller "
            "validation failures also expose `transaction_id` and `validation_report` when "
            "present.",
            "",
            *rows,
            "",
        ]
    )


def _manifest_data() -> dict[str, Any]:
    operation_blocks = _model_operation_blocks()
    operation_parameters = _model_tool_parameters()
    return {
        "app_name": "rtg_knowledge_graph",
        "schema_version": 1,
        "component_dependencies": [
            {"id": _vellis_roles()[role], "role": RUNTIME_ROLE_NAMES[role]}
            for role in RUNTIME_MANIFEST_ROLE_ORDER
        ],
        "tools": [
            {
                "name": tool,
                "operation_id": f"operation.vellis.{tool}",
                "description": _documentation(operation_blocks[tool]),
                "parameters": [
                    {
                        "name": name,
                        "required": not optional,
                        **({"default": default} if optional and default is not None else {}),
                    }
                    for name, optional, default in operation_parameters[tool]
                ],
                "transports": ["stdio", "http"],
                "success_envelope": {"ok": True, "result": "<encoded action result>"},
                "failure_envelope": {
                    "ok": False,
                    "error": {"type": "<failure type>", "message": "<message>"},
                    "optional": ["error.diagnostic", "transaction_id", "validation_report"],
                },
            }
            for tool in _model_tool_names()
        ],
    }


def render() -> None:
    GENERATED_DOC_ROOT.mkdir(parents=True, exist_ok=True)
    GENERATED_COMPONENT_DOC_ROOT.mkdir(parents=True, exist_ok=True)
    GENERATED_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    component_pages = _component_pages()
    for stale in GENERATED_COMPONENT_DOC_ROOT.glob("*.md"):
        if stale not in component_pages:
            stale.unlink()
    for path, content in component_pages.items():
        path.write_text(content, encoding="utf-8")
    (GENERATED_DOC_ROOT / "bibliotek-components.md").write_text(
        _render_component_summary(), encoding="utf-8"
    )
    (GENERATED_DOC_ROOT / "vellis-operations.md").write_text(
        _render_operation_summary(), encoding="utf-8"
    )
    GENERATED_MANIFEST.write_text(
        json.dumps(_manifest_data(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def check_generated() -> list[Finding]:
    expected = {
        **_component_pages(),
        GENERATED_DOC_ROOT / "bibliotek-components.md": _render_component_summary(),
        GENERATED_DOC_ROOT / "vellis-operations.md": _render_operation_summary(),
        GENERATED_MANIFEST: json.dumps(_manifest_data(), indent=2, sort_keys=True) + "\n",
    }
    findings = [
        Finding(path, "generated artifact is missing or stale; run just model-render")
        for path, content in expected.items()
        if not path.exists() or path.read_text(encoding="utf-8") != content
    ]
    expected_component_paths = {
        path for path in expected if path.parent == GENERATED_COMPONENT_DOC_ROOT
    }
    for path in GENERATED_COMPONENT_DOC_ROOT.glob("*.md"):
        if path not in expected_component_paths:
            findings.append(Finding(path, "stale generated component page; run just model-render"))
    return findings


def package_models() -> None:
    destination = MODEL_ROOT / "dist"
    destination.mkdir(parents=True, exist_ok=True)
    packages = {
        "software-component-modeling-foundation-0.1.0.kpar": [MODEL_ROOT / "foundation"],
        "bibliotek-0.1.0.kpar": [MODEL_ROOT / "bibliotek"],
        "vellis-0.1.0.kpar": [MODEL_ROOT / "vellis"],
    }
    for name, roots in packages.items():
        source_files = sorted(path for root in roots for path in root.rglob("*.sysml"))
        index = {path.stem: path.name for path in source_files}
        if name.startswith("software-component"):
            usage: list[dict[str, str]] = [
                {
                    "resource": "https://www.omg.org/spec/SysML/20250201/Systems-Library.kpar",
                    "versionConstraint": "2.0.0",
                },
                {
                    "resource": "https://www.omg.org/spec/KerML/20250201/Semantic-Library.kpar",
                    "versionConstraint": "1.0.0",
                },
                {
                    "resource": "https://www.omg.org/spec/KerML/20250201/Data-Type-Library.kpar",
                    "versionConstraint": "1.0.0",
                },
                {
                    "resource": "https://www.omg.org/spec/KerML/20250201/Function-Library.kpar",
                    "versionConstraint": "1.0.0",
                },
            ]
        elif name.startswith("bibliotek"):
            usage = [
                {
                    "resource": "software-component-modeling-foundation-0.1.0.kpar",
                    "versionConstraint": "0.1.0-shadow",
                }
            ]
        else:
            usage = [
                {
                    "resource": "software-component-modeling-foundation-0.1.0.kpar",
                    "versionConstraint": "0.1.0-shadow",
                },
                {"resource": "bibliotek-0.1.0.kpar", "versionConstraint": "0.1.0-shadow"},
            ]
        project = {
            "name": name.removesuffix("-0.1.0.kpar"),
            "description": "Vellis textual SysML source package",
            "version": "0.1.0-shadow",
            "usage": usage,
        }
        checksums = {
            path.name: {
                "value": hashlib.sha256(path.read_bytes()).hexdigest(),
                "algorithm": "SHA256",
            }
            for path in source_files
        }
        metadata = {
            "index": index,
            "created": "2026-07-10T00:00:00Z",
            "metamodel": "https://www.omg.org/spec/SysML/20250201",
            "checksum": checksums,
            "status": "shadow-candidate-external-validation-pending",
        }
        archive_root = project["name"].replace("-", " ").title()
        with zipfile.ZipFile(destination / name, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"{archive_root}/.project.json", json.dumps(project, sort_keys=True))
            archive.writestr(f"{archive_root}/.meta.json", json.dumps(metadata, sort_keys=True))
            for path in source_files:
                archive.write(path, f"{archive_root}/{path.name}")


def handoff(target: str) -> int:
    identity_matches: list[Path] = []
    reference_matches: list[Path] = []
    for path in _sysml_files("all"):
        text = path.read_text(encoding="utf-8")
        if re.search(rf'@SpecIdentity\s*\{{[^}}]*id\s*=\s*"{re.escape(target)}"', text):
            identity_matches.append(path)
        elif target in text:
            reference_matches.append(path)
    matches = identity_matches or reference_matches
    if not matches:
        print(f"No model element found for {target}", file=sys.stderr)
        return 1
    status = _read_json(MODEL_ROOT / "model-status.json")
    print(f"Target: {target}")
    print(f"Model phase: {status.get('phase')}")
    print("Inputs:")
    print("- model/foundation/SoftwareComponentModeling.sysml")
    for path in matches:
        print(f"- {path.relative_to(ROOT)}")
    print("Implementation input: accepted SysML/KPAR, generated view, and verification objectives.")
    print("Verification: derive black-box evidence from the target model's verification cases.")
    print(
        "Freedom: private helpers, algorithms, storage layouts, and language inheritance are open."
    )
    return 0


def setup_status() -> int:
    lock = _read_json(MODEL_ROOT / "model.lock.json")
    language = lock.get("language", {})
    assert isinstance(language, dict)
    print(f"Language baseline: SysML {language.get('sysml')} / KerML {language.get('kerml')}")
    libraries = lock.get("libraries", {})
    grammar = lock.get("grammar", {})
    artifacts: list[tuple[str, dict[str, Any]]] = []
    if isinstance(libraries, dict):
        for artifact in libraries.get("artifacts", []):
            if isinstance(artifact, dict):
                artifacts.append((str(artifact.get("id")), artifact))
    if isinstance(grammar, dict):
        artifacts.extend(
            (artifact_id, artifact)
            for artifact_id, artifact in grammar.items()
            if isinstance(artifact, dict)
        )
    cache = MODEL_ROOT / ".cache" / "formal"
    cache.mkdir(parents=True, exist_ok=True)
    for artifact_id, artifact in artifacts:
        url = str(artifact["url"])
        expected = str(artifact["sha256"])
        suffix = ".kpar" if url.endswith(".kpar") else ".pdf"
        destination = cache / f"{artifact_id}{suffix}"
        if (
            not destination.exists()
            or hashlib.sha256(destination.read_bytes()).hexdigest() != expected
        ):
            with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
                destination.write_bytes(response.read())
        actual = hashlib.sha256(destination.read_bytes()).hexdigest()
        if actual != expected:
            print(f"Checksum mismatch for {artifact_id}", file=sys.stderr)
            return 1
        print(f"Pinned artifact verified: {artifact_id}")

    validator = lock.get("validator", {})
    command = validator.get("command") if isinstance(validator, dict) else None
    if command:
        print(f"External validator: {' '.join(str(part) for part in command)}")
    else:
        print("External validator: pending; profile checks remain available")
    print("Run `just model-check` for repository profile checks.")
    print("Run `uv run python tools/model_tool.py check --require-external` for the formal gate.")
    return 0


def _report(findings: list[Finding]) -> int:
    if findings:
        for finding in findings:
            print(f"ERROR {finding.render()}")
        print(f"Model check failed with {len(findings)} finding(s).")
        return 1
    print("Model check passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and derive repository SysML artifacts")
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument(
        "--scope", choices=("foundation", "bibliotek", "vellis", "all"), default="all"
    )
    check_parser.add_argument("--require-external", action="store_true")
    subparsers.add_parser("check-generated")
    subparsers.add_parser("render")
    subparsers.add_parser("package")
    subparsers.add_parser("setup")
    handoff_parser = subparsers.add_parser("handoff")
    handoff_parser.add_argument("target")
    subparsers.add_parser("diff")
    args = parser.parse_args()

    if args.command == "check":
        return _report(check(args.scope, require_external=args.require_external))
    if args.command == "check-generated":
        return _report(check_generated())
    if args.command == "render":
        render()
        print("Rendered generated model views and application manifest.")
        return 0
    if args.command == "package":
        package_models()
        print("Packaged shadow KPAR candidates under model/dist/.")
        return 0
    if args.command == "setup":
        return setup_status()
    if args.command == "handoff":
        return handoff(args.target)
    result = subprocess.run(["git", "diff", "--", "model", "docs/model"], cwd=ROOT, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
