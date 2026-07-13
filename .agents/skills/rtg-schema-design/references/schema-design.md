# RTG Schema Design Reference

## Core distinctions

- An **anchor** is an independently identifiable thing that other records and links can address.
- An **associated data object** is a coherent, typed group of descriptive facts attached to one
  or more anchors. It is not a substitute for an independently identifiable thing.
- A **link** is a meaningful relationship users will navigate, filter, or reason over. Give it
  explicit source and target anchor sets.

Add a property when the new fact remains part of the same coherent description. Add another data
type when the fact group has distinct validation, optional presence, or evolution. Add an anchor
when independent identity, lifecycle, or linking matters. Add a link when the relationship itself
is queryable and semantically stable.

## Precision without brittleness

- Require only facts every valid partial record can truthfully provide.
- Keep unknown values absent. Never require placeholder dates, statuses, names, or priorities.
- Use Boolean, number, and string kinds deliberately; specify date-like string conventions only
  when consumers depend on them.
- Prefer stable singular PascalCase type keys and clear snake_case property keys unless the host
  system already has a compatible convention.
- Distinguish identity from display names. Define how duplicates and ambiguous lookups are handled.
- Make link direction and endpoints explicit. Do not use a catch-all relationship merely to avoid
  deciding what a relationship means.
- Avoid generic JSON blobs when callers need typed fields for validation or queries.
- Avoid premature domain specialization. Add a specialized type after repeated semantics justify
  distinct validation, behavior, or queries.

## Evolution checklist

Before proposing changes:

1. Inspect live schema, constraints, representative data, and consumers.
2. State whether the change is additive, narrowing, renaming, replacing, or retiring.
3. Explain how existing records remain valid or are transformed without losing identity.
4. Define collision, invalid-data, and failed-cutover behavior with no partial live effects.
5. Define representative positive, incomplete-data, invalid, link-endpoint, and query scenarios.
6. Ask for approval when the change alters existing meaning, required data, or live records.

Stage candidates separately from live schema, validate projected cutover state, explain findings,
and cut over only after acceptance. Validate the resulting graph and representative queries. Keep
recovery and audit evidence, but do not confuse operational history with schema semantics.

## Review questions

- Can two implementations agree on what records and links are valid?
- Can an agent store useful incomplete knowledge without inventing facts?
- Can callers distinguish independently identifiable things from their descriptions?
- Are common user questions expressible without scanning opaque blobs?
- Are direction, endpoint restrictions, optionality, and canonical names unambiguous?
- Can the schema be extended without rewriting unrelated live data?
- Is each specialized type justified by stable semantics rather than one example?
