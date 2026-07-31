# RTG Domain Review

## Core distinctions

- **Anchor:** a stable, independently identifiable concept with a UUID, type, metadata, and optional display name.
- **Associated data object:** an identity-bearing typed fact group with JSON properties, associated with one or more anchors.
- **Link:** an identity-bearing typed directed relationship. Its endpoints may be anchors or associated data objects, but never links.
- **Direct association:** an identity-free, many-to-many association between an anchor and an associated data object. It is neither a link nor a graph object.

Graph-object UUIDs are globally unique. Type keys share one namespace but do not change an object's kind. JSON values remain lossless. A missing `system.live` value normalizes to `true`; a supplied value is Boolean.

## Precision heuristics

- Use an anchor when the concept must be addressed, related, or accumulated independently over time.
- Use an associated data object when a typed group of facts has identity but makes sense through one or more anchors.
- Use a link when the relationship itself needs identity, type, metadata, direction, or lifecycle.
- Use a direct association for the bare fact that anchors and data objects are associated without reifying the association.
- State permitted source and target object kinds and type sets; direction should reflect the intended question, not wording convenience.
- Preserve truthful partial knowledge instead of forcing guessed values.

## Compatibility questions

- Does the change alter the meaning or kind of an existing type key?
- Could existing objects become invalid or misleading?
- Are property meaning, requiredness, value shape, or default interpretation changing?
- Are link direction or endpoint sets changing?
- Can old and new interpretations coexist without ambiguity?
- What future recovery or human review would be needed, without committing to migration machinery now?

## Review criteria

A sound proposal answers a current owner question, preserves the four RTG distinctions, has stable vocabulary, supports incomplete truth, makes relationship direction and endpoint sets explicit, avoids unused detail, and identifies consequential compatibility effects for human approval.
