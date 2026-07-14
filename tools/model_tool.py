from __future__ import annotations

import argparse
import ast
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
from typing import Any
from uuid import NAMESPACE_URL, uuid5

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
        ("component.app.launcher", "supports"): "SupportsRuntimeSurface",
        ("component.app.launcher", "start"): "StartRuntimeSurface",
        ("component.app.launcher", "attach"): "AttachRuntimeSurface",
        ("component.app.launcher", "stop"): "StopRuntimeSurface",
        ("component.app.launcher", "probe"): "ProbeRuntimeSurface",
        ("component.app.shell", "open"): "OpenAppShell",
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
        if not component_id:
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
        if not component_id:
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
                rf"{SYSML_IDENTIFIER}(\[[^]]+\])?\s*:\s*([\w:]+)",
                action_blocks[action],
            )
            type_aliases = {
                "bool": "Boolean",
                "float": "Real",
                "int": "Integer",
                "str": "String",
            }
            optional_return = False
            if isinstance(return_type, str) and " | " in return_type:
                return_members = {member.strip() for member in return_type.split("|")}
                if "None" in return_members and len(return_members) == 2:
                    return_type = next(member for member in return_members if member != "None")
                    optional_return = True
            if return_type in {None, "None"}:
                expected_outputs: tuple[str, ...] = ()
            else:
                assert isinstance(return_type, str)
                expected_outputs = (type_aliases.get(return_type, return_type),)
            model_output_types = tuple(output_type for _, output_type in model_outputs)
            optionality_matches = not optional_return or (
                len(model_outputs) == 1 and model_outputs[0][0] == "[0..1]"
            )
            if model_output_types != expected_outputs or not optionality_matches:
                findings.append(
                    Finding(
                        path,
                        f"{method}/{action} return contract differs: "
                        f"protocol={return_type}, model={model_outputs}",
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
                r"perform action\s+(\w+)\[[^]]+\]\s*:\s*(\w+)", component_block
            ):
                feature, action_name = match.groups()
                feature_block = _extract_braced_block(component_block, match.start())
                direct_access = bool(_documentation(feature_block))
                dependency_access = any(
                    _documentation(_extract_braced_block(component_block, dependency.start()))
                    for dependency in re.finditer(
                        rf"\bdependency\s+\w+\s+from\s+{re.escape(feature)}\s+to\s+",
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
                r"\b(?:ref\s+)?(?:derived\s+)?(?:attribute|item)\s+(\w+)(?:\[[^]]+\])?\s*:",
                block,
            )
        )
        provided_actions = set(
            re.findall(r"\bperform action\s+(\w+)\[[^]]+\]\s*:", complete_contract)
        )
        actions_with_state_semantics: set[str] = set()
        for match in re.finditer(
            r"\bdependency\s+(\w+)\s+from\s+(\w+)\s+to\s+([\w.]+)\s*\{",
            block,
        ):
            dependency_name, source, target = match.groups()
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
    if len(facade_calls) != 27 or len(facade_performers) != 27:
        findings.append(
            Finding(
                operations_path,
                f"expected 27 native facade calls and performers; found "
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
    delegations = re.findall(r"\baction invokeFacade\s*:\s*\w+", adapter)
    performers = re.findall(r"\bperform\s+\w+\.invokeFacade\s*;", adapter)
    allocations = re.findall(
        r"\ballocate\s+application\.facade\.\w+\s+to\s+adapter\.\w+\s*;", mcp_text
    )
    if "bind adapter.facade = application.facade;" not in mcp_text:
        findings.append(Finding(mcp_path, "MCP adapter is not bound to the application facade"))
    if (len(delegations), len(performers), len(allocations)) != (27, 27, 27):
        findings.append(
            Finding(
                mcp_path,
                "MCP realization must contain 27 facade delegations, performers, and allocations",
            )
        )
    for call in re.finditer(r"\baction\s+invokeFacade\s*:\s*(\w+)\s*\{", adapter):
        call_type = call.group(1)
        call_block = _extract_braced_block(adapter, call.start())
        for direction in ("in", "out"):
            for field in sorted(features(call_type, direction)):
                field_pattern = _identifier_pattern(field)
                if not re.search(
                    rf"\b{direction}\s+(?:ref\s+)?(?:attribute\s+|part\s+|item\s+)?{field_pattern}"
                    rf"\s+redefines\s+{re.escape(call_type)}::{field_pattern}\s*=",
                    call_block,
                ):
                    findings.append(
                        Finding(
                            mcp_path,
                            f"MCP facade call {call_type} leaves {direction} "
                            f"parameter {field} unbound",
                        )
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
        filters = set(re.findall(r"\bfilter\s+@([\w:]+)\s*;", text))
        missing = sorted(required_filters - filters)
        if missing:
            findings.append(Finding(path, f"view projections omit filters: {missing}"))
    vellis_path = MODEL_ROOT / "vellis" / "views" / "VellisViews.sysml"
    vellis_text = vellis_path.read_text(encoding="utf-8")
    for package in ("VellisLocalPythonRealization", "VellisMcpPythonRealization"):
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


def _test_functions(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except OSError, SyntaxError:
        return []
    return sorted(
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    )


def _evidence_group_map(path: Path) -> dict[str, tuple[str, ...]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except OSError, SyntaxError:
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
        return [f"{path_text}::{symbol}"] if symbol in _test_functions(ROOT / path_text) else []
    if not group:
        return []
    tests = set(_test_functions(ROOT / source))
    symbols = _evidence_group_map(ROOT / source).get(group, ())
    if any(symbol not in tests for symbol in symbols):
        return []
    return [f"{source}::{symbol}" for symbol in symbols]


def _verification_evidence_data() -> dict[str, object]:
    groups: dict[str, object] = {}
    for path in _sysml_files("all"):
        text = path.read_text(encoding="utf-8")
        for evidence_id in re.findall(r'evidenceId\s*=\s*"([^"]+)"', text):
            groups[evidence_id] = {
                "model_source": str(path.relative_to(ROOT)),
                "test_nodes": _evidence_test_nodes(evidence_id),
                "status": (
                    "pending"
                    if evidence_id.startswith("pending#")
                    else "resolved"
                    if _evidence_test_nodes(evidence_id)
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
    for realization_path in MODEL_ROOT.glob("**/realizations/*.sysml"):
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
    source_path = ROOT / "apps" / "rtg_knowledge_graph" / "mcp_server.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    registrations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not (
                (isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "tool")
                or (isinstance(decorator.func, ast.Name) and decorator.func.id == "_tool")
            ):
                continue
            name_keyword = next(
                (keyword for keyword in decorator.keywords if keyword.arg == "name"), None
            )
            if name_keyword is None or not isinstance(name_keyword.value, ast.Constant):
                continue
            registrations.append((node.lineno, str(name_keyword.value.value)))
    if not registrations:
        raise ValueError("FastMCP tool registrations were not found in mcp_server.py")
    return tuple(name for _, name in sorted(registrations))


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
                    multiplicity == "[0..1]",
                    _model_default(default or None),
                )
            )
        parameters[identity.removeprefix("operation.vellis.")] = tuple(action_parameters)
    return parameters


def _python_tool_description_names() -> set[str]:
    source_path = ROOT / "apps" / "rtg_knowledge_graph" / "mcp_server.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            description = next(
                (keyword.value for keyword in decorator.keywords if keyword.arg == "description"),
                None,
            )
            if not isinstance(description, ast.Subscript):
                continue
            if (
                not isinstance(description.value, ast.Name)
                or description.value.id != "TOOL_DESCRIPTIONS"
            ):
                continue
            if isinstance(description.slice, ast.Constant):
                names.add(str(description.slice.value))
    if not names:
        raise ValueError("TOOL_DESCRIPTIONS references were not found in mcp_server.py")
    return names


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
        "enum record; enum skip;",
        "enum restore_pre_cutover_snapshot;",
        "enum cutover_applied;",
        "enum ledger_failures_flushed;",
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
        if len(models) != 18:
            findings.append(
                Finding(COMPONENT_MODEL_ROOT, f"expected 18 components, found {len(models)}")
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
                    ROOT / "apps" / "rtg_knowledge_graph" / "mcp_toolset.py",
                    "MCP descriptions do not match the exact tool surface",
                )
            )
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

    if scope == "all":
        findings.extend(_check_view_semantics())

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

    action_definitions = {
        match.group(1): _extract_braced_block(text, match.start())
        for match in re.finditer(rf"\baction def\s+{OPTIONAL_IDENTIFICATION}(\w+)\s*\{{", text)
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
        r"(?m)^\s*(ref\s+|derived\s+)?(?:attribute|item)\s+(\w+)"
        r"(?:\[[^]]+\])?\s*:\s*([\w:]+)\s*\{(.*?)\}",
        flags=re.DOTALL,
    )
    for match in state_pattern.finditer(complete_component_contract):
        modifier, name, type_name, body = match.groups()
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
            f"{_documentation(body) or 'Typed component state.'} |"
        )
    if len(state_rows) == 2:
        state_rows.append("| — | — | — | This component owns no abstract state. |")

    effect_rows = [
        "| Action | State / collaborator | Access | Modeled effect |",
        "|---|---|---|---|",
    ]
    for match in re.finditer(
        r"dependency\s+\w+\s+from\s+(\w+)\s+to\s+([\w.]+)\s*\{",
        complete_component_contract,
    ):
        body = _extract_braced_block(complete_component_contract, match.start())
        effect = _documentation(body)
        access = re.search(r"kind\s*=\s*StateAccessKind::(\w+)", body)
        if effect:
            effect_rows.append(
                f"| `{match.group(1)}` | `{match.group(2)}` | `{access.group(1)}` | {effect} |"
                if access
                else f"| `{match.group(1)}` | `{match.group(2)}` | `dependency` | {effect} |"
            )
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

    satisfiers = dict(re.findall(r"\bsatisfy\s+(\w+)\s+by\s+([\w.]+)\s*;", text))
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

    return "\n".join(
        [
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
            "## Components",
            "",
            *rows,
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
    launcher_text = (MODEL_ROOT / "vellis" / "PersonalLauncher.sysml").read_text(encoding="utf-8")
    launcher_realization_text = (
        MODEL_ROOT / "vellis" / "realizations" / "PersonalLauncherPython.sysml"
    ).read_text(encoding="utf-8")
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
            controller_calls[feature] = re.findall(r"\baction\s+invoke\w*\s*:\s*(\w+)", block)
    realization_text = (MODEL_ROOT / "vellis" / "realizations" / "VellisMcpPython.sysml").read_text(
        encoding="utf-8"
    )
    allocations = dict(
        re.findall(
            r"allocate\s+application\.facade\.(\w+)\s+to\s+adapter\.(\w+)\s*;",
            realization_text,
        )
    )
    action_types = {
        identity.removeprefix("operation.vellis."): action_type
        for identity, action_type in re.findall(
            r"action def\s+<'(operation\.vellis\.[^']+)'>\s+(\w+)", operation_text
        )
    }
    rows = [
        "| # | Tool | Façade / controller realization | Signature | Principal failures | Outcome |",
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
        realization = (
            f"`{facade_feature}` → "
            f"{', '.join(f'`{call}`' for call in calls) or '`application-local`'} → "
            f"`{allocations.get(facade_feature, 'unmapped')}`"
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
    launcher_role_types = {
        "AppCatalog": "component.app.catalog",
        "AppLauncher": "component.app.launcher",
        "AppShell": "component.app.shell",
        "RuntimeAdapter": "external runtime capability",
    }
    launcher_role_rows = [
        "| Personal Launcher role | Logical type | Provider |",
        "|---|---|---|",
    ]
    launcher_role_rows.extend(
        f"| `{role}` | `{type_name}` | `{launcher_role_types[type_name]}` |"
        for role, type_name in re.findall(
            r"(?m)^\s*part\s+(\w+)\s*:\s*(AppCatalog|AppLauncher|AppShell|RuntimeAdapter)\s*;",
            launcher_text,
        )
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
    launcher_realization_definitions: dict[str, tuple[str, str]] = {}
    for definition in re.finditer(
        r"\bpart def\s+(\w+)\s*:>\s*(\w+)\s*\{", launcher_realization_text
    ):
        block = _extract_braced_block(launcher_realization_text, definition.start())
        symbol = re.search(r'\bsymbol\s*=\s*"([^"]+)"', block)
        if symbol:
            launcher_realization_definitions[definition.group(1)] = (
                definition.group(2),
                symbol.group(1),
            )
    launcher_python_rows = [
        "| Personal Launcher role | Logical type | Python realization | Implementation symbol |",
        "|---|---|---|---|",
    ]
    for role, realization in re.findall(
        r"\bpart\s+:>>\s+(\w+)\s*:\s*(\w+)\s*;", launcher_realization_text
    ):
        logical_type, symbol = launcher_realization_definitions.get(
            realization, ("Bibliotek component realization", "See Bibliotek Python realization")
        )
        launcher_python_rows.append(
            f"| `{role}` | `{logical_type}` | `{realization}` | `{symbol}` |"
        )
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
        launcher_text,
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
        satisfiers = dict(re.findall(r"\bsatisfy\s+(\w+)\s+by\s+([\w.]+)\s*;", contract_text))
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
            "## Application composition",
            "",
            *role_rows,
            "",
            "## Personal Launcher composition",
            "",
            *launcher_role_rows,
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
            "## Personal Launcher Python realization",
            "",
            *launcher_python_rows,
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
            "validation failures also expose `transaction_id` and `validation_report` when "
            "present.",
            "",
            *rows,
            "",
        ]
    )


def _manifest_data() -> dict[str, Any]:
    operation_parameters = _model_tool_parameters()
    tool_descriptions = _model_tool_descriptions()
    tool_capabilities = _model_tool_capabilities()
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
                "description": tool_descriptions[tool],
                **tool_capabilities[tool],
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
            "tools/model_tool.py",
            "tests/test_sysml_reference.py",
            "uv.lock",
            str(GENERATED_MANIFEST.relative_to(ROOT)),
        ],
        cwd=ROOT,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
