# Repository SysML view patterns

## Supported graphical pattern

```sysml
view <'diagram.bibliotek.component.example.contract'> exampleContractDiagram {
    expose BibliotekExample::ExampleComponent;
    render asTreeDiagram;
}
```

The `diagram.` short name is the generated-artifact identity. `diagram.<product>.<name>` maps to:

- `generated/reference/<product>/diagrams/<name>.puml`
- `generated/reference/<product>/diagrams/<name>.svg`

The official parser inventory must resolve the usage and the ID must be unique. The pilot backend supports registered `asTreeDiagram` and `asInterconnectionDiagram` usages. Keep `asElementTable` usages in the Markdown projection pipeline.

The repository renders component contract overviews with the pilot's `COMPMOST` and `STDCOLOR`
styles. This keeps owned features and performed actions in labeled compartments and avoids a wide,
edge-heavy graph whose layout obscures the contract. Use a separate focused view when action-state
dependencies, interconnections, flow, or sequencing are the actual concern. The SVG normalizer
removes PlantUML `textLength` overrides because macOS Quick Look misrenders them even though
browsers render them correctly. Both Java subprocesses must retain the local
`-Djava.awt.headless=true` JVM property so rendering cannot create a macOS application or take
keyboard focus.

## Disjunctive filter pattern

```sysml
view def ComponentStructureView {
    filter @SysML::PartDefinition or @SysML::PartUsage or
        @SysML::BindingConnectorAsUsage;
}
```

KerML filter conditions on the same membership are conjunctive. Multiple separate `filter` statements therefore mean all conditions must hold. Use one explicit OR expression when the projection intends a union of element types.

## Exposure guidance

Start with one public part, action, requirement, or explicit composition occurrence. Add only elements needed to answer the projection concern. A package-wide recursive exposure is acceptable for an unregistered table or broad exploratory view, but it must not enter the graphical catalog until it passes the completeness gate.

## Pilot failure interpretation

| Result | Meaning | Response |
|---|---|---|
| `EXCEEDS THE LIMIT` | Official pilot traversal exceeded its hard ceiling. | Split by concern or narrower roots; do not publish the partial result. |
| Empty or non-PlantUML output | Rendering is unsupported or unresolved. | Confirm rendering kind, qualified view name, and parser inventory. |
| `ERROR:` or kernel diagnostics | Model or rendering command failed. | Resolve formal diagnostics before regeneration. |
| Invalid SVG or renderer stderr | PlantUML/Smetana rejected the normalized source. | Diagnose the generated PlantUML; do not replace committed artifacts. |
| Missing primary nodes | The view is semantically incomplete despite successful rendering. | Correct exposure/filtering or split the concern before registration. |

When splitting, prefer stable concern suffixes such as `.contract`, `.behavior`, `.requirements`, or `.interconnections`. Each child view must remain independently meaningful and complete.
