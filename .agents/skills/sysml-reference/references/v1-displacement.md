# SysML v2 is not SysML v1

SysML v1 and UML dominate training data, and SysML v2 displaced much of that
notation. Recalled syntax is therefore biased toward forms this baseline
replaced. Confidence is not evidence; a construct you cannot cite is an
inference.

Two tables. The first is handled for you. The second is not, and is the reason
this file exists.

## Table A — displaced notation the parser rejects

The selected official validator rejects every form below, and a complete-model check or isolated
snippet probe commonly names the replacement in the diagnostic. You do not need to memorize these;
you need to know that a confusing parse error near a familiar keyword often means v1 notation.

| v1 / UML form | What it meant | SysML v2 |
| --- | --- | --- |
| `block def` | structural classifier | `part def`, `item def`, or `attribute def`, by identity |
| `«stereotype»` | lightweight extension | `metadata def` with `@`, or a `#` user keyword |
| `ValueType`, `value property` | value without identity | `attribute def` |
| `association`, `assoc` | typed relationship | `connection def` with `end` features, or a plain reference feature |
| `part property`, `flow property` | owned feature | declare the feature directly: `part wheel : Wheel;` |
| `flow port`, `full port`, `proxy port` | port kinds | `port def` with directed features and `~` conjugation |
| `bdd`, `ibd`, `par`, `stm` | diagram kinds | no diagram syntax; `view def` and `viewpoint def` |
| `struct`, `datatype`, `metaclass` in `.sysml` | KerML root notation | the SysML-layer equivalent |

## Table B — forms that parse cleanly and mean something else

**This is the dangerous class.** Nothing in the tooling catches these: they are
valid SysML v2, so the parser accepts them, and deciding whether they are
*correct* needs a symbol table and knowledge of intent. A lint that guessed here
would produce false positives, and false positives train agents to suppress
warnings, which destroys the gate. So they are documented rather than checked.

| Form | Reads like | Actually means |
| --- | --- | --- |
| `part x : T;` | "x is a T" | **composition.** `x` is owned; its lifetime is bound to the owner and it cannot be shared. |
| `ref part x : T;` | the same thing | **reference.** `T` exists independently and may be referenced elsewhere. |
| `:>` (subsets) | "narrows the inherited feature" | the inherited feature **remains** alongside a new specialising one. Both exist. |
| `:>>` (redefines) | the same thing | the inherited feature is **replaced** in this context. UML `{redefines}` maps here. |
| `= expr` | "a default value" | a **binding**, asserted for all time. A differing value is inconsistent, not merely different. |
| `default = expr` | the same thing | an initial value that may legitimately change. |
| omitted multiplicity | "any number" | **`[1..1]`.** Exactly one, always. This silently over-constrains. |
| `/* comment */` above an element | documentation | an **unowned `Comment`** in the enclosing namespace. Views and exports drop it. |
| `doc /* … */` inside the body | the same thing | documentation genuinely attached to the element. |
| `connection def` | "a relationship" | `Connection :> LinkObject, Part` — it **is a Part**, carrying structural-part semantics. |

The pattern: v1 and UML draw a distinction with a diagram adornment or a
stereotype, and SysML v2 draws it with a keyword that is easy to omit. Omitting
it is always legal and usually wrong.

## Checking, in cost order

1. **Does it exist?** Use the configured construct inventory and active standard-library search.
2. **Does it parse?** Use the configured isolated snippet probe.
3. **What does it mean?** Use the normative reference search. Table B questions live here; the
   parser cannot answer them.
4. **Does the whole model still hold?** Run the configured complete-model validation.

Acceptance is not meaning. A snippet the parser accepts may still make the wrong
claim, which is exactly what Table B is about.

## Worked example

**Question.** An inspection assignment refers to one or more independently existing assets. Should
the asset usage be composite or referential?

1. **State the semantic question without project vocabulary.** Does the
   referring object *own* these, or do they exist independently and get
   referenced?
2. **Check what exists.** Inspect the active standard library to establish the specialization and
   default semantics of the candidate usages.
3. **Retrieve the meaning.** Search for composite versus referential usage. The
   distinction is ownership, not syntax preference.
4. **Probe the form.** Reduce the candidate to the smallest valid package and use the configured
   snippet probe.
5. **Decide.** The assets exist independently of an inspection assignment, so composition would
   assert the wrong lifetime and ownership. A reference usage expresses the required sharing.
6. **Report separately.** The normative basis (the composite-versus-reference
   clause), release-matched library evidence, any project convention or stakeholder decision, and
   anything still inferred.
