from __future__ import annotations

import argparse
import ast
import functools
import hashlib
import json
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

try:
    from .sysml_diagrams import DiagramSpec, discover_diagrams
except ImportError:  # pragma: no cover - direct script execution
    from sysml_diagrams import DiagramSpec, discover_diagrams  # type: ignore[no-redef]

try:
    from .model_layout import (
        ALLOWED_CONSTRUCTS_PATH,
        BIBLIOTEK_COMPONENT_REFERENCE_ROOT,
        BIBLIOTEK_MODEL_ROOT,
        BIBLIOTEK_REFERENCE_ROOT,
        COMPONENT_MODEL_ROOT,
        FORMAL_CACHE_ROOT,
        GENERATED_CONFORMANCE_OBJECTIVES,
        GENERATED_EVIDENCE_INDEX,
        GENERATED_FORMAL_INDEX,
        GENERATED_MANIFEST,
        GENERATED_STARTER_SCHEMA,
        LANGUAGE_LOCK_PATH,
        MODEL_PACKAGE_ROOT,
        MODEL_ROOT,
        ROOT,
        VELLIS_REFERENCE_ROOT,
    )
except ImportError:  # pragma: no cover - direct script execution
    from model_layout import (  # type: ignore[no-redef]
        ALLOWED_CONSTRUCTS_PATH,
        BIBLIOTEK_COMPONENT_REFERENCE_ROOT,
        BIBLIOTEK_MODEL_ROOT,
        BIBLIOTEK_REFERENCE_ROOT,
        COMPONENT_MODEL_ROOT,
        FORMAL_CACHE_ROOT,
        GENERATED_CONFORMANCE_OBJECTIVES,
        GENERATED_EVIDENCE_INDEX,
        GENERATED_FORMAL_INDEX,
        GENERATED_MANIFEST,
        GENERATED_STARTER_SCHEMA,
        LANGUAGE_LOCK_PATH,
        MODEL_PACKAGE_ROOT,
        MODEL_ROOT,
        ROOT,
        VELLIS_REFERENCE_ROOT,
    )

GENERATED_COMPONENT_DOC_ROOT = BIBLIOTEK_COMPONENT_REFERENCE_ROOT
OPTIONAL_IDENTIFICATION = r"(?:<'[^']+'>\s+)?"
SYSML_IDENTIFIER = r"(?:[A-Za-z_]\w*|'[^']+')"
SYSML_QUALIFIED_IDENTIFIER = rf"{SYSML_IDENTIFIER}(?:\.{SYSML_IDENTIFIER})*"

EXPECTED_VELLIS_ROLES: dict[str, str] = {
    "runtime": "component.runtime.message_runtime",
    "documentStorage": "component.storage.json_file",
    "graphStore": "component.rtg.graph",
    "schemaRegistry": "component.rtg.schema",
    "constraintRegistry": "component.rtg.constraints",
    "migrationStore": "component.rtg.migration",
    "queryEngine": "component.rtg.query",
    "changeValidator": "component.rtg.change_validation",
    "controller": "component.rtg.controller",
}

STATE_TRANSFER_METHODS = {"export_snapshot", "import_snapshot", "replace_snapshot"}
STATE_TRANSFER_ALLOWLIST: dict[str, frozenset[str]] = {
    "components/rtg/graph/implementation.py": frozenset(
        {"import_snapshot", "export_snapshot", "replace_snapshot"}
    ),
    "components/rtg/schema/implementation.py": frozenset(
        {"import_snapshot", "export_snapshot", "replace_snapshot"}
    ),
    "components/rtg/constraints/implementation.py": frozenset(
        {"import_snapshot", "export_snapshot", "replace_snapshot"}
    ),
    "components/rtg/migration/implementation.py": frozenset(
        {"import_snapshot", "export_snapshot", "replace_snapshot"}
    ),
    "components/rtg/controller/coordinator.py": frozenset(
        {"_snapshot", "_replace_snapshot", "_restore", "_persist_snapshot"}
    ),
    "components/rtg/graph/runtime_binding.py": frozenset({"create_rtg_graph_adapter"}),
    "apps/rtg_knowledge_graph/composition.py": frozenset(
        {"_state_replay_binding", "export_state", "replace_state"}
    ),
}

