# Vellis model

The textual SysML v2 files in this directory are the current engineering source for Vellis. They
form one application model and load in numeric order; `99-vellis-model.sysml` imports the complete
working model.

This model is a draft. Parsing and validation establish language conformance, not architectural
acceptance. No feature is authorized for implementation until a human selects a vertical slice and
approves its intent, requirements, and verification objectives.

The model intentionally preserves the RTG distinctions among anchors, associated data objects,
directed links, and identity-free anchor/data associations. It does not preserve the former Python,
storage, schema, migration, ledger, CLI, or transport designs as contracts.

Use `just model-check` to run the pinned validator. Use the `sysml-modeling` and `sysml-reference`
skills for model changes and language decisions.
