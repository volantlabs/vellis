# State-transfer boundary matrix

Generated non-normative reading projection from the parser-backed SysML architecture graph; do not edit by hand.

Only rows marked `yes` may carry complete component state. Batch and validation rows are
included as explicit negative boundaries. Traceability columns summarize matching modeled
state-transfer or delta-scaling requirements in the owning component source.

| Component | Action | State-transfer positions | Complete state allowed | Satisfies | Verifies |
|---|---|---|---|---|---|
| `component.rtg.change_validation` | `component.rtg.change_validation.validate_batch` | none | no | yes | yes |
| `component.rtg.constraints` | `component.rtg.constraints.export_snapshot` | result | yes | yes | yes |
| `component.rtg.constraints` | `component.rtg.constraints.replace_snapshot` | effect, request | yes | yes | yes |
| `component.rtg.constraints` | `component.rtg.constraints.apply_batch` | none | no | yes | yes |
| `component.rtg.controller` | `component.rtg.controller.export_system_snapshot` | result | yes | yes | yes |
| `component.rtg.controller` | `component.rtg.controller.load_persisted_snapshot` | result | yes | yes | yes |
| `component.rtg.controller` | `component.rtg.controller.restore_from_snapshot` | request | yes | yes | yes |
| `component.rtg.graph` | `component.rtg.graph.export_snapshot` | result | yes | yes | yes |
| `component.rtg.graph` | `component.rtg.graph.replace_snapshot` | effect, request | yes | yes | yes |
| `component.rtg.graph` | `component.rtg.graph.apply_batch` | none | no | yes | yes |
| `component.rtg.migration` | `component.rtg.migration.export_snapshot` | result | yes | yes | yes |
| `component.rtg.migration` | `component.rtg.migration.replace_snapshot` | effect, request | yes | yes | yes |
| `component.rtg.migration` | `component.rtg.migration.apply_batch` | none | no | yes | yes |
| `component.rtg.schema` | `component.rtg.schema.export_snapshot` | result | yes | yes | yes |
| `component.rtg.schema` | `component.rtg.schema.replace_snapshot` | effect, request | yes | yes | yes |
| `component.rtg.schema` | `component.rtg.schema.apply_batch` | none | no | yes | yes |