RUNTIME_ROLE_NAMES: dict[str, str] = {
    "runtime": "message_runtime",
    "documentStorage": "document_storage",
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
    return sorted(
        path
        for root in roots
        for path in root.rglob("*.sysml")
        if ".cache" not in path.relative_to(MODEL_ROOT).parts
    )


def _identifier_value(identifier: str) -> str:
    if identifier.startswith("'") and identifier.endswith("'"):
        return identifier[1:-1]
    return identifier


def _identifier_pattern(identifier: str) -> str:
    return rf"(?:{re.escape(identifier)}|'{re.escape(identifier)}')"


def _satisfier_map(text: str) -> dict[str, str]:
    """Project requirement satisfiers while preserving quoted SysML names."""

    satisfiers: dict[str, str] = {}
    for requirement, target in re.findall(
        rf"\bsatisfy\s+(\w+)\s+by\s+({SYSML_QUALIFIED_IDENTIFIER})\s*;",
        text,
    ):
        satisfiers[requirement] = ".".join(
            _identifier_value(segment) for segment in re.findall(SYSML_IDENTIFIER, target)
        )
    return satisfiers


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
        identity = re.search(r"\bpart def\s+<'(component\.[^']+)'>", text)
        status = re.search(
            r"@SpecificationStatus\s*\{[^}]*lifecycleStatus\s*=\s*SpecLifecycle::(\w+);",
            text,
            flags=re.DOTALL,
        )
        if identity and status:
            statuses[identity.group(1)] = status.group(1)
    return statuses


def _extract_braced_block(text: str, start: int) -> str:
    brace = text.find("{", start)
    semicolon = text.find(";", start)
    if brace < 0 or (semicolon >= 0 and semicolon < brace):
        return text[start : semicolon + 1 if semicolon >= 0 else len(text)]
    depth = 0
    in_comment = False
    in_string = False
    escaped = False
    index = brace
    while index < len(text):
        if in_comment:
            if text.startswith("*/", index):
                in_comment = False
                index += 2
                continue
            index += 1
            continue
        if in_string:
            if escaped:
                escaped = False
            elif text[index] == "\\":
                escaped = True
            elif text[index] == '"':
                in_string = False
            index += 1
            continue
        if text.startswith("/*", index):
            in_comment = True
            index += 2
            continue
        if text[index] == '"':
            in_string = True
        elif text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
        index += 1
    return text[start:]


def _definition_block(text: str, kind: str, name: str) -> str:
    match = re.search(
        rf"\b{re.escape(kind)}\s+(?:def\s+)?{OPTIONAL_IDENTIFICATION}{re.escape(name)}\b",
        text,
    )
    return _extract_braced_block(text, match.start()) if match else ""


def _component_definition_name(text: str) -> str | None:
    match = re.search(
        r"\bpart def\s+<'component\.[^']+'>\s+(\w+)(?:\s*:>\s*\w+)?\s*\{",
        text,
    )
    return match.group(1) if match else None


def _component_id(text: str) -> str | None:
    match = re.search(r"\bpart def\s+<'(component\.[^']+)'>", text)
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
        actions = set(re.findall(rf"\baction def\s+{OPTIONAL_IDENTIFICATION}(\w+)", text))
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


def _protocol_defaulted_parameters(component_id: str) -> dict[str, set[str]]:
    code_root = ROOT / "components" / Path(*component_id.removeprefix("component.").split("."))
    protocol_path = code_root / "protocol.py"
    if not protocol_path.exists():
        return {}
    tree = ast.parse(protocol_path.read_text(encoding="utf-8"))
    result: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or not any(
            (isinstance(base, ast.Name) and base.id == "Protocol")
            or (isinstance(base, ast.Attribute) and base.attr == "Protocol")
            for base in node.bases
        ):
            continue
        for member in node.body:
            if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            positional = [*member.args.posonlyargs, *member.args.args]
            default_start = len(positional) - len(member.args.defaults)
            defaulted = {
                argument.arg
                for index, argument in enumerate(positional)
                if index >= default_start and argument.arg not in {"self", "cls"}
            }
            defaulted.update(
                argument.arg
                for argument, default in zip(
                    member.args.kwonlyargs, member.args.kw_defaults, strict=True
                )
                if default is not None
            )
            result[member.name] = defaulted
    return result


def _check_protocol_action_signatures() -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(COMPONENT_MODEL_ROOT.glob("component.*.sysml")):
        text = path.read_text(encoding="utf-8")
        component_id = _component_id(text)
        if not component_id or component_id == "component.rtg.discovery":
            continue
        action_blocks = {
            match.group(1): _extract_braced_block(text, match.start())
            for match in re.finditer(rf"\baction def\s+{OPTIONAL_IDENTIFICATION}(\w+)\s*\{{", text)
        }
        actions = set(action_blocks)
        defaulted_parameters = _protocol_defaulted_parameters(component_id)
        for method, protocol_parameters in _protocol_method_parameters(component_id).items():
            action = _model_action_for_method(component_id, method, actions)
            if not action:
                continue
            model_parameters = tuple(
                _identifier_value(name)
                for name in re.findall(
                    rf"\bin\s+(?:ref\s+)?(?:attribute\s+|part\s+|item\s+)?"
                    rf"({SYSML_IDENTIFIER})(?:\[[^]]+\])?"
                    rf"(?:\s+(?:ordered|nonunique))*\s*:",
                    action_blocks[action],
                )
            )
            normalized_protocol = tuple(_normalized_name(name) for name in protocol_parameters)
            normalized_model = tuple(_normalized_name(name) for name in model_parameters)
            if normalized_protocol != normalized_model:
                findings.append(
                    Finding(
                        path,
                        f"{method}/{action} input names or order differ: "
                        f"protocol={protocol_parameters}, model={model_parameters}",
                    )
                )
            model_declarations: dict[str, tuple[str, str]] = {}
            for declaration in re.findall(r"\bin\s+[^;{}]+;", action_blocks[action]):
                declaration_match = re.search(
                    rf"\bin\s+(?:ref\s+)?(?:attribute\s+|part\s+|item\s+)?"
                    rf"({SYSML_IDENTIFIER})(\[[^]]+\])?",
                    declaration,
                )
                if declaration_match is None:
                    continue
                name, multiplicity = declaration_match.groups()
                model_declarations[_normalized_name(_identifier_value(name))] = (
                    multiplicity or "",
                    declaration,
                )
            for parameter in defaulted_parameters.get(method, set()):
                model_contract = model_declarations.get(_normalized_name(parameter))
                if model_contract is None:
                    continue
                multiplicity, declaration = model_contract
                if not multiplicity.startswith("[0..") and not re.search(
                    r"\s(?:default\s*)?=\s*", declaration
                ):
                    findings.append(
                        Finding(
                            path,
                            f"{method}/{action} omits modeled optionality or a default for "
                            f"Python-defaulted input {parameter}",
                        )
                    )
        code_root = ROOT / "components" / Path(*component_id.removeprefix("component.").split("."))
        tree = ast.parse((code_root / "protocol.py").read_text(encoding="utf-8"))
        protocol_returns: dict[str, str | None] = {}
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or not any(
                (isinstance(base, ast.Name) and base.id == "Protocol")
                or (isinstance(base, ast.Attribute) and base.attr == "Protocol")
                for base in node.bases
            ):
                continue
            for member in node.body:
                if isinstance(
                    member, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and not member.name.startswith("_"):
                    protocol_returns[member.name] = (
                        ast.unparse(member.returns) if member.returns is not None else None
                    )
        for method, return_type in protocol_returns.items():
            action = _model_action_for_method(component_id, method, actions)
            if not action:
                continue
            model_outputs = re.findall(
                rf"\bout\s+(?:ref\s+)?(?:attribute\s+|part\s+|item\s+)?"
                rf"{SYSML_IDENTIFIER}(?:\[[^]]+\])?\s*:\s*([\w:]+)",
                action_blocks[action],
            )
            normalized_return_types = {
                "str": "String",
                "int": "Integer",
                "float": "Real",
                "bool": "Boolean",
                "tuple[str, ...]": "String",
            }
            if return_type is None or return_type == "None":
                expected_outputs: tuple[str, ...] = ()
            else:
                normalized_protocol_return = re.sub(r"\s*\|\s*None$", "", return_type)
                repeated_return = re.fullmatch(
                    r"tuple\[([^,]+), \.\.\.\]", normalized_protocol_return
                )
                normalized_return = normalized_return_types.get(normalized_protocol_return)
                if normalized_return is None:
                    normalized_return = (
                        repeated_return.group(1)
                        if repeated_return is not None
                        else normalized_protocol_return
                    )
                expected_outputs = (normalized_return,)
            if tuple(model_outputs) != expected_outputs:
                findings.append(
                    Finding(
                        path,
                        f"{method}/{action} return contract differs: "
                        f"protocol={return_type}, model={tuple(model_outputs)}",
                    )
                )
    return findings


def _check_protocol_value_fields() -> list[Finding]:
    """Require every Python boundary record field to exist in its logical model value."""
    findings: list[Finding] = []
    all_model_text = "\n".join(path.read_text(encoding="utf-8") for path in _sysml_files("all"))
    modeled_values = set(
        re.findall(
            rf"\b(?:attribute|item) def\s+{OPTIONAL_IDENTIFICATION}(\w+)",
            all_model_text,
        )
    )
    boundary_paths = list((ROOT / "components").glob("**/protocol.py"))
    boundary_paths.append(ROOT / "components" / "rtg" / "diagnostics.py")
    for protocol_path in sorted(boundary_paths):
        tree = ast.parse(protocol_path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or node.name.startswith("_"):
                continue
            fields = {
                _normalized_name(member.target.id)
                for member in node.body
                if isinstance(member, ast.AnnAssign) and isinstance(member.target, ast.Name)
            }
            if not fields:
                continue
            if node.name not in modeled_values:
                findings.append(
                    Finding(
                        protocol_path,
                        f"public boundary value lacks model definition: {node.name}",
                    )
                )
                continue
            missing = sorted(fields - _modeled_public_fields(all_model_text, node.name))
            if missing:
                findings.append(
                    Finding(protocol_path, f"{node.name} has unmodeled public fields: {missing}")
                )
    return findings


def _check_empty_public_definitions(files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    pattern = re.compile(
        rf"(?m)^\s*(?:attribute|item|part|action|state|calc|constraint) def\s+"
        rf"{OPTIONAL_IDENTIFICATION}(\w+)\s*;"
    )
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            findings.append(Finding(path, f"unexplained empty public definition {match.group(1)}"))
        braced = re.compile(
            rf"(?m)^\s*(?!abstract\b)(attribute|item|part|action|calc|constraint) def\s+"
            rf"{OPTIONAL_IDENTIFICATION}(\w+)\b(?!\s*:>)\s*\{{"
        )
        for match in braced.finditer(text):
            block = _extract_braced_block(text, match.start())
            if match.group(1) == "part" and "@ImplementationBinding" in block:
                continue
            if match.group(1) == "action" and "@FailureContract" in block:
                # A parameterless command remains a concrete public action when its
                # observable semantics and failure family are explicitly contracted.
                continue
            body = _without_comments(block)
            body = body[body.find("{") + 1 : body.rfind("}")]
            body = re.sub(r"@\w+\s*\{.*?\}", "", body, flags=re.DOTALL)
            body = re.sub(r"\bdoc\b", "", body).strip()
            if not body:
                findings.append(
                    Finding(
                        path,
                        f"concrete public definition has only documentation: {match.group(2)}",
                    )
                )
    return findings


def _check_native_modeling_style(files: list[Path]) -> list[Finding]:
    """Reject project-profile patterns that duplicate or misuse native SysML semantics."""
    findings: list[Finding] = []
    foundation = MODEL_ROOT / "foundation" / "SoftwareComponentModeling.sysml"
    for path in files:
        text = path.read_text(encoding="utf-8")
        if re.search(
            r"\b(?:ContractKind|RequiredCapability|ContractSatisfaction|CapabilityUse|"
            r"StateAuthority|DependencyPolicy|StableId|ExternalName)\b|"
            r"@(?:ContractRole|SpecIdentity)\b",
            text,
        ):
            findings.append(
                Finding(
                    path,
                    "project metadata duplicates native SysML identity, role, dependency, or "
                    "feature semantics",
                )
            )
        if path.parent == COMPONENT_MODEL_ROOT and "@ImplementationBinding" in text:
            findings.append(
                Finding(path, "logical component definitions must not contain realization bindings")
            )
        if re.search(r"\battribute\s+diagnostic(?:\[[^]]+\])?\s*:\s*JsonObject\b", text):
            findings.append(
                Finding(path, "public diagnostics must use the shared typed diagnostic value")
            )
        if re.search(r"\benum\s+<'[^']+'>", text):
            findings.append(
                Finding(
                    path,
                    "enum short names must not serve as implicit external serialization mappings",
                )
            )
        for match in re.finditer(r"\b(calc|constraint) def\s+(?:<'[^']+'>\s+)?(\w+)\s*\{", text):
            block = _extract_braced_block(text, match.start())
            expression_body = _without_comments(block)
            expression_body = expression_body[expression_body.find("{") + 1 :]
            expression_body = expression_body.rsplit("}", 1)[0]
            expression_body = re.sub(r"\b(?:in|out)\s+[^;{}]+;", "", expression_body)
            expression_body = re.sub(r"\breturn\s+[^;={}]+;", "", expression_body)
            expression_body = re.sub(r"\bdoc\b\s*;?", "", expression_body)
            expression_body = re.sub(r"@\w+\s*\{.*?\}", "", expression_body, flags=re.DOTALL)
            has_result = bool(expression_body.strip())
            if not has_result:
                findings.append(
                    Finding(
                        path,
                        f"{match.group(1)} definition {match.group(2)} has no evaluable result",
                    )
                )
    if foundation in files:
        foundation_text = foundation.read_text(encoding="utf-8")
        if re.search(r"\bMcp\w*\b|\bTransportKind\b", foundation_text):
            findings.append(
                Finding(foundation, "application/transport vocabulary leaked into the foundation")
            )
    all_text = "\n".join(path.read_text(encoding="utf-8") for path in files)
    for kind, name in (
        ("attribute", "JsonValue"),
        ("attribute", "JsonScalar"),
        ("attribute", "SqlOperationResult"),
        ("item", "RtgObject"),
        ("attribute", "RtgSchemaPayload"),
        ("attribute", "RtgConstraintPayload"),
        ("attribute", "VellisQueryResponse"),
        ("attribute", "VellisSnapshotExport"),
        ("part", "VellisUser"),
    ):
        if re.search(rf"\b{kind} def\s+{name}\b", all_text) and not re.search(
            rf"\babstract\s+{kind} def\s+{name}\b", all_text
        ):
            findings.append(Finding(MODEL_ROOT, f"specialization base {name} must be abstract"))
    return findings


def _check_connected_formal_semantics(files: list[Path]) -> list[Finding]:
    """Reject evaluable definitions that are never connected to a contract or another rule."""
    findings: list[Finding] = []
    all_text = "\n".join(path.read_text(encoding="utf-8") for path in files)
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\b(calc|constraint) def\s+(?:<'[^']+'>\s+)?(\w+)\s*\{", text):
            kind, name = match.groups()
            if len(re.findall(rf"\b{re.escape(name)}\b", all_text)) < 2:
                findings.append(
                    Finding(path, f"{kind} definition {name} is not connected to a contract")
                )
    return findings


def _check_discriminated_public_alternatives(files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    all_text = "\n".join(path.read_text(encoding="utf-8") for path in files)
    for base in ("VellisQueryResponse", "VellisSnapshotExport"):
        match = re.search(rf"\babstract attribute def\s+{base}\s*\{{", all_text)
        if not match:
            continue
        base_block = _extract_braced_block(all_text, match.start())
        if not re.search(r"\battribute\s+kind\s*:\s*\w+", base_block):
            findings.append(
                Finding(MODEL_ROOT, f"public alternative base {base} lacks a discriminator")
            )
        subtypes = list(
            re.finditer(rf"\battribute def\s+(\w+)\s*:>\s*{base}(?:\s*,[^{{]+)?\s*\{{", all_text)
        )
        if len(subtypes) < 2:
            findings.append(
                Finding(MODEL_ROOT, f"public alternative base {base} lacks concrete alternatives")
            )
        for subtype in subtypes:
            subtype_block = _extract_braced_block(all_text, subtype.start())
            if not re.search(r":>>\s+kind\s*=\s*\w+::\w+\s*;", subtype_block):
                findings.append(
                    Finding(
                        MODEL_ROOT,
                        f"public alternative {subtype.group(1)} does not fix its discriminator",
                    )
                )
    return findings


def _check_requirement_and_verification_semantics(files: list[Path]) -> list[Finding]:
    """Require native obligations, satisfaction, and subject-compatible verification."""
    findings: list[Finding] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        requirements: dict[str, str] = {}
        for match in re.finditer(
            rf"(?m)^\s*requirement\s+(?!def\b){OPTIONAL_IDENTIFICATION}(\w+)\s*\{{",
            text,
        ):
            block = _extract_braced_block(text, match.start())
            subject = re.search(r"\bsubject\s+\w+\s*:\s*([\w:]+)", block)
            if not subject:
                findings.append(Finding(path, f"requirement {match.group(1)} has no subject"))
                continue
            requirements[match.group(1)] = subject.group(1)
            if not re.search(r"\brequire\s+constraint\b", block):
                findings.append(
                    Finding(path, f"requirement {match.group(1)} has no required constraint")
                )

        draft = bool(
            re.search(
                r"@SpecificationStatus\s*\{[^}]*lifecycleStatus\s*=\s*SpecLifecycle::draft;",
                text,
                re.DOTALL,
            )
        )
        if not draft:
            for name in requirements:
                if not re.search(rf"\bsatisfy\s+(?:requirement\s+)?{re.escape(name)}\s+by\b", text):
                    findings.append(Finding(path, f"accepted requirement {name} has no satisfier"))

        verified: set[str] = set()
        for match in re.finditer(r"(?m)^\s*verification def\s+(\w+)\s*\{", text):
            block = _extract_braced_block(text, match.start())
            subject = re.search(r"\bsubject\s+\w+\s*:\s*([\w:]+)", block)
            subject_type = subject.group(1) if subject else None
            if not subject_type:
                findings.append(
                    Finding(path, f"verification {match.group(1)} has no typed subject")
                )
            for requirement_name in re.findall(r"\bverify\s+(\w+)\s*;", block):
                verified.add(requirement_name)
                requirement_type = requirements.get(requirement_name)
                if requirement_type and subject_type and requirement_type != subject_type:
                    findings.append(
                        Finding(
                            path,
                            f"verification {match.group(1)} subject {subject_type} is incompatible "
                            f"with {requirement_name} subject {requirement_type}",
                        )
                    )
            if "verify " in block and "@EvidenceBinding" not in block:
                findings.append(
                    Finding(path, f"verification {match.group(1)} lacks evidence binding")
                )
        for name in requirements:
            if name not in verified:
                findings.append(Finding(path, f"requirement {name} has no verification objective"))

        failure_subjects = {
            subject_type
            for name, subject_type in requirements.items()
            if name.endswith("FailureSemantics")
        }
        for match in re.finditer(rf"\baction def\s+{OPTIONAL_IDENTIFICATION}(\w+)\s*\{{", text):
            block = _extract_braced_block(text, match.start())
            if "@FailureContract" in block and match.group(1) not in failure_subjects:
                findings.append(
                    Finding(
                        path,
                        f"action {match.group(1)} lacks an action-scoped failure requirement",
                    )
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

        for match in re.finditer(rf"\baction def\s+{OPTIONAL_IDENTIFICATION}(\w+)\s*\{{", text):
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
                rf"perform action\s+({SYSML_IDENTIFIER})\[[^]]+\]\s*:\s*(\w+)",
                component_block,
            ):
                raw_feature, action_name = match.groups()
                feature = _identifier_value(raw_feature)
                feature_block = _extract_braced_block(component_block, match.start())
                direct_access = bool(_documentation(feature_block))
                feature_pattern = rf"(?:{re.escape(feature)}|'{re.escape(feature)}')"
                dependency_access = any(
                    _documentation(_extract_braced_block(component_block, dependency.start()))
                    for dependency in re.finditer(
                        rf"\bdependency\s+\w+\s+from\s+{feature_pattern}\s+to\s+",
                        component_block,
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
        for match in re.finditer(r"\brequirement\s+<'([^']+)'>\s+(\w+)\s*\{", text):
            stable_id, name = match.groups()
            requirement_names.add(name)
            block = _extract_braced_block(text, match.start())
            if not stable_id:
                findings.append(Finding(path, f"requirement {name} lacks a SysML short ID"))
            if not _documentation(block):
                findings.append(Finding(path, f"requirement {name} lacks normative text"))
        verified = set(re.findall(r"\bverify\s+(\w+)\s*;", text))
        for name in sorted(requirement_names - verified):
            findings.append(Finding(path, f"requirement {name} lacks verification objective"))
    return findings


def _check_state_access_semantics() -> list[Finding]:
    findings: list[Finding] = []
    allowed = {"read", "create", "write", "delete", "noStateEffect"}
    for path in sorted(COMPONENT_MODEL_ROOT.glob("component.*.sysml")):
        text = path.read_text(encoding="utf-8")
        component_name = _component_definition_name(text)
        if not component_name:
            continue
        block = _definition_block(text, "part def", component_name)
        complete_contract = "\n".join(_part_definition_chain(text, component_name)) or block
        state_features = set(
            re.findall(
                r"(?m)^\s*(?:ref\s+)?(?:derived\s+)?(?:attribute|item)\s+"
                r"(\w+)(?:\[[^]]+\])?\s*:",
                block,
            )
        )
        provided_actions = {
            _identifier_value(name)
            for name in re.findall(
                rf"\bperform action\s+({SYSML_IDENTIFIER})\[[^]]+\]\s*:",
                complete_contract,
            )
        }
        actions_with_state_semantics: set[str] = set()
        for match in re.finditer(
            rf"\bdependency\s+(\w+)\s+from\s+({SYSML_IDENTIFIER})\s+to\s+([\w.]+)\s*\{{",
            block,
        ):
            dependency_name, raw_source, target = match.groups()
            source = _identifier_value(raw_source)
            dependency_block = _extract_braced_block(block, match.start())
            access = re.search(
                r"@StateAccess\s*\{[^}]*kind\s*=\s*StateAccessKind::(\w+);",
                dependency_block,
                re.DOTALL,
            )
            if target.rsplit(".", 1)[-1] in state_features and not access:
                findings.append(
                    Finding(path, f"state dependency {dependency_name} lacks typed StateAccess")
                )
            if access and access.group(1) not in allowed:
                findings.append(
                    Finding(path, f"state dependency {dependency_name} has invalid access kind")
                )
            if target.rsplit(".", 1)[-1] in state_features and access:
                actions_with_state_semantics.add(source)
        if state_features:
            for action in sorted(provided_actions - actions_with_state_semantics):
                findings.append(
                    Finding(
                        path,
                        f"stateful component action {action} lacks typed state access "
                        "or explicit no-state-effect",
                    )
                )
    return findings


def _check_native_behavior_realizations() -> list[Finding]:
    findings: list[Finding] = []
    operations_path = MODEL_ROOT / "vellis" / "VellisOperations.sysml"
    operations_text = operations_path.read_text(encoding="utf-8")
    facade = _definition_block(operations_text, "part def", "VellisApplicationFacade")
    if re.search(r"\bdependency\s+\w+Flow\s+from\s+rtg", facade):
        findings.append(Finding(operations_path, "facade still uses dependency as invocation"))
    facade_calls = re.findall(r"\baction\s+invoke\w*\s*:\s*\w+", facade)
    facade_performers = re.findall(r"\bperform\s+rtg\w+\.invoke\w*\s*;", facade)
    # Three façade actions are intentionally application-local projections:
    # usage guidance, reconstruction-evidence inspection, and the deprecated
    # runtime-health-only flush response. Every other action has a typed nested
    # provider invocation and matching performer declaration.
    expected_delegated_actions = 24
    if (
        len(facade_calls) != expected_delegated_actions
        or len(facade_performers) != expected_delegated_actions
    ):
        findings.append(
            Finding(
                operations_path,
                f"expected {expected_delegated_actions} delegated facade calls and "
                "performers; found "
                f"{len(facade_calls)} and {len(facade_performers)}",
            )
        )

    action_definitions: dict[str, str] = {}
    for source in (
        operations_text,
        (COMPONENT_MODEL_ROOT / "component.rtg.controller.sysml").read_text(encoding="utf-8"),
    ):
        for match in re.finditer(rf"\baction def\s+{OPTIONAL_IDENTIFICATION}(\w+)\s*\{{", source):
            action_definitions[match.group(1)] = _extract_braced_block(source, match.start())

    def features(action_type: str, direction: str) -> set[str]:
        return set(
            _identifier_value(name)
            for name in re.findall(
                rf"\b{direction}\s+(?:ref\s+)?(?:attribute\s+|part\s+|item\s+)?"
                rf"({SYSML_IDENTIFIER})(?:\[[^]]+\])?\s*:",
                action_definitions.get(action_type, ""),
            )
        )

    for outer in re.finditer(r"\bperform action\s+(rtg\w+)\[[^]]+\]\s*:\s*(\w+)\s*\{", facade):
        outer_name, outer_type = outer.groups()
        outer_block = _extract_braced_block(facade, outer.start())
        calls = list(re.finditer(r"\baction\s+(invoke\w*)\s*:\s*(\w+)\s*\{", outer_block))
        if not calls:
            continue
        for field in sorted(features(outer_type, "in") | features(outer_type, "out")):
            if not re.search(
                rf"\b{re.escape(outer_name)}\.{_identifier_pattern(field)}", outer_block
            ):
                findings.append(
                    Finding(operations_path, f"facade action {outer_name} does not connect {field}")
                )
        for call in calls:
            call_name, call_type = call.groups()
            call_block = _extract_braced_block(outer_block, call.start())
            for field in sorted(features(call_type, "in")):
                field_pattern = _identifier_pattern(field)
                if not re.search(
                    rf"\bin\s+(?:ref\s+)?(?:attribute\s+|part\s+|item\s+)?{field_pattern}"
                    rf"\s+redefines\s+{re.escape(call_type)}::{field_pattern}\s*=",
                    call_block,
                ):
                    findings.append(
                        Finding(
                            operations_path,
                            f"facade call {outer_name}.{call_name} leaves input {field} unbound",
                        )
                    )
            for field in sorted(features(call_type, "out")):
                field_pattern = _identifier_pattern(field)
                directly_bound = re.search(
                    rf"\bout\s+(?:ref\s+)?(?:attribute\s+|part\s+|item\s+)?{field_pattern}"
                    rf"\s+redefines\s+{re.escape(call_type)}::{field_pattern}\s*=",
                    call_block,
                )
                consumed = bool(re.search(rf"\b{call_name}\.{field_pattern}", outer_block))
                if not directly_bound and not consumed:
                    findings.append(
                        Finding(
                            operations_path,
                            f"facade call {outer_name}.{call_name} leaves output "
                            f"{field} disconnected",
                        )
                    )

    controller_path = COMPONENT_MODEL_ROOT / "component.rtg.controller.sysml"
    controller_text = controller_path.read_text(encoding="utf-8")
    controller = _definition_block(controller_text, "part def", "RtgController")
    for call in re.finditer(r"(?<!perform )\baction\s+(\w+)\s*:\s*(\w+)\s*\{", controller):
        call_name, call_type = call.groups()
        if call_type not in action_definitions:
            continue
        call_block = _extract_braced_block(controller, call.start())
        for field in sorted(features(call_type, "in")):
            field_pattern = _identifier_pattern(field)
            if not re.search(
                rf"\bin\s+(?:ref\s+)?(?:attribute\s+|part\s+|item\s+)?{field_pattern}"
                rf"\s+redefines\s+{re.escape(call_type)}::{field_pattern}\s*=",
                call_block,
            ):
                findings.append(
                    Finding(
                        controller_path,
                        f"controller call {call_name} leaves input {field} unbound",
                    )
                )
        for field in sorted(features(call_type, "out")):
            field_pattern = _identifier_pattern(field)
            directly_bound = re.search(
                rf"\bout\s+(?:ref\s+)?(?:attribute\s+|part\s+|item\s+)?{field_pattern}"
                rf"\s+redefines\s+{re.escape(call_type)}::{field_pattern}\s*=",
                call_block,
            )
            consumed = bool(re.search(rf"\b{call_name}\.{field_pattern}", controller))
            if not directly_bound and not consumed:
                findings.append(
                    Finding(
                        controller_path,
                        f"controller call {call_name} leaves output {field} disconnected",
                    )
                )

    mcp_path = MODEL_ROOT / "vellis" / "realizations" / "VellisMcpPython.sysml"
    mcp_text = mcp_path.read_text(encoding="utf-8")
    adapter = _definition_block(mcp_text, "part def", "VellisMcpAdapter")
    registrations = re.findall(
        r"\bperform action\s+\w+\[[^]]+\]\s*:\s*\w+\s*\{\s*@McpToolBinding",
        adapter,
    )
    allocations = re.findall(
        r"\ballocate\s+adapter\.\w+\s+to\s+application\.gateway\.invokeTool\s*;",
        mcp_text,
    )
    if "ref part gateway[1] : McpGateway;" not in adapter:
        findings.append(Finding(mcp_path, "MCP transport adapter lacks its generic gateway role"))
    if "part application : VellisRuntimePython;" not in mcp_text:
        findings.append(Finding(mcp_path, "MCP transport does not compose runtime-native Vellis"))
    if "bind adapter.gateway = application.gateway;" not in mcp_text:
        findings.append(Finding(mcp_path, "MCP transport is not bound to the generic gateway"))
    if len(registrations) != 27 or len(allocations) != 27:
        findings.append(
            Finding(
                mcp_path,
                "MCP realization must project all 27 typed registrations through "
                "gateway.invokeTool",
            )
        )
    for forbidden in (
        "invokeFacade",
        "RtgMcpToolset",
        "ref part facade",
        "bind adapter.facade",
        "VellisLocalPythonRealization",
    ):
        if forbidden in mcp_text:
            findings.append(
                Finding(mcp_path, f"generic MCP realization retains direct coupling: {forbidden}")
            )
    local_path = MODEL_ROOT / "vellis" / "realizations" / "VellisLocalPython.sysml"
    local_text = local_path.read_text(encoding="utf-8")
    local_allocations = re.findall(
        r"allocate\s+logicalVellis\.facade\.\w+\s+to\s+pythonVellis\.facade\.\w+\s*;",
        local_text,
    )
    if "part :>> facade : PythonVellisFacade;" not in local_text or len(local_allocations) != 27:
        findings.append(
            Finding(local_path, "Python facade realization must allocate all 27 logical actions")
        )
    return findings


def _check_view_semantics() -> list[Finding]:
    findings: list[Finding] = []
    expected = {
        MODEL_ROOT / "bibliotek" / "views" / "BibliotekViews.sysml": {
            "SysML::PartDefinition",
            "SysML::PartUsage",
            "SysML::BindingConnectorAsUsage",
            "SysML::AllocationUsage",
            "SysML::ActionDefinition",
            "SysML::ActionUsage",
            "SysML::Dependency",
            "SysML::SuccessionAsUsage",
            "SysML::RequirementUsage",
            "SysML::SatisfyRequirementUsage",
            "SysML::VerificationCaseDefinition",
        },
        MODEL_ROOT / "vellis" / "views" / "VellisViews.sysml": {
            "SysML::PartDefinition",
            "SysML::PartUsage",
            "SysML::PortDefinition",
            "SysML::PortUsage",
            "SysML::InterfaceDefinition",
            "SysML::InterfaceUsage",
            "SysML::FlowUsage",
            "SysML::BindingConnectorAsUsage",
            "SysML::AllocationUsage",
            "SysML::UseCaseDefinition",
            "SysML::UseCaseUsage",
            "SysML::ActionUsage",
            "SysML::SuccessionAsUsage",
            "SysML::RequirementUsage",
            "SysML::SatisfyRequirementUsage",
            "SysML::VerificationCaseDefinition",
        },
    }
    for path, required_filters in expected.items():
        text = path.read_text(encoding="utf-8")
        if "viewpoint def" in text:
            findings.append(Finding(path, "projection-only concerns must use view definitions"))
        filter_statements = re.findall(r"\bfilter\s+([^;]+);", text)
        filters = {
            name for statement in filter_statements for name in re.findall(r"@([\w:]+)", statement)
        }
        missing = sorted(required_filters - filters)
        if missing:
            findings.append(Finding(path, f"view projections omit filters: {missing}"))
        for definition in re.finditer(r"\bview def\s+\w+\s*\{", text):
            block = _extract_braced_block(text, definition.start())
            definition_filters = re.findall(r"\bfilter\s+([^;]+);", block)
            if len(definition_filters) != 1 or " or " not in definition_filters[0]:
                findings.append(
                    Finding(path, "each multi-type view definition needs one disjunctive filter")
                )
        for statement in filter_statements:
            if len(re.findall(r"@[\w:]+", statement)) > 1 and " or " not in statement:
                findings.append(Finding(path, "multi-type view filters must be disjunctive"))
    try:
        diagram_specs = discover_diagrams(_read_json(GENERATED_FORMAL_INDEX))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        findings.append(Finding(GENERATED_FORMAL_INDEX, f"invalid diagram inventory: {error}"))
        diagram_specs = ()
    diagram_ids = [spec.diagram_id for spec in diagram_specs]
    if len(diagram_ids) != len(set(diagram_ids)):
        findings.append(Finding(GENERATED_FORMAL_INDEX, "registered diagram IDs must be unique"))
    vellis_path = MODEL_ROOT / "vellis" / "views" / "VellisViews.sysml"
    vellis_text = vellis_path.read_text(encoding="utf-8")
    for package in (
        "VellisLocalPythonRealization",
        "VellisMcpPythonRealization",
        "VellisRuntimePythonRealization",
    ):
        if f"private import {package}::*;" not in vellis_text:
            findings.append(Finding(vellis_path, f"Vellis views do not import {package}"))
        if f"expose {package}::**;" not in vellis_text:
            findings.append(
                Finding(vellis_path, f"Vellis composition view does not expose {package}")
            )
    return findings


def _normalized_name(value: str) -> str:
    return "".join(_words(value))


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
        _normalized_name(_identifier_value(name))
        for name in re.findall(
            rf"\b(?:attribute|item|part)\s+({SYSML_IDENTIFIER})(?:\[[^]]+\])?"
            rf"(?:\s+ordered)?\s*:",
            block,
        )
    }
    parent = match.group(1)
    if parent:
        fields.update(_modeled_public_fields(text, parent, seen))
    return fields


def _check_verification_closure() -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(COMPONENT_MODEL_ROOT.glob("component.*.sysml")):
        text = path.read_text(encoding="utf-8")
        component_id = _component_id(text) or path.stem
        status = _component_model_statuses().get(component_id)
        verifications = list(re.finditer(r"\bverification def\s+(\w+)\s*\{", text))
        if not verifications:
            findings.append(Finding(path, "component lacks a boundary verification definition"))
            continue
        if not any(match.group(1).endswith("BoundaryVerification") for match in verifications):
            findings.append(Finding(path, "component lacks a named boundary verification"))
        for verification in verifications:
            name = verification.group(1)
            block = _extract_braced_block(text, verification.start())
            if not re.search(r"\bobjective\s*\{.*?\bverify\s+\w+", block, re.DOTALL):
                findings.append(Finding(path, f"verification {name} has no modeled objective"))
            evidence = re.search(r'evidenceId\s*=\s*"([^"]+)"', block)
            if not evidence:
                findings.append(Finding(path, f"verification {name} lacks evidence binding"))
                continue
            evidence_id = evidence.group(1)
            if not evidence_id.endswith(f"#{name}"):
                findings.append(
                    Finding(path, f"verification {name} evidence lacks its exact evidence group")
                )
            evidence_path = evidence_id.split("#", 1)[0].split("::", 1)[0]
            if status != "draft" and not (ROOT / evidence_path).exists():
                findings.append(Finding(path, f"evidence does not resolve: {evidence_id}"))
            elif status != "draft" and not _evidence_test_nodes(evidence_id):
                findings.append(
                    Finding(path, f"evidence has no concrete test nodes: {evidence_id}")
                )
    return findings


@functools.cache
def _test_module(path: Path, modified_ns: int, size: int) -> ast.Module | None:
    """Parse one stable test-file version for evidence lookup helpers."""
    del modified_ns, size
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except OSError, SyntaxError:
        return None


def _current_test_module(path: Path) -> ast.Module | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return _test_module(path, stat.st_mtime_ns, stat.st_size)


def _test_functions(path: Path) -> list[str]:
    tree = _current_test_module(path)
    if tree is None:
        return []
    return sorted(
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    )


def _is_evidence_wrapper(path: Path, symbol: str) -> bool:
    """Return whether a test merely delegates its proof to another test function."""
    tree = _current_test_module(path)
    if tree is None:
        return False
    function = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol
        ),
        None,
    )
    if function is None:
        return False
    statements = [
        statement
        for statement in function.body
        if not isinstance(statement, (ast.Import, ast.ImportFrom))
        and not (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        )
    ]
    if len(statements) != 1:
        return False
    statement = statements[0]
    value = statement.value if isinstance(statement, (ast.Expr, ast.Return)) else None
    if not isinstance(value, ast.Call):
        return False
    callable_node = value.func
    return (isinstance(callable_node, ast.Name) and callable_node.id.startswith("test_")) or (
        isinstance(callable_node, ast.Attribute) and callable_node.attr.startswith("test_")
    )


def _evidence_group_map(path: Path) -> dict[str, tuple[str, ...]]:
    tree = _current_test_module(path)
    if tree is None:
        return {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(
            isinstance(target, ast.Name) and target.id == "MODEL_EVIDENCE" for target in targets
        ):
            continue
        value_node = node.value
        if value_node is None:
            return {}
        try:
            value = ast.literal_eval(value_node)
        except ValueError, SyntaxError:
            return {}
        if not isinstance(value, dict):
            return {}
        result: dict[str, tuple[str, ...]] = {}
        for group, symbols in value.items():
            if not isinstance(group, str) or not isinstance(symbols, tuple | list):
                return {}
            if not symbols or any(not isinstance(symbol, str) for symbol in symbols):
                return {}
            normalized = tuple(symbols)
            if len(set(normalized)) != len(normalized):
                return {}
            result[group] = normalized
        return result
    return {}


def _evidence_test_nodes(evidence_id: str) -> list[str]:
    source, _, group = evidence_id.partition("#")
    if source == "pending":
        return []
    if "::" in source:
        path_text, symbol = source.split("::", 1)
        path = ROOT / path_text
        return (
            [f"{path_text}::{symbol}"]
            if symbol in _test_functions(path) and not _is_evidence_wrapper(path, symbol)
            else []
        )
    if not group:
        return []
    tests = set(_test_functions(ROOT / source))
    symbols = _evidence_group_map(ROOT / source).get(group, ())
    path = ROOT / source
    if any(symbol not in tests or _is_evidence_wrapper(path, symbol) for symbol in symbols):
        return []
    return [f"{source}::{symbol}" for symbol in symbols]


def _verification_evidence_data() -> dict[str, object]:
    groups: dict[str, object] = {}
    for path in _sysml_files("all"):
        text = path.read_text(encoding="utf-8")
        for evidence_id in re.findall(r'evidenceId\s*=\s*"([^"]+)"', text):
            test_nodes = _evidence_test_nodes(evidence_id)
            groups[evidence_id] = {
                "model_source": str(path.relative_to(ROOT)),
                "test_nodes": test_nodes,
                "status": (
                    "pending"
                    if evidence_id.startswith("pending#")
                    else "resolved"
                    if test_nodes
                    else "unresolved"
                ),
            }
    return {
        "description": (
            "Generated concrete test-node index for modeled verification evidence groups."
        ),
        "groups": dict(sorted(groups.items())),
    }


def _audit_python_boundary(component_id: str) -> dict[str, object]:
    code_root = ROOT / "components" / Path(*component_id.removeprefix("component.").split("."))
    protocol_path = code_root / "protocol.py"
    if not protocol_path.exists():
        return {"protocol": None, "records": {}, "literal_aliases": {}}
    tree = ast.parse(protocol_path.read_text(encoding="utf-8"))
    records: dict[str, dict[str, object]] = {}
    literal_aliases: dict[str, list[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            fields: dict[str, object] = {}
            for member in node.body:
                if not isinstance(member, ast.AnnAssign) or not isinstance(member.target, ast.Name):
                    continue
                fields[_normalized_name(member.target.id)] = {
                    "python_name": member.target.id,
                    "annotation": ast.unparse(member.annotation),
                    "has_default": member.value is not None,
                    "default_expression": (
                        ast.unparse(member.value) if member.value is not None else None
                    ),
                }
            if fields:
                records[node.name] = fields
        elif isinstance(node, ast.TypeAlias) and isinstance(node.name, ast.Name):
            values = [
                value.value
                for value in ast.walk(node.value)
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
            ]
            if values:
                literal_aliases[node.name.id] = values
    return {
        "protocol": str(protocol_path.relative_to(ROOT)),
        "records": records,
        "literal_aliases": literal_aliases,
    }


def _audit_model_boundary(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    records: dict[str, dict[str, object]] = {}
    bases: dict[str, str] = {}
    for match in re.finditer(
        rf"\b(?:attribute|item) def\s+{OPTIONAL_IDENTIFICATION}(\w+)\s*(?:[^{{;]*)\{{",
        text,
    ):
        base = re.search(r":>\s*(\w+)", match.group(0))
        if base:
            bases[match.group(1)] = base.group(1)
        block = _extract_braced_block(text, match.start())
        fields: dict[str, object] = {}
        for field in re.finditer(
            rf"\b(?:attribute|item|ref item)\s+{OPTIONAL_IDENTIFICATION}({SYSML_IDENTIFIER})"
            r"(?P<multiplicity>\[[^]]+\])?(?:\s+(?:ordered|nonunique))*"
            r"\s*:\s*(?P<type>[\w:']+)"
            r"(?P<value>\s+default\s*=|\s*=)?",
            block,
        ):
            name = field.group(1).strip("'")
            value_kind = field.group("value") or ""
            fields[_normalized_name(name)] = {
                "model_name": name,
                "type": field.group("type"),
                "multiplicity": field.group("multiplicity") or "[1]",
                "value_kind": (
                    "default"
                    if "default" in value_kind
                    else "fixed"
                    if "=" in value_kind
                    else "none"
                ),
            }
        if fields:
            records[match.group(1)] = fields

    def inherited_fields(record_name: str, seen: frozenset[str] = frozenset()) -> dict[str, object]:
        if record_name in seen:
            return dict(records.get(record_name, {}))
        result: dict[str, object] = {}
        base_name = bases.get(record_name)
        if base_name in records:
            result.update(inherited_fields(base_name, seen | {record_name}))
        result.update(records.get(record_name, {}))
        return result

    records = {record_name: inherited_fields(record_name) for record_name in records}
    enums: dict[str, list[str]] = {}
    for match in re.finditer(r"\benum def\s+(\w+)\s*\{", text):
        block = _extract_braced_block(text, match.start())
        enums[match.group(1)] = [
            value.strip("'") for value in re.findall(r"\benum\s+([\w']+)", block) if value != "def"
        ]
    return {"records": records, "enums": enums}


def _audit_component(component_id: str) -> dict[str, object]:
    model_path = COMPONENT_MODEL_ROOT / f"{component_id}.sysml"
    if not model_path.exists():
        raise ValueError(f"unknown component target: {component_id}")
    model = _audit_model_boundary(model_path)
    python = _audit_python_boundary(component_id)
    findings: list[dict[str, object]] = []
    comparisons: list[dict[str, object]] = []
    model_records = model["records"]
    python_records = python["records"]
    assert isinstance(model_records, dict) and isinstance(python_records, dict)
    for record_name in sorted(set(model_records) & set(python_records)):
        model_fields = model_records[record_name]
        python_fields = python_records[record_name]
        assert isinstance(model_fields, dict) and isinstance(python_fields, dict)
        for field_name in sorted(set(model_fields) | set(python_fields)):
            if field_name not in model_fields:
                findings.append(
                    {
                        "kind": "python_field_missing_from_model",
                        "candidate_classification": "model_drift",
                        "record": record_name,
                        "field": field_name,
                    }
                )
                continue
            if field_name not in python_fields:
                findings.append(
                    {
                        "kind": "model_field_missing_from_python",
                        "candidate_classification": "implementation_drift",
                        "record": record_name,
                        "field": field_name,
                    }
                )
                continue
            model_field = model_fields[field_name]
            python_field = python_fields[field_name]
            assert isinstance(model_field, dict) and isinstance(python_field, dict)
            model_default = model_field["value_kind"] == "default"
            model_optional = str(model_field["multiplicity"]).startswith("[0")
            python_default = bool(python_field["has_default"])
            if (model_default and not python_default) or (
                python_default and not model_default and not model_optional
            ):
                findings.append(
                    {
                        "kind": "default_mismatch",
                        "candidate_classification": "human_decision_required",
                        "record": record_name,
                        "field": field_name,
                        "model": model_field,
                        "python": python_field,
                    }
                )
            if (
                model_field["multiplicity"] == "[0..1]"
                and model_field["type"] == "JsonValue"
                and python_field.get("default_expression") == "None"
            ):
                findings.append(
                    {
                        "kind": "optional_json_null_normalization",
                        "candidate_classification": "human_decision_required",
                        "record": record_name,
                        "field": field_name,
                        "model": model_field,
                        "python": python_field,
                        "question": (
                            "Python uses None for modeled absence even though JSON null is also a "
                            "valid present value; decide whether the distinction is contract-"
                            "significant or declare a codec."
                        ),
                    }
                )
            comparisons.append(
                {
                    "kind": "type_comparison",
                    "record": record_name,
                    "field": field_name,
                    "model": {
                        "type": model_field["type"],
                        "multiplicity": model_field["multiplicity"],
                    },
                    "python": {"annotation": python_field["annotation"]},
                }
            )
    literal_aliases = python["literal_aliases"]
    enums = model["enums"]
    assert isinstance(literal_aliases, dict) and isinstance(enums, dict)
    for enum_name in sorted(set(enums) & set(literal_aliases)):
        if set(enums[enum_name]) != set(literal_aliases[enum_name]):
            findings.append(
                {
                    "kind": "enum_literal_mismatch",
                    "candidate_classification": "human_decision_required",
                    "type": enum_name,
                    "model": enums[enum_name],
                    "python": literal_aliases[enum_name],
                }
            )
    model_text = model_path.read_text(encoding="utf-8")
    evidence = {
        evidence_id: _evidence_test_nodes(evidence_id)
        for evidence_id in re.findall(r'evidenceId\s*=\s*"([^"]+)"', model_text)
    }
    codecs: list[dict[str, str]] = []
    for realization_path in (MODEL_ROOT / "vellis" / "realizations").glob("*.sysml"):
        realization_text = realization_path.read_text(encoding="utf-8")
        code_root = (
            f'codeRoot = "components/{component_id.removeprefix("component.").replace(".", "/")}"'
        )
        for part in re.finditer(r"\bpart def\s+[^\n{]+\{", realization_text):
            part_block = _extract_braced_block(realization_text, part.start())
            if code_root not in part_block:
                continue
            for block in re.findall(r"@ImplementationCodec\s*\{([^}]*)\}", part_block):
                values = dict(
                    re.findall(
                        r'(logicalType|implementationType|normalization)\s*=\s*"([^"]*)"',
                        block,
                    )
                )
                if values:
                    codecs.append(values)
    history = subprocess.run(
        [
            "git",
            "log",
            "--follow",
            "-n",
            "8",
            "--format=%h %ad %s",
            "--date=short",
            "--",
            str(model_path.relative_to(ROOT)),
        ],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    ).stdout.splitlines()
    predecessor_path = Path("docs/components") / f"{component_id}.md"
    predecessor_history = subprocess.run(
        [
            "git",
            "log",
            "--all",
            "-n",
            "8",
            "--format=%h %ad %s",
            "--date=short",
            "--",
            str(predecessor_path),
        ],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    ).stdout.splitlines()
    python_module = component_id.removeprefix("component.").replace(".", ".")
    package_name = "Bibliotek" + "".join(
        segment.title() for segment in component_id.removeprefix("component.").split(".")
    )
    consumer_search = _consumer_reference_paths(
        f"{re.escape(component_id)}|components\\.{re.escape(python_module)}|{package_name}"
    )
    action_signature_findings = [
        finding.message
        for finding in _check_protocol_action_signatures()
        if finding.path == model_path
    ]
    code_root = ROOT / "components" / Path(*component_id.removeprefix("component.").split("."))
    production_paths = tuple(path for path in code_root.glob("*.py") if path.name != "reference.py")
    resource_scaling_findings = [
        {
            "kind": "forbidden_whole_state_mechanic",
            "candidate_classification": "implementation_drift",
            "path": str(finding.path.relative_to(ROOT)),
            "message": finding.message,
        }
        for finding in _check_resource_scaling_antipatterns(production_paths)
    ]
    for path in production_paths:
        text = path.read_text(encoding="utf-8")
        if re.search(r"compensation|before[_-]?image|preimage", text, re.IGNORECASE):
            resource_scaling_findings.append(
                {
                    "kind": "retained_compensation_state_review",
                    "candidate_classification": "human_decision_required",
                    "path": str(path.relative_to(ROOT)),
                    "message": (
                        "Review whether compensation or before-image data survives beyond one "
                        "owner invocation."
                    ),
                }
            )
    return {
        "component_id": component_id,
        "lifecycle": _component_model_statuses().get(component_id),
        "model_source": str(model_path.relative_to(ROOT)),
        "python_boundary": python,
        "model_boundary": model,
        "implementation_codecs": codecs,
        "evidence_groups": evidence,
        "history": history,
        "predecessor_contract": {
            "path": str(predecessor_path),
            "history": predecessor_history,
        },
        "consumer_references": sorted(
            path.removeprefix("./")
            for path in consumer_search
            if path.removeprefix("./") != str(model_path.relative_to(ROOT))
        ),
        "action_signature_findings": action_signature_findings,
        "resource_scaling_findings": resource_scaling_findings,
        "boundary_comparisons": comparisons,
        "candidate_findings": findings,
    }


def _consumer_reference_paths(pattern: str) -> list[str]:
    excluded_prefixes = ("reference/", "generated/reference/", "build/")
    if shutil.which("rg"):
        return subprocess.run(
            [
                "rg",
                "-l",
                "--glob",
                "!reference/**",
                "--glob",
                "!generated/reference/**",
                "--glob",
                "!build/**",
                pattern,
                ".",
            ],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
        ).stdout.splitlines()

    tracked_and_untracked = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    ).stdout.splitlines()
    expression = re.compile(pattern)
    matches: list[str] = []
    for relative in tracked_and_untracked:
        normalized = relative.removeprefix("./")
        if normalized.startswith(excluded_prefixes):
            continue
        path = ROOT / normalized
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            continue
        if expression.search(text):
            matches.append(normalized)
    return matches


def model_audit(target: str | None, output_root: Path | None = None) -> tuple[Path, Path]:
    statuses = _component_model_statuses()
    targets = (
        [target]
        if target
        else sorted(key for key, value in statuses.items() if value == "accepted")
    )
    unknown = [component_id for component_id in targets if component_id not in statuses]
    if unknown:
        raise ValueError(f"unknown component target: {unknown[0]}")
    payload = {
        "description": (
            "Advisory evidence bundle; candidate findings require authority triage before mutation."
        ),
        "classifications": [
            "model_drift",
            "implementation_drift",
            "intentional_codec",
            "intentional_implementation_freedom",
            "tooling_gap",
            "evidence_gap",
            "human_decision_required",
        ],
        "components": [_audit_component(component_id) for component_id in targets],
    }
    destination = output_root or ROOT / "build" / "model-audits"
    destination.mkdir(parents=True, exist_ok=True)
    stem = target or "all-accepted"
    json_path = destination / f"{stem}.json"
    markdown_path = destination / f"{stem}.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        f"# Model hygiene audit: {stem}",
        "",
        (
            "Advisory only. Classify each candidate with history and consumer evidence before "
            "changing an accepted model or realization."
        ),
        "",
    ]
    for component in payload["components"]:
        assert isinstance(component, dict)
        findings = component["candidate_findings"]
        evidence = component["evidence_groups"]
        assert isinstance(findings, list) and isinstance(evidence, dict)
        lines.extend(
            [
                f"## {component['component_id']}",
                "",
                f"- Lifecycle: {component['lifecycle']}",
                f"- Candidate findings: {len(findings)}",
                f"- Boundary field comparisons: {len(component['boundary_comparisons'])}",
                f"- Action signature findings: {len(component['action_signature_findings'])}",
                f"- Evidence groups: {len(evidence)}",
                f"- Explicit codecs: {len(component['implementation_codecs'])}",
                "",
            ]
        )
        if findings:
            lines.extend(["### Candidate findings", ""])
            for finding in findings:
                assert isinstance(finding, dict)
                model_detail = finding.get("model")
                field_name = finding.get("field")
                if isinstance(model_detail, dict):
                    field_name = model_detail.get("model_name", field_name)
                subject = ".".join(
                    str(value) for value in (finding.get("record"), field_name) if value
                )
                lines.append(
                    f"- `{finding['kind']}` ({finding['candidate_classification']})"
                    + (f": `{subject}`" if subject else "")
                    + (f" — {finding['question']}" if finding.get("question") else "")
                )
            lines.append("")
        codecs = component["implementation_codecs"]
        assert isinstance(codecs, list)
        if codecs:
            lines.extend(["### Declared realization codecs", ""])
            for codec in codecs:
                assert isinstance(codec, dict)
                lines.append(
                    f"- `{codec.get('logicalType', '?')}` ↔ "
                    f"`{codec.get('implementationType', '?')}`: "
                    f"{codec.get('normalization', '')}"
                )
            lines.append("")
        lines.extend(["### Evidence resolution", ""])
        for evidence_id, nodes in sorted(evidence.items()):
            assert isinstance(nodes, list)
            lines.append(f"- `{evidence_id}`: {len(nodes)} concrete test node(s)")
        lines.append("")
        action_findings = component["action_signature_findings"]
        assert isinstance(action_findings, list)
        if action_findings:
            lines.extend(["### Action signature findings", ""])
            lines.extend(f"- {finding}" for finding in action_findings)
            lines.append("")
        predecessor = component["predecessor_contract"]
        consumers = component["consumer_references"]
        history = component["history"]
        assert isinstance(predecessor, dict)
        assert isinstance(consumers, list)
        assert isinstance(history, list)
        lines.extend(
            [
                "### Authority evidence",
                "",
                f"- Current model history entries: {len(history)}",
                f"- Predecessor candidate: `{predecessor['path']}` "
                f"({len(predecessor['history'])} history entries)",
                f"- Consumer/reference files: {len(consumers)}",
            ]
        )
        lines.extend(f"  - `{path}`" for path in consumers[:20])
        if len(consumers) > 20:
            lines.append(f"  - … {len(consumers) - 20} more in the JSON bundle")
        lines.append("")
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, markdown_path


def _conformance_objectives_data() -> dict[str, object]:
    requirements_by_source: dict[Path, dict[str, str]] = {}
    global_requirements: dict[str, set[str]] = {}
    for path in _sysml_files("all"):
        text = path.read_text(encoding="utf-8")
        requirements = {
            name: stable_id
            for stable_id, name in re.findall(r"\brequirement\s+<'([^']+)'>\s+(\w+)\s*\{", text)
        }
        requirements_by_source[path] = requirements
        for name, stable_id in requirements.items():
            global_requirements.setdefault(name, set()).add(stable_id)

    objectives: list[dict[str, object]] = []
    for path in _sysml_files("all"):
        text = path.read_text(encoding="utf-8")
        local_requirements = requirements_by_source[path]
        for match in re.finditer(r"\bverification def\s+(\w+)\s*\{", text):
            block = _extract_braced_block(text, match.start())
            subject = re.search(r"\bsubject\s+(\w+)\s*:\s*([\w:]+)", block)
            evidence = re.search(r'evidenceId\s*=\s*"([^"]+)"', block)
            requirement_ids: list[str] = []
            for requirement_name in re.findall(r"\bverify\s+(\w+)\s*;", block):
                stable_id = local_requirements.get(requirement_name)
                if stable_id is None:
                    candidates = global_requirements.get(requirement_name, set())
                    stable_id = next(iter(candidates)) if len(candidates) == 1 else requirement_name
                requirement_ids.append(stable_id)
            evidence_id = evidence.group(1) if evidence else ""
            objectives.append(
                {
                    "verification": match.group(1),
                    "model_source": path.relative_to(ROOT).as_posix(),
                    "subject": {
                        "role": subject.group(1) if subject else "unknown",
                        "type": subject.group(2) if subject else "unknown",
                    },
                    "requirements": requirement_ids,
                    "evidence_id": evidence_id,
                    "evidence_nodes": _evidence_test_nodes(evidence_id) if evidence_id else [],
                    "status": "pending" if evidence_id.startswith("pending#") else "resolved",
                }
            )
    return {
        "schema_version": 1,
        "description": (
            "Generated implementation-neutral verification objectives derived from SysML "
            "subjects, requirements, and evidence bindings."
        ),
        "objectives": sorted(
            objectives,
            key=lambda item: (str(item["model_source"]), str(item["verification"])),
        ),
    }


def _model_source_digest() -> str:
    digest = hashlib.sha256()
    for path in _sysml_files("all"):
        relative = path.relative_to(MODEL_ROOT).as_posix()
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _check_formal_model_index() -> list[Finding]:
    try:
        index = _read_json(GENERATED_FORMAL_INDEX)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return [Finding(GENERATED_FORMAL_INDEX, f"invalid formal model index: {error}")]
    findings: list[Finding] = []
    if index.get("source_digest") != _model_source_digest():
        findings.append(
            Finding(GENERATED_FORMAL_INDEX, "formal parser index is stale; run just model-render")
        )
    packages = index.get("packages")
    authored = index.get("authored_packages")
    if not isinstance(packages, dict) or not isinstance(authored, dict):
        return [Finding(GENERATED_FORMAL_INDEX, "formal parser index lacks package inventories")]
    expected_sources = {path.relative_to(ROOT).as_posix() for path in _sysml_files("all")}
    if set(authored.values()) != expected_sources or set(packages) != set(authored):
        findings.append(
            Finding(GENERATED_FORMAL_INDEX, "formal parser package inventory is incomplete")
        )

    expected_kinds = {
        "action": "ActionDefinition",
        "attribute": "AttributeDefinition",
        "calc": "CalculationDefinition",
        "constraint": "ConstraintDefinition",
        "item": "ItemDefinition",
        "metadata": "MetadataDefinition",
        "part": "PartDefinition",
        "use case": "UseCaseDefinition",
        "verification": "VerificationCaseDefinition",
        "view": "ViewDefinition",
    }
    source_to_package = {str(source): str(package) for package, source in authored.items()}
    for path in _sysml_files("all"):
        relative = path.relative_to(ROOT).as_posix()
        package = source_to_package.get(relative)
        package_index = packages.get(package, {}) if package else {}
        named = package_index.get("named_elements", []) if isinstance(package_index, dict) else []
        parsed = {
            (str(element.get("kind")), str(element.get("name")))
            for element in named
            if isinstance(element, dict)
        }
        text = path.read_text(encoding="utf-8")
        for keyword, formal_kind in expected_kinds.items():
            for name in re.findall(rf"\b{keyword}\s+def\s+{OPTIONAL_IDENTIFICATION}(\w+)", text):
                if (formal_kind, name) not in parsed:
                    findings.append(
                        Finding(
                            GENERATED_FORMAL_INDEX,
                            f"official parser index omits {formal_kind} {package}::{name}",
                        )
                    )
        for name in re.findall(r"\brequirement\s+<'[^']+'>\s+(\w+)\s*\{", text):
            if ("RequirementUsage", name) not in parsed:
                findings.append(
                    Finding(
                        GENERATED_FORMAL_INDEX,
                        f"official parser index omits RequirementUsage {package}::{name}",
                    )
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
    for actor_type in ("HumanOperator", "AiAgent"):
        if not re.search(rf"\bpart def\s+{actor_type}\s*:>\s*VellisUser\b", text):
            findings.append(Finding(path, f"missing VellisUser specialization {actor_type}"))
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
    operations_text = (MODEL_ROOT / "vellis" / "VellisOperations.sysml").read_text(encoding="utf-8")
    operation_types = set(
        re.findall(rf"\baction def\s+{OPTIONAL_IDENTIFICATION}(\w+)", operations_text)
    )
    performers = {
        (_identifier_value(use_case), _identifier_value(action))
        for use_case, action in re.findall(
            rf"\bperform\s+({SYSML_IDENTIFIER})\.({SYSML_IDENTIFIER})\s*;", text
        )
    }
    actor_occurrences = dict(re.findall(r"\bpart\s+(\w+)\s*:\s*(HumanOperator|AiAgent)\s*;", text))
    for match in re.finditer(
        rf"\buse case\s+(?!def\b)({SYSML_IDENTIFIER})\s*:\s*(\w+)\s*\{{", text
    ):
        usage_name = _identifier_value(match.group(1))
        block = _extract_braced_block(text, match.start())
        actor_binding = re.search(r"\bactor\s+users\s*=\s*(\w+)\s*;", block)
        if (
            "subject application = vellis;" not in block
            or actor_binding is None
            or actor_binding.group(1) not in actor_occurrences
        ):
            findings.append(Finding(path, f"use case {usage_name} lacks subject or actor binding"))
        nested_actions = re.findall(
            rf"\b(?:then\s+)?action\s+({SYSML_IDENTIFIER})\s*:\s*(\w+)\s*;", block
        )
        if not nested_actions:
            findings.append(Finding(path, f"use case {usage_name} has no observable actions"))
        for action_name, action_type in nested_actions:
            action_name = _identifier_value(action_name)
            if action_type not in operation_types:
                findings.append(
                    Finding(path, f"use case {usage_name} uses unknown action type {action_type}")
                )
            if (usage_name, action_name) not in performers:
                findings.append(
                    Finding(path, f"facade does not perform {usage_name}.{action_name}")
                )
    return findings


def _python_tool_names() -> tuple[str, ...]:
    """Return the generated inventory projected by the generic MCP transport host.

    The transport deliberately has no hard-coded Vellis tool functions.  Its concrete tool
    inventory is the generated application manifest consumed by ``gateway_registration.py`` and
    projected from ``gateway.registrations`` by ``mcp_server.py``.
    """
    return tuple(str(tool["name"]) for tool in _generated_gateway_tools())


def _generated_gateway_tools() -> tuple[dict[str, Any], ...]:
    manifest = _read_json(GENERATED_MANIFEST)
    tools = manifest.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ValueError("generated application manifest has no MCP tool registrations")
    registrations: list[dict[str, Any]] = []
    names: set[str] = set()
    for value in tools:
        if not isinstance(value, dict):
            raise ValueError("generated MCP tool registration must be an object")
        name = value.get("name")
        description = value.get("description")
        if not isinstance(name, str) or not name:
            raise ValueError("generated MCP tool registration lacks a name")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"generated MCP tool registration {name} lacks a description")
        if name in names:
            raise ValueError(f"generated MCP tool registration repeats {name}")
        names.add(name)
        registrations.append(value)
    return tuple(registrations)


def _python_tool_parameters() -> dict[str, tuple[tuple[str, bool, Any], ...]]:
    """Return the generated facade catalog consumed by the message-native gateway."""
    parameters: dict[str, tuple[tuple[str, bool, Any], ...]] = {}
    for tool in _generated_gateway_tools():
        raw_parameters = tool.get("parameters")
        if not isinstance(raw_parameters, list):
            raise ValueError(f"generated tool {tool['name']} lacks parameters")
        decoded: list[tuple[str, bool, Any]] = []
        for raw in raw_parameters:
            if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
                raise ValueError(f"generated tool {tool['name']} has an invalid parameter")
            required = bool(raw.get("required", False))
            decoded.append(
                (
                    str(raw["name"]),
                    not required,
                    raw.get("default"),
                )
            )
        parameters[str(tool["name"])] = tuple(decoded)
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
    start_pattern = re.compile(r"action def\s+(?:<'([^']+)'>\s+)?\w+\s*\{")
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
        identity = match.group(1)
        if not identity or not identity.startswith("operation.vellis."):
            continue
        action_parameters = []
        for parameter, multiplicity, default in re.findall(
            rf"\bin\s+({SYSML_IDENTIFIER})\s*:\s*\w+(\[[^]]+\])?"
            r"(?:\s+(?:default\s*)?=\s*([^;{}]+))?",
            block,
        ):
            action_parameters.append(
                (
                    _identifier_value(parameter),
                    multiplicity == "[0..1]" or bool(default),
                    _model_default(default or None),
                )
            )
        parameters[identity.removeprefix("operation.vellis.")] = tuple(action_parameters)
    return parameters


def _model_tool_parameter_schemas() -> dict[str, dict[str, Any]]:
    text = _without_comments(
        (MODEL_ROOT / "vellis" / "VellisOperations.sysml").read_text(encoding="utf-8")
    )
    schemas: dict[str, dict[str, Any]] = {}
    start_pattern = re.compile(r"action def\s+(?:<'([^']+)'>\s+)?\w+\s*\{")
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
        identity = match.group(1)
        if not identity or not identity.startswith("operation.vellis."):
            continue
        properties: dict[str, Any] = {}
        required: list[str] = []
        block = text[match.start() : end]
        for parameter, type_name, multiplicity, default in re.findall(
            rf"\bin\s+({SYSML_IDENTIFIER})\s*:\s*({SYSML_IDENTIFIER})(\[[^]]+\])?"
            r"(?:\s+(?:default\s*)?=\s*([^;{}]+))?",
            block,
        ):
            name = _identifier_value(parameter)
            value_schema = _vellis_wire_schema(_identifier_value(type_name))
            property_schema = (
                {"anyOf": [value_schema, {"type": "null"}]}
                if multiplicity == "[0..1]"
                else value_schema
            )
            if default:
                property_schema = {**property_schema, "default": _model_default(default)}
            properties[name] = property_schema
            if multiplicity != "[0..1]" and not default:
                required.append(name)
        schemas[identity.removeprefix("operation.vellis.")] = {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }
    return schemas


@functools.cache
def _vellis_wire_inventory() -> tuple[dict[str, Any], dict[str, list[str]]]:
    records: dict[str, Any] = {}
    enums: dict[str, list[str]] = {}
    roots = (MODEL_ROOT / "vellis", MODEL_ROOT / "bibliotek")
    for root in roots:
        for path in sorted(root.rglob("*.sysml")):
            boundary = _audit_model_boundary(path)
            records.update(cast(dict[str, Any], boundary["records"]))
            enums.update(cast(dict[str, list[str]], boundary["enums"]))
    return records, enums


def _vellis_wire_schema(type_name: str, seen: frozenset[str] = frozenset()) -> dict[str, Any]:
    records, enums = _vellis_wire_inventory()
    # The accepted Python realization deliberately encodes this two-field logical
    # record as a positional pair.  Keep that explicit codec visible in the MCP
    # schema instead of projecting the logical record's object representation.
    if type_name == "RtgQueryReturnProperty":
        return {
            "type": "array",
            "prefixItems": [
                {"type": "string"},
                {"type": "array", "items": {"type": "string"}, "minItems": 1},
            ],
            "minItems": 2,
            "maxItems": 2,
        }
    if type_name == "RuntimeReconstructionRequest":
        return {
            "type": "object",
            "properties": {
                "through_runtime_position": {"type": "integer"},
                "checkpoint_references": {"type": "object"},
                "reset_targets": {"type": "boolean", "default": False},
                "external_boundaries": {
                    "type": "array",
                    "items": _vellis_wire_schema("RuntimeExternalBoundaryDisposition", seen),
                },
            },
            "additionalProperties": False,
        }
    if type_name in enums:
        return {
            "type": "string",
            "enum": [re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower() for value in enums[type_name]],
        }
    if type_name in {"String", "Uuid", "JsonRelativePath", "Timestamp"}:
        return {"type": "string"}
    if type_name == "RtgResourceIdentifier":
        return {"type": "string"}
    if type_name == "Boolean":
        return {"type": "boolean"}
    if type_name == "Integer":
        return {"type": "integer"}
    if type_name == "Real":
        return {"type": "number"}
    scalar = _vellis_wire_schema_type(type_name)
    if type_name not in records and scalar is not None and scalar != "object":
        return {"type": scalar}
    if type_name in {"JsonValue", "JsonObject", "JsonScalar"}:
        if type_name == "JsonValue":
            return {}
        if type_name == "JsonScalar":
            return {"type": ["string", "number", "integer", "boolean", "null"]}
        return {"type": "object"}
    fields = records.get(type_name)
    if not isinstance(fields, dict) or type_name in seen:
        return {"type": "object"}
    if type_name.endswith("List") and len(fields) == 1:
        field = next(iter(fields.values()))
        if isinstance(field, dict):
            return {
                "type": "array",
                "items": _vellis_wire_schema(str(field["type"]).rsplit("::", 1)[-1], seen),
            }
    properties: dict[str, Any] = {}
    required: list[str] = []
    for field_name, raw in fields.items():
        if not isinstance(raw, dict):
            continue
        field_schema = _vellis_wire_schema(str(raw["type"]).rsplit("::", 1)[-1], seen | {type_name})
        multiplicity = str(raw.get("multiplicity", "[1]"))
        if "*" in multiplicity:
            field_schema = {"type": "array", "items": field_schema}
        model_name = str(raw.get("model_name", field_name))
        wire_name = re.sub(r"(?<!^)(?=[A-Z])", "_", model_name).lower()
        properties[wire_name] = field_schema
        if multiplicity not in {"[0..1]", "[0..*]"} and raw.get("value_kind") != "default":
            required.append(wire_name)
    result: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if type_name == "RtgSystemSnapshot":
        # A full Vellis snapshot export specializes the system snapshot with a
        # fixed `kind=full` discriminator and is intentionally accepted directly
        # by restore.
        properties["kind"] = {"type": "string", "enum": ["full"]}
    if required:
        result["required"] = required
    return result


def _vellis_wire_schema_type(type_name: str) -> str | None:
    if type_name in {"String", "Uuid", "JsonRelativePath"}:
        return "string"
    if type_name == "Boolean":
        return "boolean"
    if type_name == "Integer":
        return "integer"
    if type_name == "JsonValue":
        return None
    if type_name.endswith("List"):
        return "array"
    if type_name.startswith("Vellis") and type_name.endswith(("Topic", "Format", "Kind", "State")):
        return "string"
    if type_name.startswith("Rtg") and type_name.endswith(("Mode", "Status")):
        return "string"
    return "object"


def _python_tool_description_names() -> set[str]:
    return {str(tool["name"]) for tool in _generated_gateway_tools()}


def _check_generic_mcp_transport_projection() -> list[Finding]:
    """Keep the FastMCP host generic and the generated manifest authoritative."""
    findings: list[Finding] = []
    server_path = ROOT / "apps" / "rtg_knowledge_graph" / "mcp_server.py"
    server_text = server_path.read_text(encoding="utf-8")
    for forbidden in ("RtgMcpToolset", "components.rtg", "def rtg_"):
        if forbidden in server_text:
            findings.append(
                Finding(server_path, f"generic MCP transport retains Vellis coupling: {forbidden}")
            )
    for required in (
        "def build_mcp_server(gateway: McpGateway)",
        "for registration in gateway.registrations:",
        "server.add_tool(_RuntimeGatewayTool(gateway, registration))",
        "await self._gateway.invoke_tool(",
    ):
        if required not in server_text:
            findings.append(
                Finding(server_path, f"generic MCP transport projection omits {required}")
            )

    registration_path = ROOT / "apps" / "rtg_knowledge_graph" / "gateway_registration.py"
    registration_text = registration_path.read_text(encoding="utf-8")
    for required in (
        'joinpath("model_app_manifest.json")',
        'manifest.get("tools")',
        "McpGatewayToolRegistration(",
    ):
        if required not in registration_text:
            findings.append(
                Finding(
                    registration_path,
                    f"generated MCP gateway registration projection omits {required}",
                )
            )
    return findings


def _model_tool_names() -> tuple[str, ...]:
    text = (MODEL_ROOT / "vellis" / "realizations" / "VellisMcpPython.sysml").read_text(
        encoding="utf-8"
    )
    return tuple(re.findall(r'toolName\s*=\s*"([^"]+)"', text))


def _model_tool_descriptions() -> dict[str, str]:
    text = (MODEL_ROOT / "vellis" / "realizations" / "VellisMcpPython.sysml").read_text(
        encoding="utf-8"
    )
    descriptions: dict[str, str] = {}
    for match in re.finditer(r"\bperform action\s+\w+\[[^]]+\]\s*:\s*\w+\s*\{", text):
        block = _extract_braced_block(text, match.start())
        tool_match = re.search(r'toolName\s*=\s*"([^"]+)"', block)
        if tool_match is None:
            continue
        descriptions[tool_match.group(1)] = _documentation(block)
    return descriptions


def _model_tool_capabilities() -> dict[str, dict[str, Any]]:
    text = (MODEL_ROOT / "vellis" / "realizations" / "VellisMcpPython.sysml").read_text(
        encoding="utf-8"
    )
    capabilities: dict[str, dict[str, Any]] = {}
    for block in re.findall(r"@McpToolBinding\s*\{(.*?)\}", text, re.DOTALL):
        name_match = re.search(r'toolName\s*=\s*"([^"]+)"', block)
        lane_match = re.search(r"lane\s*=\s*McpOperationalLane::(\w+)", block)
        audience_match = re.search(r"audience\s*=\s*McpAudienceKind::(\w+)", block)
        if name_match is None or lane_match is None or audience_match is None:
            continue

        def boolean(name: str, source: str = block) -> bool:
            match = re.search(rf"\b{name}\s*=\s*(true|false)", source)
            return match is not None and match.group(1) == "true"

        predecessors_match = re.search(
            r"\brecommendedPredecessors\s*=\s*\((.*?)\)", block, re.DOTALL
        )
        recommended_predecessors = (
            re.findall(r'"([^"]+)"', predecessors_match.group(1))
            if predecessors_match is not None
            else []
        )
        dry_run_match = re.search(r'\bdryRunTool\s*=\s*"([^"]+)"', block)
        capabilities[name_match.group(1)] = {
            "lane": lane_match.group(1),
            "audience": audience_match.group(1),
            "ledgers": boolean("ledgers"),
            "recommended_predecessors": recommended_predecessors,
            "dry_run_tool": dry_run_match.group(1) if dry_run_match is not None else None,
            "annotations": {
                "readOnlyHint": boolean("readOnlyHint"),
                "destructiveHint": boolean("destructiveHint"),
                "idempotentHint": boolean("idempotentHint"),
                "openWorldHint": boolean("openWorldHint"),
            },
        }
    return capabilities


def _model_operation_ids() -> tuple[str, ...]:
    text = (MODEL_ROOT / "vellis" / "VellisOperations.sysml").read_text(encoding="utf-8")
    return tuple(re.findall(r"\baction def\s+<'(operation\.vellis\.[^']+)'>", text))


def _model_operation_blocks() -> dict[str, str]:
    text = (MODEL_ROOT / "vellis" / "VellisOperations.sysml").read_text(encoding="utf-8")
    blocks: dict[str, str] = {}
    for match in re.finditer(r"\baction def\s+(?:<'([^']+)'>\s+)?\w+\s*\{", text):
        block = _extract_braced_block(text, match.start())
        identity = match.group(1)
        if identity and identity.startswith("operation.vellis."):
            blocks[identity.removeprefix("operation.vellis.")] = block
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
        "contract.vellis.facade.runtime_projection",
    ):
        if contract_id not in operations_text:
            findings.append(Finding(operations_path, f"Vellis facade omits {contract_id}"))
    facade_block = _definition_block(operations_text, "part def", "VellisApplicationFacade")
    for performance in re.finditer(r"perform action\s+(\w+)\[[^]]+\]\s*:\s*(\w+)", facade_block):
        feature = performance.group(1)
        performance_has_effect = False
        body_start = facade_block.find("{", performance.end())
        statement_end = facade_block.find(";", performance.end())
        if body_start != -1 and (statement_end == -1 or body_start < statement_end):
            performance_body = _extract_braced_block(facade_block, body_start)
            performance_has_effect = bool(
                _documentation(performance_body)
                or re.search(r"\baction\s+\w+\s*(?::\s*\w+)?\s*\{", performance_body)
            )
        dependency_has_effect = bool(
            re.search(
                rf"dependency\s+\w+\s+from\s+{re.escape(feature)}\s+to\s+[\w.]+\s*\{{"
                r".*?\bdoc\s*/\*",
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
        "enum restore_pre_cutover_snapshot;",
        "enum cutover_applied;",
        "contract.rtg.controller.operation_results",
        "contract.rtg.controller.intentional_boundary",
    )
    for term in required_controller_terms:
        if term not in controller_text:
            findings.append(Finding(operations_path, f"controller black-box profile omits {term}"))
    for forbidden in (
        "sqlStorage",
        "ReplayLedger",
        "VerifyReplayFromLedger",
        "ListMigrationHistory",
        "FlushLedgerFailures",
        "ledgerPosition",
        "transactionId",
    ):
        if forbidden in controller_text:
            findings.append(
                Finding(operations_path, f"controller retains runtime-owned term {forbidden}")
            )
    return findings


def _vellis_roles() -> dict[str, str]:
    text = (MODEL_ROOT / "vellis" / "Vellis.sysml").read_text(encoding="utf-8")
    role_types = dict(
        re.findall(
            r"(?m)^\s*part\s+(\w+)\s*:\s*"
            r"(MessageRuntime|JsonFileStorage|RtgGraph|RtgSchema|RtgConstraints|RtgMigration|"
            r"RtgQueryEngine|RtgChangeValidator|RtgController)\s*;",
            text,
        )
    )
    type_to_id = {
        "MessageRuntime": "component.runtime.message_runtime",
        "JsonFileStorage": "component.storage.json_file",
        "RtgGraph": "component.rtg.graph",
        "RtgSchema": "component.rtg.schema",
        "RtgConstraints": "component.rtg.constraints",
        "RtgMigration": "component.rtg.migration",
        "RtgQueryEngine": "component.rtg.query",
        "RtgChangeValidator": "component.rtg.change_validation",
        "RtgController": "component.rtg.controller",
    }
    return {role: type_to_id[type_name] for role, type_name in role_types.items()}


def _check_contract_satisfaction() -> list[Finding]:
    """Validate native identity bindings for persistent collaborator roles.

    Invocation-scoped collaborators are action parameters and need no composition binding.
    A component occurrence that retains a collaborator declares a referential part role; the
    application binds that role to exactly one compatible occurrence when its multiplicity is one.
    """
    path = MODEL_ROOT / "vellis" / "Vellis.sysml"
    text = path.read_text(encoding="utf-8")
    role_types = dict(re.findall(r"(?m)^\s*part\s+(\w+)\s*:\s*(\w+)\s*;", text))
    findings: list[Finding] = []
    contract_paths = [
        *COMPONENT_MODEL_ROOT.glob("*.sysml"),
        MODEL_ROOT / "vellis" / "VellisOperations.sysml",
    ]
    model_text = "\n".join(
        model_path.read_text(encoding="utf-8")
        for model_path in contract_paths
        if model_path.exists()
    )
    parents = {
        name: parent
        for name, parent in re.findall(
            r"\bpart def\s+(?:<'[^']+'>\s+)?(\w+)\s*:>\s*(\w+)\s*\{", model_text
        )
    }
    bindings: dict[tuple[str, str], list[str]] = {}
    for consumer, feature, provider in re.findall(r"\bbind\s+(\w+)\.(\w+)\s*=\s*(\w+)\s*;", text):
        bindings.setdefault((consumer, feature), []).append(provider)

    for consumer_role, consumer_type in role_types.items():
        definition = _definition_block(model_text, "part def", consumer_type)
        for match in re.finditer(r"\bref part\s+(\w+)\s*(\[[^]]+\])\s*:\s*(\w+)\s*;", definition):
            feature, multiplicity, required_type = match.groups()
            providers = bindings.get((consumer_role, feature), [])
            if multiplicity == "[1]" and len(providers) != 1:
                findings.append(
                    Finding(
                        path,
                        f"{consumer_role}.{feature} requires exactly one bound {required_type}; "
                        f"found {len(providers)}",
                    )
                )
            for provider_role in providers:
                provider_type = role_types.get(provider_role)
                if provider_type is None:
                    findings.append(Finding(path, f"binding names unknown role {provider_role}"))
                    continue
                ancestor = provider_type
                while ancestor in parents and ancestor != required_type:
                    ancestor = parents[ancestor]
                if ancestor != required_type:
                    findings.append(
                        Finding(
                            path,
                            f"binding type mismatch: {consumer_role}.{feature} requires "
                            f"{required_type}, but {provider_role} is {provider_type}",
                        )
                    )

    declared_bindings = {
        (consumer, feature)
        for consumer, feature, _ in re.findall(r"\bbind\s+(\w+)\.(\w+)\s*=\s*(\w+)\s*;", text)
    }
    for consumer, feature in declared_bindings:
        consumer_type = role_types.get(consumer)
        definition = _definition_block(model_text, "part def", consumer_type or "")
        if not re.search(rf"\bref part\s+{re.escape(feature)}\b", definition):
            findings.append(Finding(path, f"binding targets unknown role {consumer}.{feature}"))
    return findings


def _check_allowed_profile(files: list[Path]) -> list[Finding]:
    profile_path = ALLOWED_CONSTRUCTS_PATH
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
    """Keep reusable component implementations independent of applications."""
    findings: list[Finding] = []
    for model_path in COMPONENT_MODEL_ROOT.glob("component.*.sysml"):
        text = model_path.read_text(encoding="utf-8")
        component_id = _component_id(text)
        if not component_id:
            continue
        code_root = ROOT / "components" / Path(*component_id.removeprefix("component.").split("."))
        if not code_root.is_dir():
            continue
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
                if imported == "apps" or imported.startswith("apps.")
            )
            if violations:
                findings.append(
                    Finding(
                        python_path,
                        f"{component_id} imports application modules: {violations}",
                    )
                )
    return findings


def _check_resource_scaling_antipatterns(paths: tuple[Path, ...] | None = None) -> list[Finding]:
    """Reject whole-state mechanics from ordinary production operations."""
    candidates = paths or tuple(
        path
        for root in (ROOT / "components", ROOT / "apps")
        for path in root.rglob("*.py")
        if "tests" not in path.parts
    )
    findings: list[Finding] = []
    canonical_store_names = {
        "_anchors",
        "_data_objects",
        "_links",
        "_anchor_data",
        "_definitions",
        "_constraints",
        "_migrations",
    }
    for path in candidates:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as error:
            findings.append(Finding(path, f"cannot inspect resource scaling: {error}"))
            continue
        try:
            relative = path.relative_to(ROOT).as_posix()
        except ValueError:
            relative = path.as_posix()
        allowed_functions = STATE_TRANSFER_ALLOWLIST.get(relative, frozenset())

        class ScalingVisitor(ast.NodeVisitor):
            def __init__(self, source_path: Path, permitted_functions: frozenset[str]) -> None:
                self.functions: list[str] = []
                self.source_path = source_path
                self.allowed_functions = permitted_functions

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                self.functions.append(node.name)
                self.generic_visit(node)
                self.functions.pop()

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                self.functions.append(node.name)
                self.generic_visit(node)
                self.functions.pop()

            def visit_Call(self, node: ast.Call) -> None:
                current = self.functions[-1] if self.functions else "<module>"
                method = node.func.attr if isinstance(node.func, ast.Attribute) else None
                if method in STATE_TRANSFER_METHODS and current not in self.allowed_functions:
                    findings.append(
                        Finding(
                            self.source_path,
                            f"line {node.lineno}: ordinary operation {current} calls "
                            f"whole-state {method}; use a component-local batch or add a "
                            "narrow explicit state-transfer rationale",
                        )
                    )
                is_deepcopy = (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "copy"
                    and node.func.attr == "deepcopy"
                )
                if is_deepcopy and node.args:
                    argument = node.args[0]
                    if (
                        isinstance(argument, ast.Attribute)
                        and argument.attr in canonical_store_names
                    ):
                        findings.append(
                            Finding(
                                self.source_path,
                                f"line {node.lineno}: {current} deep-copies complete canonical "
                                f"store {argument.attr}",
                            )
                        )
                self.generic_visit(node)

        ScalingVisitor(path, allowed_functions).visit(tree)
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
    findings.extend(_check_connected_formal_semantics(files))
    findings.extend(_check_discriminated_public_alternatives(files))
    findings.extend(_check_requirement_and_verification_semantics(files))
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
        for stable_id in re.findall(r"<'([^']+\.[^']+)'>", text):
            if stable_id in stable_ids:
                findings.append(
                    Finding(
                        path, f"duplicate stable ID {stable_id} (also in {stable_ids[stable_id]})"
                    )
                )
            stable_ids[stable_id] = path

    lock_path = LANGUAGE_LOCK_PATH
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
        if len(models) != 13:
            findings.append(
                Finding(COMPONENT_MODEL_ROOT, f"expected 13 components, found {len(models)}")
            )
        findings.extend(_check_forbidden_component_imports())
        findings.extend(_check_protocol_action_coverage())
        findings.extend(_check_protocol_action_signatures())
        findings.extend(_check_protocol_value_fields())
        findings.extend(_check_component_contract_completeness())
        findings.extend(_check_state_access_semantics())
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
                    GENERATED_MANIFEST,
                    "MCP descriptions do not match the exact tool surface",
                )
            )
        findings.extend(_check_generic_mcp_transport_projection())
        toolset_path = ROOT / "apps" / "rtg_knowledge_graph" / "mcp_toolset.py"
        toolset_text = toolset_path.read_text(encoding="utf-8")
        if (
            'joinpath("model_app_manifest.json")' not in toolset_text
            or "TOOL_NAMES, TOOL_DESCRIPTIONS, _MODELED_TOOL_CAPABILITIES = "
            "_load_model_tool_metadata()"
            not in toolset_text
            or re.search(r"TOOL_DESCRIPTIONS\s*:\s*dict[^=]*=\s*\{", toolset_text)
        ):
            findings.append(
                Finding(
                    toolset_path,
                    "MCP runtime tool names and descriptions must come from the generated "
                    "model application manifest",
                )
            )
        realization_text = (
            MODEL_ROOT / "vellis" / "realizations" / "VellisMcpPython.sysml"
        ).read_text(encoding="utf-8")
        binding_blocks = re.findall(r"@McpToolBinding\s*\{(.*?)\}", realization_text, re.DOTALL)
        model_descriptions = _model_tool_descriptions()
        if (
            len(binding_blocks) != 27
            or set(model_descriptions) != set(python_tools)
            or any(not description.strip() for description in model_descriptions.values())
        ):
            findings.append(
                Finding(
                    MODEL_ROOT / "vellis" / "realizations" / "VellisMcpPython.sysml",
                    "each MCP realization must document its exact non-empty tool description",
                )
            )
        if re.search(r"\b(?:descriptionSymbol|resultMapping|errorMapping)\b", realization_text):
            findings.append(
                Finding(
                    MODEL_ROOT / "vellis" / "realizations" / "VellisMcpPython.sysml",
                    "MCP realization duplicates native documentation or typed encoding semantics",
                )
            )
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
        findings.extend(_check_native_behavior_realizations())
        findings.extend(_check_vellis_runtime_topology_model())

    if scope == "all":
        findings.extend(_check_view_semantics())
        findings.extend(_check_resource_scaling_antipatterns())

    if require_external:
        validator = _read_json(lock_path).get("validator", {})
        command = validator.get("command") if isinstance(validator, dict) else None
        if not command:
            findings.append(
                Finding(lock_path, "external formal validator is not pinned/configured")
            )
        else:
            expanded_command = [
                sys.executable if str(part) == "{python}" else str(part) for part in command
            ]
            result = subprocess.run(
                expanded_command,
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
        rf"\b(in|out)\s+(?:ref\s+)?(?:attribute\s+|part\s+|item\s+)?"
        rf"({SYSML_IDENTIFIER})(\[[^]]+\])?((?:\s+(?:ordered|nonunique))*)"
        rf"\s*:\s*([\w:]+)(\[[^]]+\])?"
        r"(?:\s+(?:default\s*)?=\s*([^;{}]+))?",
        block,
    )
    if not features:
        return "—"
    return "; ".join(
        f"{direction} `{_identifier_value(name)}: {type_name}{before or after or ''}"
        f"{modifiers}`" + (f" = `{default.strip()}`" if default else "")
        for direction, name, before, modifiers, type_name, after, default in features
    )


def _part_definition_chain(text: str, name: str, seen: set[str] | None = None) -> list[str]:
    seen = set() if seen is None else seen
    if name in seen:
        return []
    seen.add(name)
    match = re.search(
        rf"\bpart def\s+{OPTIONAL_IDENTIFICATION}{re.escape(name)}"
        r"(?:\s*:>\s*(\w+))?\s*\{",
        text,
    )
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
        (
            _identifier_value(field_name),
            multiplicity + (" ordered" if ordering else ""),
            type_name,
            default,
        )
        for field_name, multiplicity, ordering, type_name, default in re.findall(
            rf"\b(?:ref\s+)?(?:attribute|item)\s+({SYSML_IDENTIFIER})"
            r"(\[[^]]+\])?(?:\s+(ordered))?\s*:\s*([\w:]+)"
            r"(?:\s+(?:default\s*)?=\s*([^;{}]+))?",
            block,
        )
    )
    return fields


def _component_page(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    all_model_text = "\n".join(source.read_text(encoding="utf-8") for source in _sysml_files("all"))
    component_id = _component_id(text) or path.stem
    component_name = _component_definition_name(text) or path.stem
    component_block = _definition_block(text, "part def", component_name)
    component_contract_blocks = _part_definition_chain(text, component_name)
    complete_component_contract = "\n".join(component_contract_blocks) or component_block
    status = _component_model_statuses().get(component_id, "unknown")
    purpose = _documentation(component_block) or "See the modeled contracts and invariants below."
    diagram = _component_diagrams().get(component_id)

    action_definitions = {
        match.group(1): _extract_braced_block(text, match.start())
        for match in re.finditer(rf"\baction def\s+{OPTIONAL_IDENTIFICATION}(\w+)\s*\{{", text)
    }
    provided = [
        (_identifier_value(feature), action_type)
        for feature, action_type in re.findall(
            rf"perform action\s+({SYSML_IDENTIFIER})\[[^]]+\]\s*:\s*(\w+)",
            complete_component_contract,
        )
    ]
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

    required_rows = ["| Role | Kind | Referenced type | Multiplicity |", "|---|---|---|---|"]
    for kind, feature, contract in required:
        feature_match = re.search(
            rf"ref {kind}\s+{re.escape(feature)}(\[[^]]+\])?\s*:"
            rf"\s*{re.escape(contract)}(?:\s*\{{(.*?)\}}|\s*;)",
            complete_component_contract,
            flags=re.DOTALL,
        )
        cardinality = feature_match.group(1) if feature_match and feature_match.group(1) else "—"
        required_rows.append(f"| `{feature}` | `{kind}` | `{contract}` | `{cardinality}` |")
    if len(required_rows) == 2:
        required_rows.append("| — | — | — | No retained collaborator roles. |")

    state_rows = ["| State feature | Type | Ownership | Meaning |", "|---|---|---|---|"]
    state_pattern = re.compile(
        rf"(?m)^\s*(ref\s+|derived\s+)?(?:attribute|item)\s+({SYSML_IDENTIFIER})"
        r"(?:\[[^]]+\])?\s*:\s*([\w:]+)(?:\s*\{(.*?)\}|\s*;)",
        flags=re.DOTALL,
    )
    for match in state_pattern.finditer(complete_component_contract):
        modifier, raw_name, type_name, body = match.groups()
        name = _identifier_value(raw_name)
        normalized_modifier = (modifier or "").strip()
        ownership = (
            "referenced"
            if normalized_modifier == "ref"
            else "derived"
            if normalized_modifier == "derived"
            else "owned"
        )
        state_rows.append(
            f"| `{name}` | `{type_name}` | `{ownership}` | "
            f"{_documentation(body or '') or 'Typed component state.'} |"
        )
    if len(state_rows) == 2:
        state_rows.append("| — | — | — | This component owns no abstract state. |")

    effect_rows = [
        "| Action | State / collaborator | Access | Modeled effect |",
        "|---|---|---|---|",
    ]
    for match in re.finditer(
        rf"dependency\s+\w+\s+from\s+({SYSML_IDENTIFIER})\s+to\s+([\w.]+)\s*\{{",
        complete_component_contract,
    ):
        body = _extract_braced_block(complete_component_contract, match.start())
        effect = _documentation(body)
        access = re.search(r"kind\s*=\s*StateAccessKind::(\w+)", body)
        if effect:
            source = _identifier_value(match.group(1))
            target = match.group(2)
            access_kind = access.group(1) if access else "dependency"
            effect_rows.append(f"| `{source}` | `{target}` | `{access_kind}` | {effect} |")
    for feature, _ in provided:
        feature_match = re.search(
            rf"perform action\s+{re.escape(feature)}\[[^]]+\]\s*:\s*\w+\s*\{{",
            complete_component_contract,
        )
        if not feature_match:
            continue
        body = _extract_braced_block(complete_component_contract, feature_match.start())
        effect = _documentation(body)
        if effect and not any(f"| `{feature}` |" in row for row in effect_rows):
            effect_rows.append(f"| `{feature}` | — | `declared` | {effect} |")
    if len(effect_rows) == 2:
        effect_rows.append("| — | — | — | Effects are stated by the requirements below. |")

    behavior_rows = [
        "| Public action | Nested semantic actions | Observable successions |",
        "|---|---|---|",
    ]
    for feature, _ in provided:
        feature_match = re.search(
            rf"perform action\s+{re.escape(feature)}\[[^]]+\]\s*:\s*\w+\s*\{{",
            complete_component_contract,
        )
        if not feature_match:
            continue
        block = _extract_braced_block(complete_component_contract, feature_match.start())
        nested = re.findall(r"\baction\s+(?!def\b)(\w+)(?:\s*:\s*(\w+))?\s*(?:\{|;)", block)
        successions = [" ".join(value.split()) for value in re.findall(r"\bfirst\s+.*?;", block)]
        if nested or successions:
            nested_text = ", ".join(
                f"`{name}: {type_name or 'local'}`" for name, type_name in nested
            )
            behavior_rows.append(
                f"| `{feature}` | "
                f"{nested_text or '—'} | "
                f"{'; '.join(f'`{value}`' for value in successions) or '—'} |"
            )
    if len(behavior_rows) == 2:
        behavior_rows.append("| — | — | No action decomposition required at this boundary. |")

    satisfiers = _satisfier_map(text)
    requirement_rows = [
        "| Stable ID | Subject | Satisfier | Required constraint |",
        "|---|---|---|---|",
    ]
    for match in re.finditer(r"\brequirement\s+<'([^']+)'>\s+(\w+)\s*\{", text):
        block = _extract_braced_block(text, match.start())
        subject = re.search(r"\bsubject\s+\w+\s*:\s*([\w:]+)", block)
        requirement_rows.append(
            f"| `{match.group(1)}` | `{subject.group(1) if subject else 'unknown'}` | "
            f"`{satisfiers.get(match.group(2), 'unsatisfied-draft')}` | "
            f"{_documentation(block) or 'Formal modeled predicate.'} |"
        )
    if len(requirement_rows) == 2:
        requirement_rows.append("| — | — | — | No component-scoped requirements. |")

    value_rows = [
        "| Public definition | Kind | Fields | Meaning |",
        "|---|---|---|---|",
    ]
    for match in re.finditer(r"\b(attribute|item) def\s+(\w+)(?:\s*:>\s*\w+)?\s*\{", text):
        definition_block = _extract_braced_block(text, match.start())
        fields = _public_field_signatures(all_model_text, match.group(2))
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
            f"| `{match.group(2)}` | `{match.group(1)}` | {rendered_fields} | {meaning} |"
        )
    if len(value_rows) == 2:
        value_rows.append("| — | — | — | No component-owned public values. |")

    enum_rows = ["| Enumeration | Logical literals |", "|---|---|"]
    for match in re.finditer(r"\benum def\s+(\w+)\s*\{", text):
        block = _extract_braced_block(text, match.start())
        rendered_values: list[str] = []
        for value_match in re.finditer(r"\benum\s+(?:'([^']+)'|(\w+))\s*(;|\{)", block):
            quoted_name, model_name, _ = value_match.groups()
            rendered_values.append(f"`{quoted_name or model_name}`")
        enum_rows.append(f"| `{match.group(1)}` | {', '.join(rendered_values) or '—'} |")
    if len(enum_rows) == 2:
        enum_rows.append("| — | No component-owned public enumerations. |")

    verification_rows = [
        "| Verification | Subject | Objectives | Evidence |",
        "|---|---|---|---|",
    ]
    for match in re.finditer(r"\bverification def\s+(\w+)\s*\{", text):
        block = _extract_braced_block(text, match.start())
        objectives = re.findall(r"\bverify\s+(\w+)\s*;", block)
        evidence = re.search(r'evidenceId\s*=\s*"([^"]+)"', block)
        subject = re.search(r"\bsubject\s+\w+\s*:\s*([\w:]+)", block)
        verification_rows.append(
            f"| `{match.group(1)}` | `{subject.group(1) if subject else 'unknown'}` | "
            f"{', '.join(f'`{name}`' for name in objectives) or '—'} | "
            f"`{evidence.group(1)}` |"
            if evidence
            else (
                f"| `{match.group(1)}` | `{subject.group(1) if subject else 'unknown'}` | "
                f"{', '.join(f'`{name}`' for name in objectives) or '—'} | — |"
            )
        )
    if len(verification_rows) == 2:
        verification_rows.append("| — | — | — | No boundary verification modeled. |")

    sections = [
        f"# {component_id}",
        "",
        "Generated from textual SysML v2 by `just model-render` as a non-normative reading "
        "projection; do not edit by hand.",
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
        "## Retained collaborator roles",
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
        "## Native action behavior",
        "",
        *behavior_rows,
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
    ]
    if diagram is not None:
        svg_path = f"../diagrams/{diagram.name}.svg"
        puml_path = f"../diagrams/{diagram.name}.puml"
        sections.extend(
            [
                "## Diagram",
                "",
                f"![{component_id} contract diagram]({svg_path})",
                "",
                f"[PlantUML source]({puml_path})",
                "",
            ]
        )
    sections.extend(
        [
            "Equivalent private algorithms, helpers, storage layouts, and "
            "implementation-language inheritance remain implementation choices.",
            "",
        ]
    )
    return "\n".join(sections)


def _registered_diagrams() -> tuple[DiagramSpec, ...]:
    return discover_diagrams(_read_json(GENERATED_FORMAL_INDEX))


def _component_diagrams() -> dict[str, DiagramSpec]:
    result: dict[str, DiagramSpec] = {}
    for spec in _registered_diagrams():
        suffix = ".contract"
        if spec.product == "bibliotek" and spec.name.endswith(suffix):
            result[spec.name.removesuffix(suffix)] = spec
    return result


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

    diagram_rows = ["| Diagram ID | SVG | PlantUML |", "|---|---|---|"]
    for spec in _registered_diagrams():
        diagram_rows.append(
            f"| `{spec.diagram_id}` | [diagram](diagrams/{spec.name}.svg) | "
            f"[source](diagrams/{spec.name}.puml) |"
        )

    component_models = {
        path: path.read_text(encoding="utf-8")
        for path in sorted(COMPONENT_MODEL_ROOT.glob("component.*.sysml"))
    }
    definition_owners: dict[str, str] = {}
    for text in component_models.values():
        for component_id, definition in re.findall(
            r"\bpart def\s+<'(component\.[^']+)'>\s+(\w+)", text
        ):
            definition_owners[definition] = component_id

    dependency_rows = [
        "| Consumer | Retained role | Required component type | Provider |",
        "|---|---|---|---|",
    ]
    for text in component_models.values():
        component_id = _component_id(text)
        component_name = _component_definition_name(text)
        if not component_id or not component_name:
            continue
        component_block = _definition_block(text, "part def", component_name)
        for role, required_type in re.findall(
            r"\bref part\s+(\w+)\s*\[[^]]+\]\s*:\s*(\w+)\s*;", component_block
        ):
            provider = definition_owners.get(required_type, "external capability")
            dependency_rows.append(
                f"| `{component_id}` | `{role}` | `{required_type}` | `{provider}` |"
            )
    if len(dependency_rows) == 2:
        dependency_rows.append("| — | — | — | No retained component dependencies. |")

    umbrella = (BIBLIOTEK_MODEL_ROOT / "Bibliotek.sysml").read_text(encoding="utf-8")
    shared_packages = [
        package
        for package in re.findall(r"\bpublic import\s+(\w+)::\*\s*;", umbrella)
        if package in {"BibliotekSoftwareValues", "BibliotekRtgDiagnostics"}
    ]
    shared_rows = ["| Shared package | Ownership |", "|---|---|"]
    shared_rows.extend(
        f"| `{package}` | Bibliotek-wide public values with no single component owner. |"
        for package in shared_packages
    )
    shared_sources = {
        "BibliotekSoftwareValues": BIBLIOTEK_MODEL_ROOT / "shared-values" / "SoftwareValues.sysml",
        "BibliotekRtgDiagnostics": BIBLIOTEK_MODEL_ROOT / "shared-values" / "RtgDiagnostics.sysml",
    }
    shared_text = "\n".join(
        shared_sources[package].read_text(encoding="utf-8") for package in shared_packages
    )
    shared_value_rows = [
        "| Package | Public definition | Kind | Fields / literals | Meaning |",
        "|---|---|---|---|---|",
    ]
    for package in shared_packages:
        text = shared_sources[package].read_text(encoding="utf-8")
        for match in re.finditer(r"\b(abstract\s+)?(attribute|item) def\s+(\w+)", text):
            abstract, kind, name = match.groups()
            block = _extract_braced_block(text, match.start())
            fields = _public_field_signatures(shared_text, name)
            rendered_fields = ", ".join(
                f"`{field}{multiplicity}: {type_name}`"
                + (f" = `{default.strip()}`" if default else "")
                for field, multiplicity, type_name, default in fields
            )
            shared_value_rows.append(
                f"| `{package}` | `{name}` | `{'abstract ' if abstract else ''}{kind}` | "
                f"{rendered_fields or '—'} | "
                f"{_documentation(block) or 'Defined by its typed alternatives or fields.'} |"
            )
        for match in re.finditer(r"\benum def\s+(\w+)\s*\{", text):
            block = _extract_braced_block(text, match.start())
            literals = ", ".join(
                f"`{_identifier_value(literal)}`"
                for literal in re.findall(rf"\benum\s+({SYSML_IDENTIFIER})\s*;", block)
            )
            shared_value_rows.append(
                f"| `{package}` | `{match.group(1)}` | `enum` | {literals or '—'} | "
                f"{_documentation(block) or 'Closed public literal vocabulary.'} |"
            )
    return "\n".join(
        [
            "# Bibliotek model reference",
            "",
            "Generated from textual SysML v2 by `just model-render` as a non-normative reading "
            "projection; do not edit by hand.",
            "",
            "Bibliotek is a reusable SysML library package. It imports the generic modeling "
            "foundation privately and publicly exposes its supported component and shared-value "
            "packages. It has no dependency on Vellis or its realizations.",
            "",
            "Review the cross-model [architecture projections](../architecture/index.md) for "
            "package layers, component context, application composition, runtime topology, and "
            "traceability matrices.",
            "",
            "## Components",
            "",
            *rows,
            "",
            "## Diagrams",
            "",
            *diagram_rows,
            "",
            "## Shared public packages",
            "",
            *shared_rows,
            "",
            "## Shared public values",
            "",
            *shared_value_rows,
            "",
            "## Retained component dependency topology",
            "",
            *dependency_rows,
            "",
        ]
    )


def _render_operation_summary() -> str:
    operation_text = (MODEL_ROOT / "vellis" / "VellisOperations.sysml").read_text(encoding="utf-8")
    starter = _starter_schema_data()
    starter_definitions = [
        item["definition"]
        for item in starter["knowledge_changes"]["schema_changes"]["definition_writes"]
    ]
    starter_rows = [
        "| Anchor | Required facts | Fields |",
        "|---|---|---|",
    ]
    facts_by_key = {
        definition["type_key"]: definition
        for definition in starter_definitions
        if definition["kind"] == "data_object"
    }
    for definition in starter_definitions:
        if definition["kind"] != "anchor":
            continue
        facts_key = definition["payload"]["required_data_types"][0]
        properties = facts_by_key[facts_key]["payload"]["properties"]
        fields = ", ".join(
            f"`{name}`{' (required)' if rule['required'] else ''}"
            for name, rule in properties.items()
        )
        starter_rows.append(f"| `{definition['type_key']}` | `{facts_key}` | {fields} |")
    starter_link_rows = [
        "| Link | Allowed sources | Allowed targets |",
        "|---|---|---|",
    ]
    for definition in starter_definitions:
        if definition["kind"] != "link":
            continue
        sources = ", ".join(f"`{value}`" for value in definition["payload"]["allowed_source_types"])
        targets = ", ".join(f"`{value}`" for value in definition["payload"]["allowed_target_types"])
        starter_link_rows.append(f"| `{definition['type_key']}` | {sources} | {targets} |")
    operation_blocks: dict[str, str] = {}
    for match in re.finditer(r"\baction def\s+(?:<'([^']+)'>\s+)?\w+\s*\{", operation_text):
        block = _extract_braced_block(operation_text, match.start())
        identity = match.group(1)
        if identity and identity.startswith("operation.vellis."):
            operation_blocks[identity.removeprefix("operation.vellis.")] = block
    facade_block = _definition_block(operation_text, "part def", "VellisApplicationFacade")
    facade_features = {
        action_type: feature
        for feature, action_type in re.findall(
            r"perform action\s+(\w+)\[[^]]+\]\s*:\s*(\w+)", facade_block
        )
    }
    controller_calls: dict[str, list[str]] = {}
    for action_type, feature in facade_features.items():
        match = re.search(
            rf"perform action\s+{re.escape(feature)}\[[^]]+\]\s*:\s*{action_type}\s*\{{",
            facade_block,
        )
        if match:
            block = _extract_braced_block(facade_block, match.start())
            controller_calls[feature] = re.findall(r"\baction\s+\w+\s*:\s*(\w+)", block)
    realization_text = (MODEL_ROOT / "vellis" / "realizations" / "VellisMcpPython.sysml").read_text(
        encoding="utf-8"
    )
    adapter_block = _definition_block(realization_text, "part def", "VellisMcpAdapter")
    gateway_registrations = {
        action_type: feature
        for feature, action_type in re.findall(
            r"perform action\s+(\w+)\[[^]]+\]\s*:\s*(\w+)", adapter_block
        )
    }
    action_types = {
        identity.removeprefix("operation.vellis."): action_type
        for identity, action_type in re.findall(
            r"action def\s+<'(operation\.vellis\.[^']+)'>\s+(\w+)", operation_text
        )
    }
    rows = [
        "| # | Tool | Façade / delegated realization | Signature | Principal failures | Outcome |",
        "|---:|---|---|---|---|---|",
    ]
    for index, tool in enumerate(_model_tool_names(), 1):
        block = operation_blocks.get(tool, "")
        failure = re.search(r"errorIds\s*=\s*\((.*?)\)", block, flags=re.DOTALL)
        failures = (
            ", ".join(f"`{name}`" for name in re.findall(r'"([^"]+)"', failure.group(1)))
            if failure
            else "—"
        )
        facade_feature = facade_features.get(action_types.get(tool, ""), "unmapped")
        calls = controller_calls.get(facade_feature, [])
        registration = gateway_registrations.get(action_types.get(tool, ""), "unmapped")
        realization = (
            f"`{facade_feature}` → "
            f"{', '.join(f'`{call}`' for call in calls) or '`application-local`'} → "
            f"`{registration}` registration → `gateway.invokeTool`"
        )
        rows.append(
            f"| {index} | `{tool}` | {realization} | {_feature_signature(block)} | "
            f"{failures or 'None'} | "
            f"{_documentation(block) or 'See the typed façade action.'} |"
        )
    role_rows = ["| Application role | Bibliotek component |", "|---|---|"]
    role_rows.extend(
        f"| `{role}` | `{component_id}` |" for role, component_id in _vellis_roles().items()
    )
    local_realization_text = (
        MODEL_ROOT / "vellis" / "realizations" / "VellisLocalPython.sysml"
    ).read_text(encoding="utf-8")
    realization_definitions: dict[str, tuple[str, str]] = {}
    for definition in re.finditer(r"\bpart def\s+(\w+)\s*:>\s*(\w+)\s*\{", local_realization_text):
        block = _extract_braced_block(local_realization_text, definition.start())
        symbol = re.search(r'\bsymbol\s*=\s*"([^"]+)"', block)
        if symbol:
            realization_definitions[definition.group(1)] = (definition.group(2), symbol.group(1))
    python_role_rows = [
        "| Application role | Logical type | Python realization | Implementation symbol |",
        "|---|---|---|---|",
    ]
    for role, realization in re.findall(
        r"\bpart\s+:>>\s+(\w+)\s*:\s*(\w+)\s*;", local_realization_text
    ):
        logical_type, symbol = realization_definitions.get(realization, ("unmapped", "unmapped"))
        python_role_rows.append(f"| `{role}` | `{logical_type}` | `{realization}` | `{symbol}` |")
    use_case_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((MODEL_ROOT / "vellis" / "use-cases").glob("*.sysml"))
    )
    use_case_rows = [
        "| Actor-visible use case | Objective | Realized application actions |",
        "|---|---|---|",
    ]
    for definition in re.finditer(r"\buse case def\s+(\w+)\s*\{", use_case_text):
        name = definition.group(1)
        definition_block = _extract_braced_block(use_case_text, definition.start())
        usage = re.search(rf"\buse case\s+\w+\s*:\s*{name}\s*\{{", use_case_text)
        usage_block = _extract_braced_block(use_case_text, usage.start()) if usage else ""
        actions = [
            (_identifier_value(feature), action)
            for feature, action in re.findall(
                rf"\baction\s+({SYSML_IDENTIFIER})\s*:\s*(\w+)", usage_block
            )
        ]
        use_case_rows.append(
            f"| `{name}` | {_documentation(definition_block) or 'Modeled actor outcome.'} | "
            f"{', '.join(f'`{feature}: {action}`' for feature, action in actions) or '—'} |"
        )

    contract_texts = [
        (MODEL_ROOT / "vellis" / "Vellis.sysml").read_text(encoding="utf-8"),
        operation_text,
        realization_text,
    ]
    contract_rows = [
        "| Stable ID | Subject | Satisfier | Required constraint |",
        "|---|---|---|---|",
    ]
    verification_rows = [
        "| Verification | Subject | Objectives | Evidence |",
        "|---|---|---|---|",
    ]
    for contract_text in contract_texts:
        satisfiers = _satisfier_map(contract_text)
        for requirement in re.finditer(r"\brequirement\s+<'([^']+)'>\s+(\w+)\s*\{", contract_text):
            block = _extract_braced_block(contract_text, requirement.start())
            subject = re.search(r"\bsubject\s+\w+\s*:\s*([\w:]+)", block)
            contract_rows.append(
                f"| `{requirement.group(1)}` | `{subject.group(1) if subject else 'unknown'}` | "
                f"`{satisfiers.get(requirement.group(2), 'unsatisfied')}` | "
                f"{_documentation(block) or 'Formal modeled predicate.'} |"
            )
        for verification in re.finditer(r"\bverification def\s+(\w+)\s*\{", contract_text):
            block = _extract_braced_block(contract_text, verification.start())
            subject = re.search(r"\bsubject\s+\w+\s*:\s*([\w:]+)", block)
            evidence = re.search(r'evidenceId\s*=\s*"([^"]+)"', block)
            objectives = re.findall(r"\bverify\s+(\w+)\s*;", block)
            verification_rows.append(
                f"| `{verification.group(1)}` | `{subject.group(1) if subject else 'unknown'}` | "
                f"{', '.join(f'`{objective}`' for objective in objectives) or '—'} | "
                f"`{evidence.group(1) if evidence else 'unbound'}` |"
            )
    return "\n".join(
        [
            "# Vellis application model reference",
            "",
            "Generated from textual SysML v2 by `just model-render` as a non-normative reading "
            "projection; do not edit by hand.",
            "",
            "Review the cross-model [architecture projections](../architecture/index.md) for "
            "logical composition, runtime topology, operation ownership, and verification "
            "coverage.",
            "",
            "## Application composition",
            "",
            *role_rows,
            "",
            "## Everyday Life starter ontology",
            "",
            f"Ontology `{starter['ontology_id']}` version `{starter['version']}` is generated as "
            "schema-only bootstrap material. It contains no people, tasks, or other graph facts.",
            "",
            *starter_rows,
            "",
            *starter_link_rows,
            "",
            "## Actor-visible use cases",
            "",
            *use_case_rows,
            "",
            "## Python realization",
            "",
            *python_role_rows,
            "",
            "## Requirements and satisfaction",
            "",
            *contract_rows,
            "",
            "## Verification closure",
            "",
            *verification_rows,
            "",
            "## Façade and transport mappings",
            "",
            "Successful MCP calls encode as `{ok: true, result: <encoded action result>}`. "
            "Failures encode as `{ok: false, error: {type, message, diagnostic?}}`; controller "
            "validation failures also expose `validation_report` when present. Runtime message "
            "and trace identities remain envelope/history metadata.",
            "",
            *rows,
            "",
        ]
    )


def _runtime_binding_string(
    assignments: dict[str, str],
    field_definitions: dict[str, tuple[str, bool, str | None]],
    role_name: str,
    name: str,
) -> str:
    value = assignments.get(name, field_definitions[name][2])
    if value is None:
        raise ValueError(f"runtime occurrence {role_name} lacks {name}")
    match = re.fullmatch(r'"([^"\\]*(?:\\.[^"\\]*)*)"', value)
    if match is None:
        raise ValueError(f"runtime occurrence {role_name} has invalid {name}")
    return bytes(match.group(1), "utf-8").decode("unicode_escape")


def _runtime_binding_positive_integer(
    assignments: dict[str, str],
    field_definitions: dict[str, tuple[str, bool, str | None]],
    role_name: str,
    name: str,
) -> int:
    value = assignments.get(name, field_definitions[name][2])
    if value is None or re.fullmatch(r"\d+", value) is None or int(value) < 1:
        raise ValueError(f"runtime occurrence {role_name} has invalid {name}")
    return int(value)


def _runtime_binding_tuple_strings(
    assignments: dict[str, str], role_name: str, name: str
) -> list[str]:
    value = assignments.get(name)
    if value is None or re.fullmatch(r"\(\s*\"[^\"]+\"(?:\s*,\s*\"[^\"]+\")*\s*\)", value) is None:
        raise ValueError(f"runtime occurrence {role_name} has invalid {name}")
    return re.findall(r'"([^\"]+)"', value)


def _runtime_binding_tuple_positive_integers(
    assignments: dict[str, str], role_name: str, name: str
) -> list[int]:
    value = assignments.get(name)
    if value is None or re.fullmatch(r"\(\s*\d+(?:\s*,\s*\d+)*\s*\)", value) is None:
        raise ValueError(f"runtime occurrence {role_name} has invalid {name}")
    result = [int(item) for item in re.findall(r"\d+", value)]
    if any(item < 1 for item in result):
        raise ValueError(f"runtime occurrence {role_name} has invalid {name}")
    return result


def _vellis_runtime_occurrences() -> tuple[dict[str, Any], ...]:
    path = MODEL_ROOT / "vellis" / "realizations" / "VellisRuntimePython.sysml"
    text = path.read_text(encoding="utf-8")
    metadata_definition = _definition_block(text, "metadata def", "RuntimeOccurrenceBinding")
    if not metadata_definition:
        raise ValueError("Vellis runtime realization lacks RuntimeOccurrenceBinding metadata")

    field_definitions: dict[str, tuple[str, bool, str | None]] = {}
    for match in re.finditer(
        r"\battribute\s+(\w+)(\[[^]]+\])?\s*:\s*([\w:]+)"
        r"(?:\s+default\s*=\s*([^;]+))?\s*;",
        metadata_definition,
    ):
        name, multiplicity, type_name, default = match.groups()
        field_definitions[name] = (
            type_name,
            bool(multiplicity and multiplicity.startswith("[0")),
            default.strip() if default is not None else None,
        )
    expected_fields = {
        "instanceKey",
        "componentContractId",
        "implementationBinding",
        "runtimeBindingId",
        "bindingVersion",
        "laneNames",
        "laneCapacities",
        "laneWorkerLimits",
        "configurationReferences",
        "replayAuthority",
    }
    if set(field_definitions) != expected_fields:
        raise ValueError(
            "RuntimeOccurrenceBinding fields differ from the manifest projection: "
            f"{sorted(field_definitions)}"
        )

    runtime_contract = (
        MODEL_ROOT / "bibliotek" / "shared-values" / "RuntimeMessaging.sysml"
    ).read_text(encoding="utf-8")
    replay_definition = _definition_block(runtime_contract, "enum def", "RuntimeReplayMode")
    replay_modes = set(re.findall(rf"\benum\s+({SYSML_IDENTIFIER})\s*;", replay_definition))
    if not replay_modes:
        raise ValueError("RuntimeReplayMode has no modeled literals")

    runtime_definition = _definition_block(text, "part def", "VellisRuntimePython")
    if not runtime_definition:
        raise ValueError("Vellis runtime realization lacks VellisRuntimePython")
    occurrences: list[dict[str, Any]] = []
    annotated_parts: set[str] = set()
    part_pattern = re.compile(r"\bpart\s+(?::>>\s+)?(\w+)\s*:\s*([\w:]+)\s*\{")
    for part_match in part_pattern.finditer(runtime_definition):
        part_block = _extract_braced_block(runtime_definition, part_match.start())
        binding_matches = list(re.finditer(r"@RuntimeOccurrenceBinding\s*\{", part_block))
        if not binding_matches:
            continue
        role_name, type_name = part_match.groups()
        if len(binding_matches) != 1:
            raise ValueError(f"runtime occurrence {role_name} must have exactly one binding")
        if role_name in annotated_parts:
            raise ValueError(f"duplicate runtime occurrence role: {role_name}")
        annotated_parts.add(role_name)
        binding = _extract_braced_block(part_block, binding_matches[0].start())
        assignments: dict[str, str] = {}
        for assignment in re.finditer(r"\b(\w+)\s*=\s*([^;{}]+)\s*;", binding):
            name, value = assignment.groups()
            if name in assignments:
                raise ValueError(f"runtime occurrence {role_name} repeats {name}")
            assignments[name] = value.strip()
        unknown = set(assignments) - expected_fields
        if unknown:
            raise ValueError(
                f"runtime occurrence {role_name} has unknown fields: {sorted(unknown)}"
            )
        missing = {
            name
            for name, (_, optional, default) in field_definitions.items()
            if not optional and default is None and name not in assignments
        }
        if missing:
            raise ValueError(
                f"runtime occurrence {role_name} lacks required fields: {sorted(missing)}"
            )

        replay_value = assignments["replayAuthority"]
        replay_match = re.fullmatch(r"RuntimeReplayMode::(\w+)", replay_value)
        if replay_match is None or replay_match.group(1) not in replay_modes:
            raise ValueError(f"runtime occurrence {role_name} has invalid replayAuthority")
        configuration_value = assignments.get("configurationReferences")
        if configuration_value is None:
            configuration_references: list[str] = []
        else:
            tuple_match = re.fullmatch(
                r'\(\s*(?:"[^"\\]*(?:\\.[^"\\]*)*"\s*'
                r'(?:,\s*"[^"\\]*(?:\\.[^"\\]*)*"\s*)*)?\)',
                configuration_value,
            )
            if tuple_match is None:
                raise ValueError(
                    f"runtime occurrence {role_name} has invalid configurationReferences"
                )
            configuration_references = re.findall(
                r'"([^"\\]*(?:\\.[^"\\]*)*)"', configuration_value
            )

        implementation_binding = _runtime_binding_string(
            assignments, field_definitions, role_name, "implementationBinding"
        )
        if implementation_binding.rsplit("::", 1)[-1] != type_name.rsplit("::", 1)[-1]:
            raise ValueError(
                f"runtime occurrence {role_name} implementation binding differs from its type"
            )
        lane_names = _runtime_binding_tuple_strings(assignments, role_name, "laneNames")
        lane_capacities = _runtime_binding_tuple_positive_integers(
            assignments, role_name, "laneCapacities"
        )
        lane_worker_limits = _runtime_binding_tuple_positive_integers(
            assignments, role_name, "laneWorkerLimits"
        )
        if not (
            len(lane_names) == len(lane_capacities) == len(lane_worker_limits)
            and len(lane_names) == len(set(lane_names))
        ):
            raise ValueError(f"runtime occurrence {role_name} lane declarations differ or repeat")
        occurrence = {
            "instance_key": _runtime_binding_string(
                assignments, field_definitions, role_name, "instanceKey"
            ),
            "component_contract_id": _runtime_binding_string(
                assignments, field_definitions, role_name, "componentContractId"
            ),
            "implementation_binding": implementation_binding,
            "runtime_binding_id": _runtime_binding_string(
                assignments, field_definitions, role_name, "runtimeBindingId"
            ),
            "binding_version": _runtime_binding_positive_integer(
                assignments, field_definitions, role_name, "bindingVersion"
            ),
            "lanes": [
                {
                    "name": name,
                    "queue_capacity": capacity,
                    "worker_limit": worker_limit,
                }
                for name, capacity, worker_limit in zip(
                    lane_names, lane_capacities, lane_worker_limits, strict=True
                )
            ],
            "configuration_references": configuration_references,
            "replay_authority": replay_match.group(1),
        }
        if any(
            not str(occurrence[field]).strip()
            for field in (
                "instance_key",
                "component_contract_id",
                "implementation_binding",
                "runtime_binding_id",
            )
        ):
            raise ValueError(f"runtime occurrence {role_name} contains an empty identity")
        occurrences.append(occurrence)

    if runtime_definition.count("@RuntimeOccurrenceBinding") != len(occurrences):
        raise ValueError("every RuntimeOccurrenceBinding must annotate one occurrence part usage")
    instance_keys = [str(item["instance_key"]) for item in occurrences]
    if len(instance_keys) != len(set(instance_keys)):
        raise ValueError("Vellis runtime occurrence instance keys must be unique")
    return tuple(occurrences)


def _check_vellis_runtime_topology_model() -> list[Finding]:
    path = MODEL_ROOT / "vellis" / "realizations" / "VellisRuntimePython.sysml"
    try:
        occurrences = _vellis_runtime_occurrences()
    except (OSError, ValueError) as error:
        return [Finding(path, f"invalid runtime occurrence topology: {error}")]
    if len(occurrences) != 12:
        return [Finding(path, f"expected 12 runtime occurrences, found {len(occurrences)}")]
    return []


def _manifest_data() -> dict[str, Any]:
    operation_parameters = _model_tool_parameters()
    parameter_schemas = _model_tool_parameter_schemas()
    tool_descriptions = _model_tool_descriptions()
    tool_capabilities = _model_tool_capabilities()
    operation_text = (MODEL_ROOT / "vellis" / "VellisOperations.sysml").read_text(encoding="utf-8")

    def runtime_tool_metadata(tool: str) -> dict[str, Any]:
        action_name = "".join(part.capitalize() for part in tool.split("_"))
        marker = re.search(
            rf"\baction def\s+<'operation\.vellis\.{tool}'>\s+{action_name}",
            operation_text,
        )
        if marker is None:
            raise ValueError(f"Vellis tool has no logical action: {tool}")
        block = _extract_braced_block(operation_text, marker.start())
        arguments, _request_schema, result_schema = _runtime_action_signature(block)
        failure = re.search(
            r"@FailureContract\s*\{[^}]*errorIds\s*=\s*\(([^)]*)\)",
            block,
            re.DOTALL,
        )
        failure_names = re.findall(r'"([^"]+)"', failure.group(1)) if failure else []
        operator = tool in {
            "rtg_replay_ledger",
            "rtg_verify_replay_from_ledger",
            "rtg_list_migration_history",
            "rtg_get_operation_outcome",
        }
        read_only = bool(tool_capabilities[tool]["annotations"]["readOnlyHint"])
        lane = "operator" if operator else "read" if read_only else "mutation"
        return {
            "binding_id": "binding.python.vellis.facade.v2",
            "binding_version": 1,
            "request_codec_id": "codec.python.application.vellis.facade.request.json",
            "request_codec_version": 1,
            "result_codec_id": "codec.python.application.vellis.facade.result.json",
            "result_codec_version": 1,
            "failure_codec_id": "codec.python.application.vellis.facade.failure.json",
            "failure_codec_version": 1,
            "request_arguments": arguments,
            "request_schema": parameter_schemas[tool],
            "result_schema": result_schema,
            "fault_schema": {"oneOf": [_vellis_wire_schema(name) for name in failure_names]},
            "failure_names": failure_names,
            "concurrency_lane": lane,
            "consistency_group": ("vellis.facade.state" if lane in {"read", "mutation"} else None),
            "consistency_access": (
                "shared" if lane == "read" else "exclusive" if lane == "mutation" else "independent"
            ),
            "idempotency": "idempotent" if read_only else "non_idempotent",
            "deadline_seconds": 120,
            "replay_mode": "coordinator_trace",
            "recovery_authorized": tool == "rtg_replay_ledger",
            "request_payload_disposition": (
                "state_transfer" if tool == "rtg_restore_from_snapshot" else "command"
            ),
            "result_payload_disposition": (
                "state_transfer"
                if tool in {"rtg_export_system_snapshot", "rtg_load_persisted_snapshot"}
                else "query_result"
            ),
            "fault_payload_disposition": "diagnostic",
            "effect_payload_disposition": None,
        }

    def application_action_metadata(
        *,
        contract_id: str,
        binding_id: str,
        method_name: str,
        action_name: str,
        source: Path,
        lane: str,
        replay_mode: str,
        idempotency: str,
        externally_effectful: bool = False,
    ) -> dict[str, Any]:
        source_text = source.read_text(encoding="utf-8")
        marker = re.search(rf"\baction def\s+{action_name}\s*\{{", source_text)
        if marker is None:
            raise ValueError(f"application binding resolves no modeled action {action_name}")
        block = _extract_braced_block(source_text, marker.start())
        arguments, request_schema, result_schema = _runtime_action_signature(block)
        failure = re.search(
            r"@FailureContract\s*\{[^}]*errorIds\s*=\s*\(([^)]*)\)",
            block,
            re.DOTALL,
        )
        failure_names = re.findall(r'"([^"]+)"', failure.group(1)) if failure else []
        return {
            "action_id": f"{contract_id}.{method_name}",
            "method_name": method_name,
            "binding_id": binding_id,
            "binding_version": 1,
            "schema_version": 1,
            "request_codec_id": f"codec.python.{contract_id}.request.json",
            "request_codec_version": 1,
            "result_codec_id": f"codec.python.{contract_id}.result.json",
            "result_codec_version": 1,
            "failure_codec_id": f"codec.python.{contract_id}.failure.json",
            "failure_codec_version": 1,
            "request_arguments": arguments,
            "request_schema": request_schema,
            "result_schema": result_schema,
            "fault_schema": {"oneOf": [_vellis_wire_schema(name) for name in failure_names]},
            "failure_names": failure_names,
            "concurrency_lane": lane,
            "consistency_group": None,
            "consistency_access": "independent",
            "deadline_seconds": 120,
            "idempotency": idempotency,
            "replay_mode": replay_mode,
            "externally_effectful": externally_effectful,
            "recovery_authorized": False,
            "request_payload_disposition": "command",
            "result_payload_disposition": "query_result",
            "fault_payload_disposition": "diagnostic",
            "effect_payload_disposition": None,
        }

    application_bindings = [
        {
            "component_contract_id": "application.vellis.runner",
            "binding_id": "binding.python.vellis.runner.v2",
            "binding_version": 1,
            "actions": [
                application_action_metadata(
                    contract_id="application.vellis.runner",
                    binding_id="binding.python.vellis.runner.v2",
                    method_name="run",
                    action_name="RunRtgKnowledgeGraph",
                    source=MODEL_ROOT / "vellis" / "VellisOperations.sysml",
                    lane="runner",
                    replay_mode="external_exchange",
                    idempotency="idempotent",
                    externally_effectful=True,
                )
            ],
        },
        {
            "component_contract_id": "application.vellis.starter_ontology_installer",
            "binding_id": "binding.python.vellis.starter_ontology_installer.v2",
            "binding_version": 1,
            "actions": [
                application_action_metadata(
                    contract_id="application.vellis.starter_ontology_installer",
                    binding_id="binding.python.vellis.starter_ontology_installer.v2",
                    method_name=method_name,
                    action_name=action_name,
                    source=MODEL_ROOT / "vellis" / "EverydayLifeOntology.sysml",
                    lane="installer",
                    replay_mode="coordinator_trace",
                    idempotency=idempotency,
                )
                for method_name, action_name, idempotency in (
                    ("install", "InstallEverydayLifeOntology", "non_idempotent"),
                    ("get_status", "GetEverydayLifeOntologyStatus", "idempotent"),
                )
            ],
        },
        {
            "component_contract_id": "component.interface.mcp_gateway",
            "binding_id": "binding.python.interface.mcp_gateway.v2",
            "binding_version": 1,
            "actions": [],
        },
    ]

    manifest = {
        "app_name": "rtg_knowledge_graph",
        "schema_version": 4,
        "runtime": {
            "runtime_key": "vellis.rtg_knowledge_graph",
            "component_contract_id": "component.runtime.message_runtime",
            "implementation_binding": "VellisRuntimePythonRealization::SqliteMessageRuntime",
            "ledger_backend": "sqlite_internal_bootstrap",
            "configuration_references": ["config.runtime_database_path"],
            "routing_scope": "local_single_process",
        },
        "occurrences": list(_vellis_runtime_occurrences()),
        "topology_migration_required_on_occurrence_change": True,
        "component_dependencies": [
            {"id": _vellis_roles()[role], "role": RUNTIME_ROLE_NAMES[role]}
            for role in RUNTIME_MANIFEST_ROLE_ORDER
        ],
        "application_bindings": application_bindings,
        "tools": [
            {
                "name": tool,
                "operation_id": f"operation.vellis.{tool}",
                "target_instance_key": "vellis.facade.primary",
                "target_component_contract_id": "application.vellis.facade",
                "target_action_id": f"application.vellis.facade.{tool}",
                "message_schema_version": 1,
                "codec_id": "codec.python.application.vellis.facade.request.json",
                "codec_version": 1,
                **runtime_tool_metadata(tool),
                "description": tool_descriptions[tool],
                **tool_capabilities[tool],
                "parameter_schema": parameter_schemas[tool],
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
                    "optional": ["error.diagnostic", "validation_report"],
                },
            }
            for tool in _model_tool_names()
        ],
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    manifest["manifest_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return manifest


def _starter_schema_data() -> dict[str, Any]:
    path = MODEL_ROOT / "vellis" / "EverydayLifeOntology.sysml"
    text = path.read_text(encoding="utf-8")
    identity = _definition_block(text, "attribute def", "EverydayLifeOntologyIdentity")
    ontology_id = _required_string_default(identity, "ontologyId")
    version = _required_string_default(identity, "version")
    migration_id = _required_string_default(identity, "bootstrapMigrationId")

    definitions: list[dict[str, Any]] = []
    schema_ids: list[str] = []
    for match in re.finditer(r"\bpart def\s+(?:<'[^']+'>\s+)?(\w+)\s*\{", text):
        block = _extract_braced_block(text, match.start())
        if "@StarterAnchorDefinition" not in block:
            continue
        metadata = _definition_block(block, "@StarterAnchorDefinition", "")
        if not metadata:
            metadata = _extract_braced_block(block, block.index("@StarterAnchorDefinition"))
        type_key = _required_assignment(metadata, "typeKey")
        facts_type = _required_assignment(metadata, "factsTypeKey")
        description = _required_assignment(metadata, "description")
        facts_block = _definition_block(text, "attribute def", facts_type)
        fields: dict[str, dict[str, Any]] = {}
        for field in re.finditer(
            rf"\battribute\s+({SYSML_IDENTIFIER})(\[0\.\.1\])?\s*:\s*(String|Boolean)\s*;",
            facts_block,
        ):
            fields[_snake_case(_identifier_value(field.group(1)))] = {
                "required": field.group(2) is None,
                "value_kinds": ["boolean" if field.group(3) == "Boolean" else "string"],
            }
        anchor_uuid = str(uuid5(NAMESPACE_URL, f"{ontology_id}:schema:{type_key}"))
        facts_uuid = str(uuid5(NAMESPACE_URL, f"{ontology_id}:schema:{facts_type}"))
        schema_ids.extend((anchor_uuid, facts_uuid))
        definitions.extend(
            (
                {
                    "uuid": anchor_uuid,
                    "kind": "anchor",
                    "type_key": type_key,
                    "description": description,
                    "payload": {"required_data_types": [facts_type]},
                    "system": {"live": False},
                },
                {
                    "uuid": facts_uuid,
                    "kind": "data_object",
                    "type_key": facts_type,
                    "description": f"Typed facts for {type_key} anchors.",
                    "payload": {"properties": fields},
                    "system": {"live": False},
                },
            )
        )

    for match in re.finditer(r"\bitem def\s+(\w+)\s*\{", text):
        block = _extract_braced_block(text, match.start())
        if "@StarterLinkDefinition" not in block:
            continue
        metadata = _extract_braced_block(block, block.index("@StarterLinkDefinition"))
        type_key = _required_assignment(metadata, "typeKey")
        link_uuid = str(uuid5(NAMESPACE_URL, f"{ontology_id}:schema:{type_key}"))
        schema_ids.append(link_uuid)
        definitions.append(
            {
                "uuid": link_uuid,
                "kind": "link",
                "type_key": type_key,
                "description": _required_assignment(metadata, "description"),
                "payload": {
                    "allowed_source_types": _string_tuple_assignment(metadata, "sourceTypes"),
                    "allowed_target_types": _string_tuple_assignment(metadata, "targetTypes"),
                },
                "system": {"live": False},
            }
        )

    migration_uuid = str(uuid5(NAMESPACE_URL, f"{ontology_id}:migration-record:{migration_id}"))
    definition_writes = [
        {"ref": {"resource_id": item["uuid"]}, "definition": item} for item in definitions
    ]
    return {
        "ontology_id": ontology_id,
        "version": version,
        "bootstrap_migration_id": migration_uuid,
        "bootstrap_migration_key": migration_id,
        "schema_definition_count": len(definitions),
        "graph_objects": [],
        "knowledge_changes": {
            "schema_changes": {"definition_writes": definition_writes},
            "migration_changes": {
                "migration_writes": [
                    {
                        "ref": {"resource_id": migration_uuid},
                        "migration": {
                            "migration_id": migration_uuid,
                            "description": "Install the modeled Vellis Everyday Life ontology.",
                            "status": "ready",
                            "schema_make_live": schema_ids,
                        },
                    }
                ]
            },
        },
    }


def _required_string_default(block: str, name: str) -> str:
    match = re.search(rf"\battribute\s+{name}\s*:\s*String\s*=\s*\"([^\"]+)\"", block)
    if match is None:
        raise ValueError(f"Everyday Life ontology is missing {name}")
    return match.group(1)


def _required_assignment(block: str, name: str) -> str:
    match = re.search(rf"\b{name}\s*=\s*\"([^\"]+)\"", block)
    if match is None:
        raise ValueError(f"starter ontology metadata is missing {name}")
    return match.group(1)


def _string_tuple_assignment(block: str, name: str) -> list[str]:
    match = re.search(rf"\b{name}\s*=\s*\(([^)]*)\)", block)
    if match is None:
        raise ValueError(f"starter ontology metadata is missing {name}")
    return re.findall(r'"([^"]+)"', match.group(1))


def _snake_case(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _runtime_json_schema(type_name: str, multiplicity: str | None) -> dict[str, Any]:
    primitive = _vellis_wire_schema(type_name)
    if multiplicity is not None and "*" in multiplicity:
        return {"type": "array", "items": primitive}
    return primitive


def _runtime_default(value: str) -> Any:
    value = value.strip()
    if "::" in value:
        return value.rsplit("::", 1)[1]
    if value in {"true", "false"}:
        return value == "true"
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return None


def _runtime_action_signature(
    block: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    pattern = re.compile(
        r"\b(in|out)\s+(?:ref\s+)?(?:attribute\s+|item\s+)?"
        r"('?\w+'?)\s*(\[[^]]+\])?\s*(?:ordered\s+)?\s*:\s*([\w:]+)"
        r"\s*(\[[^]]+\])?"
        r"(?:default\s*=\s*([^;}{]+))?"
    )
    arguments: list[dict[str, Any]] = []
    result: dict[str, Any] = {"type": "null"}
    for (
        direction,
        raw_name,
        name_multiplicity,
        type_name,
        type_multiplicity,
        raw_default,
    ) in pattern.findall(block):
        name = raw_name.strip("'")
        multiplicity = name_multiplicity or type_multiplicity or None
        schema = _runtime_json_schema(type_name.rsplit("::", 1)[-1], multiplicity or None)
        if direction == "out":
            result = schema
            continue
        optional = bool(multiplicity and multiplicity.startswith("[0")) or bool(raw_default)
        arguments.append(
            {
                "name": _snake_case(name),
                "required": not optional,
                "default": _runtime_default(raw_default) if raw_default else None,
                "schema": schema,
            }
        )
    request_properties = {item["name"]: item["schema"] for item in arguments}
    return (
        arguments,
        {
            "type": "object",
            "additionalProperties": False,
            "properties": request_properties,
            "required": [item["name"] for item in arguments if item["required"]],
        },
        result,
    )


def _runtime_binding_resource_data() -> dict[Path, dict[str, Any]]:
    """Project reusable Python participation descriptors from the realization model."""

    path = MODEL_ROOT / "bibliotek" / "realizations" / "BibliotekRuntimePython.sysml"
    text = path.read_text(encoding="utf-8")
    resources: dict[Path, dict[str, Any]] = {}
    logical_actions: dict[
        str,
        tuple[tuple[str, ...], list[dict[str, Any]], dict[str, Any], dict[str, Any]],
    ] = {}
    for component_path in sorted(COMPONENT_MODEL_ROOT.glob("component.*.sysml")):
        component_text = component_path.read_text(encoding="utf-8")
        for match in re.finditer(r"\baction def\s+(\w+)", component_text):
            name = match.group(1)
            block = _extract_braced_block(component_text, match.start())
            contract = re.search(
                r"@FailureContract\s*\{[^}]*errorIds\s*=\s*\(([^)]*)\)",
                block,
                flags=re.DOTALL,
            )
            arguments, request_schema, result_schema = _runtime_action_signature(block)
            projected = (
                tuple(re.findall(r'"([^"]+)"', contract.group(1))) if contract else (),
                arguments,
                request_schema,
                result_schema,
            )
            prior = logical_actions.get(name)
            if prior is not None and prior != projected:
                raise ValueError(
                    f"ambiguous modeled runtime action name {name} in {component_path}"
                )
            logical_actions[name] = projected

    for part_match in re.finditer(
        r"\bpart def\s+(\w+)\s*:>\s*ComponentRuntimeAdapter\s*\{",
        text,
    ):
        part_block = _extract_braced_block(text, part_match.start())
        binding = re.search(r"@RuntimePythonBinding\s*\{([^}]*)\}", part_block, re.DOTALL)
        if binding is None:
            raise ValueError(f"{part_match.group(1)} lacks RuntimePythonBinding metadata")
        binding_block = binding.group(1)
        contract_id = _required_assignment(binding_block, "componentContractId")
        binding_id = _required_assignment(binding_block, "bindingId")
        resource_path = ROOT / _required_assignment(binding_block, "resourcePath")
        version_match = re.search(r"\bbindingVersion\s*=\s*(\d+)", binding_block)
        if version_match is None:
            raise ValueError(f"{part_match.group(1)} lacks bindingVersion")
        actions: list[dict[str, Any]] = []
        for action_match in re.finditer(
            r"\bperform action\s+(\w+)\s*(?:\[\s*0\.\.\*\s*\])?\s*:\s*(\w+)\s*\{",
            part_block,
        ):
            method_name, logical_action = action_match.groups()
            if logical_action not in logical_actions:
                raise ValueError(
                    f"runtime binding {method_name} resolves no modeled action {logical_action}"
                )
            action_block = _extract_braced_block(part_block, action_match.start())
            metadata = re.search(
                r"@RuntimePythonActionBinding\s*\{([^}]*)\}",
                action_block,
                re.DOTALL,
            )
            if metadata is None:
                raise ValueError(f"runtime action {method_name} lacks binding metadata")
            values = metadata.group(1)

            def enum_value(
                name: str,
                enum_name: str,
                *,
                source: str = values,
                action_name: str = method_name,
            ) -> str:
                match = re.search(rf"\b{name}\s*=\s*{enum_name}::(\w+)", source)
                if match is None:
                    raise ValueError(f"runtime action {action_name} lacks {name}")
                return match.group(1)

            def optional_enum_value(
                name: str,
                enum_name: str,
                default: str | None = None,
                *,
                source: str = values,
            ) -> str | None:
                match = re.search(rf"\b{name}\s*=\s*{enum_name}::(\w+)", source)
                return match.group(1) if match else default

            def optional_string(name: str, *, source: str = values) -> str | None:
                match = re.search(rf'\b{name}\s*=\s*"([^"]+)"', source)
                return match.group(1) if match else None

            def boolean_value(
                name: str,
                *,
                source: str = values,
                action_name: str = method_name,
            ) -> bool:
                match = re.search(rf"\b{name}\s*=\s*(true|false)", source)
                if match is None:
                    raise ValueError(f"runtime action {action_name} lacks {name}")
                return match.group(1) == "true"

            failure_names = _string_tuple_assignment(values, "failureNames")
            logical_failures, request_arguments, request_schema, result_schema = logical_actions[
                logical_action
            ]
            if tuple(failure_names) != logical_failures:
                raise ValueError(
                    f"runtime failures differ from {logical_action}: {failure_names} != "
                    f"{list(logical_failures)}"
                )
            disposition_names = (
                _string_tuple_assignment(values, "failureDispositionNames")
                if "failureDispositionNames" in values
                else []
            )
            disposition_match = re.search(r"\bfailureDispositionValues\s*=\s*\(([^)]*)\)", values)
            disposition_values = (
                re.findall(r"RuntimeTraceDisposition::(\w+)", disposition_match.group(1))
                if disposition_match
                else []
            )
            if len(disposition_names) != len(disposition_values):
                raise ValueError(f"runtime failure dispositions differ for {method_name}")
            deadline_match = re.search(r"\bdeadlineSeconds\s*=\s*([0-9.]+)", values)
            action_id = _required_assignment(values, "actionId")
            if action_id != f"{contract_id}.{method_name}":
                raise ValueError(f"runtime action ID differs for {method_name}")
            actions.append(
                {
                    "action_id": action_id,
                    "binding_id": binding_id,
                    "binding_version": int(version_match.group(1)),
                    "schema_version": 1,
                    "request_codec_id": f"codec.python.{contract_id}.request.json",
                    "request_codec_version": 1,
                    "result_codec_id": f"codec.python.{contract_id}.result.json",
                    "result_codec_version": 1,
                    "failure_codec_id": f"codec.python.{contract_id}.failure.json",
                    "failure_codec_version": 1,
                    "canonical_effect_schema_version": (
                        1
                        if enum_value("replayMode", "RuntimeReplayMode") == "canonical_effect"
                        else None
                    ),
                    "canonical_effect_codec_id": (
                        f"{binding_id}.{action_id}.effect.json"
                        if enum_value("replayMode", "RuntimeReplayMode") == "canonical_effect"
                        else None
                    ),
                    "canonical_effect_codec_version": (
                        1
                        if enum_value("replayMode", "RuntimeReplayMode") == "canonical_effect"
                        else None
                    ),
                    "request_arguments": request_arguments,
                    "request_schema": request_schema,
                    "result_schema": result_schema,
                    "fault_schema": {
                        "oneOf": [
                            _vellis_wire_schema(failure_name) for failure_name in failure_names
                        ]
                    },
                    "concurrency_lane": _required_assignment(values, "concurrencyLane"),
                    "consistency_access": enum_value(
                        "consistencyAccess", "RuntimeConsistencyAccess"
                    ),
                    "consistency_group": optional_string("consistencyGroup"),
                    "deadline_seconds": (
                        float(deadline_match.group(1)) if deadline_match else None
                    ),
                    "externally_effectful": boolean_value("externallyEffectful"),
                    "failure_dispositions": dict(
                        zip(disposition_names, disposition_values, strict=True)
                    ),
                    "failure_names": failure_names,
                    "idempotency": enum_value("idempotency", "RuntimeActionIdempotency"),
                    "method_name": method_name,
                    "modeled_fault_trace_disposition": enum_value(
                        "modeledFaultTraceDisposition", "RuntimeTraceDisposition"
                    ),
                    "recovery_authorized": boolean_value("recoveryAuthorized"),
                    "replay_mode": enum_value("replayMode", "RuntimeReplayMode"),
                    "resolved_argument_from_result": optional_string("resolvedArgumentFromResult"),
                    "request_payload_disposition": optional_enum_value(
                        "requestPayloadDisposition", "RuntimePayloadDisposition", "command"
                    ),
                    "result_payload_disposition": optional_enum_value(
                        "resultPayloadDisposition", "RuntimePayloadDisposition", "query_result"
                    ),
                    "fault_payload_disposition": optional_enum_value(
                        "faultPayloadDisposition", "RuntimePayloadDisposition", "diagnostic"
                    ),
                    "effect_payload_disposition": optional_enum_value(
                        "effectPayloadDisposition",
                        "RuntimePayloadDisposition",
                        "canonical_delta"
                        if enum_value("replayMode", "RuntimeReplayMode") == "canonical_effect"
                        else None,
                    ),
                }
            )
        resources[resource_path] = {
            "actions": actions,
            "binding_id": binding_id,
            "binding_version": int(version_match.group(1)),
            "component_contract_id": contract_id,
            "schema_version": 1,
            "source_contract_id": contract_id,
        }
    return resources


def _runtime_binding_resource_text() -> dict[Path, str]:
    return {
        path: json.dumps(data, indent=2, sort_keys=True) + "\n"
        for path, data in _runtime_binding_resource_data().items()
    }


def _check_runtime_payload_dispositions() -> list[Finding]:
    findings: list[Finding] = []
    for path, resource in _runtime_binding_resource_data().items():
        for action in resource["actions"]:
            name = str(action["method_name"])
            if (
                name == "export_snapshot"
                and action["result_payload_disposition"] != "state_transfer"
            ):
                findings.append(Finding(path, f"{name} result must be state_transfer"))
            if name in {"replace_snapshot", "restore_from_snapshot"}:
                if action["request_payload_disposition"] != "state_transfer":
                    findings.append(Finding(path, f"{name} request must be state_transfer"))
            if action["effect_payload_disposition"] == "state_transfer" and name not in {
                "replace_snapshot",
                "restore_from_snapshot",
            }:
                findings.append(
                    Finding(path, f"ordinary action {name} may not emit a state-transfer effect")
                )
    for source in (
        ROOT / "components/rtg/query/runtime_binding.py",
        ROOT / "components/rtg/change_validation/runtime_binding.py",
    ):
        text = source.read_text(encoding="utf-8")
        for forbidden in (
            'RuntimeArgumentDescriptor("graph_snapshot"',
            '"graph_snapshot": snapshot',
            '"schema_snapshot": snapshot',
            '"constraint_snapshot": snapshot',
            '"migration_snapshot": snapshot',
        ):
            if forbidden in text:
                findings.append(
                    Finding(
                        source,
                        f"ordinary request retains snapshot-shaped argument: {forbidden}",
                    )
                )
    return findings


def render() -> None:
    BIBLIOTEK_REFERENCE_ROOT.mkdir(parents=True, exist_ok=True)
    VELLIS_REFERENCE_ROOT.mkdir(parents=True, exist_ok=True)
    GENERATED_COMPONENT_DOC_ROOT.mkdir(parents=True, exist_ok=True)
    GENERATED_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    component_pages = _component_pages()
    for stale in GENERATED_COMPONENT_DOC_ROOT.glob("*.md"):
        if stale not in component_pages:
            stale.unlink()
    for path, content in component_pages.items():
        path.write_text(content, encoding="utf-8")
    (BIBLIOTEK_REFERENCE_ROOT / "index.md").write_text(
        _render_component_summary(), encoding="utf-8"
    )
    (VELLIS_REFERENCE_ROOT / "index.md").write_text(_render_operation_summary(), encoding="utf-8")
    GENERATED_MANIFEST.write_text(
        json.dumps(_manifest_data(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    GENERATED_STARTER_SCHEMA.write_text(
        json.dumps(_starter_schema_data(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    GENERATED_EVIDENCE_INDEX.write_text(
        json.dumps(_verification_evidence_data(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    GENERATED_CONFORMANCE_OBJECTIVES.write_text(
        json.dumps(_conformance_objectives_data(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for path, content in _runtime_binding_resource_text().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def check_generated() -> list[Finding]:
    expected = {
        **_component_pages(),
        BIBLIOTEK_REFERENCE_ROOT / "index.md": _render_component_summary(),
        VELLIS_REFERENCE_ROOT / "index.md": _render_operation_summary(),
        GENERATED_MANIFEST: json.dumps(_manifest_data(), indent=2, sort_keys=True) + "\n",
        GENERATED_STARTER_SCHEMA: json.dumps(_starter_schema_data(), indent=2, sort_keys=True)
        + "\n",
        GENERATED_EVIDENCE_INDEX: json.dumps(
            _verification_evidence_data(), indent=2, sort_keys=True
        )
        + "\n",
        GENERATED_CONFORMANCE_OBJECTIVES: json.dumps(
            _conformance_objectives_data(), indent=2, sort_keys=True
        )
        + "\n",
        **_runtime_binding_resource_text(),
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
    findings.extend(_check_formal_model_index())
    findings.extend(_check_runtime_payload_dispositions())
    return findings


def package_models() -> None:
    destination = MODEL_PACKAGE_ROOT
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
                    "versionConstraint": "0.1.0",
                }
            ]
        else:
            usage = [
                {
                    "resource": "software-component-modeling-foundation-0.1.0.kpar",
                    "versionConstraint": "0.1.0",
                },
                {"resource": "bibliotek-0.1.0.kpar", "versionConstraint": "0.1.0"},
            ]
        project = {
            "name": name.removesuffix("-0.1.0.kpar"),
            "description": "Vellis textual SysML source package",
            "version": "0.1.0",
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
            "status": "formally-validated",
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
        if re.search(rf"<'{re.escape(target)}'>", text):
            identity_matches.append(path)
        elif target in text:
            reference_matches.append(path)
    matches = identity_matches or reference_matches
    if not matches:
        print(f"No model element found for {target}", file=sys.stderr)
        return 1
    is_component = target.startswith("component.")
    is_vellis = target == "application.vellis" or any(
        path.is_relative_to(MODEL_ROOT / "vellis") for path in matches
    )
    if target == "application.vellis":
        matches = sorted((MODEL_ROOT / "vellis").rglob("*.sysml"))
    print(f"Target: {target}")
    print("Model authority: normative textual SysML")
    if is_component:
        print("Model product: build/model/packages/bibliotek-0.1.0.kpar")
        print(f"Generated view: generated/reference/bibliotek/components/{target}.md")
    elif is_vellis:
        print("Model product: build/model/packages/vellis-0.1.0.kpar")
        print("Generated view: generated/reference/vellis/index.md")
        print(
            "Generated starter schema: apps/rtg_knowledge_graph/resources/everyday_life_schema.json"
        )
    else:
        print(
            "Model product: build/model/packages/software-component-modeling-foundation-0.1.0.kpar"
        )
    print("Model sources:")
    foundation = MODEL_ROOT / "foundation" / "SoftwareComponentModeling.sysml"
    if foundation not in matches:
        print("- model/foundation/SoftwareComponentModeling.sysml")
    for path in matches:
        print(f"- {path.relative_to(ROOT)}")
    print("Implementation input: accepted SysML/KPAR, generated view, and verification objectives.")
    model_sources = {path.relative_to(ROOT).as_posix() for path in matches}
    conformance = _conformance_objectives_data()
    raw_objectives = conformance.get("objectives", [])
    if not isinstance(raw_objectives, list):
        raw_objectives = []
    objectives = [
        objective
        for objective in raw_objectives
        if isinstance(objective, dict)
        and (
            objective.get("model_source") in model_sources
            or target in objective.get("requirements", [])
        )
    ]
    print(
        f"Verification: {len(objectives)} structured objective(s) in "
        f"{GENERATED_CONFORMANCE_OBJECTIVES.relative_to(ROOT)}."
    )
    print(
        "Freedom: private helpers, algorithms, storage layouts, and language inheritance are open."
    )
    return 0


def setup_status() -> int:
    lock = _read_json(LANGUAGE_LOCK_PATH)
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
    cache = FORMAL_CACHE_ROOT
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
        result = subprocess.run(
            [sys.executable, "tools/sysml_validator.py", "setup"],
            cwd=ROOT,
            check=False,
        )
        if result.returncode:
            return result.returncode
        print(
            "External validator: "
            + " ".join(sys.executable if str(part) == "{python}" else str(part) for part in command)
        )
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
    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("target", nargs="?")
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
        print(f"Packaged KPAR products under {MODEL_PACKAGE_ROOT.relative_to(ROOT)}/.")
        return 0
    if args.command == "setup":
        return setup_status()
    if args.command == "handoff":
        return handoff(args.target)
    if args.command == "audit":
        try:
            json_path, markdown_path = model_audit(args.target)
        except (OSError, ValueError, SyntaxError) as error:
            print(f"Model audit failed: {error}", file=sys.stderr)
            return 2
        print(
            "Wrote advisory audit bundles: "
            f"{json_path.relative_to(ROOT)}, {markdown_path.relative_to(ROOT)}"
        )
        return 0
    result = subprocess.run(
        [
            "git",
            "diff",
            "--",
            "model",
            "generated",
            "components",
            "tests",
            "apps/rtg_knowledge_graph",
            "reference/specifications",
            ".agents/skills",
            ".github/workflows/check.yml",
            "AGENTS.md",
            "README.md",
            "docs/engineering/sysml-modeling.md",
            "justfile",
            "pyproject.toml",
            "tools/sysml_reference.py",
            "tools/sysml_diagrams.py",
            "tools/model_views.py",
            "tools/model_tool.py",
            "tests/test_sysml_reference.py",
            "tests/test_model_views.py",
            "uv.lock",
            str(GENERATED_MANIFEST.relative_to(ROOT)),
        ],
        cwd=ROOT,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
