# Use-Case-First Model-Based Software Development with SysML v2

This model is organized as a practical starting point for model-native software development rather than as a complete architecture.

## 1. Establish system boundaries and valued outcomes

Start with:

- the owner and external participants,
- the Vellis system boundary,
- the RTG subsystem boundary,
- externally valuable use cases,
- the minimum information exchanged across those boundaries.

Avoid beginning with controllers, repositories, adapters, services, managers, queues, or deployment processes.

## 2. Keep use cases black-box

A use case should state:

- its subject,
- its external actors,
- its objective,
- externally observable interaction ordering.

Do not allocate the use case to internal design elements yet. Do not express a validation algorithm as a linear use-case sequence unless failure and alternate outcomes are modeled explicitly.

## 3. Instantiate reusable use cases in contexts

Use-case definitions remain reusable. Context packages bind their inherited subject and actor parameters to concrete participants. This makes the selected system boundary and external environment explicit without coupling the reusable behavior to one deployment.

## 4. Add requirements when a use case reveals a necessary guarantee

Examples in this model:

- durable history follows from recovery, audit, and time travel,
- atomic state changes follow from governed graph mutation,
- provenance follows from agents and automations acting for the owner,
- simplicity requirements follow from the turn-key single-owner product intent.

Prefer requirement statements about externally meaningful properties. Derive internal requirements only after selecting a logical design.

## 5. Introduce white-box design incrementally

Add an internal part, action, or service only when at least one of the following is true:

- a use case cannot be realized without assigning a distinct responsibility,
- a requirement needs a clear satisfying element,
- a failure boundary or lifecycle requires independent identity,
- a trade study needs an explicit alternative.

A useful review question is: **What model element would become false or unrealizable if this design element were removed?** If there is no answer, defer it.

## 6. Derive implementation slices from the model

For each implementation increment:

1. Select one use-case scenario and its requirements.
2. Define only the request/result data needed by that scenario.
3. Add the smallest logical behavior that realizes it.
4. Allocate behavior only where responsibility is unclear without allocation.
5. Add verification cases before asking implementation agents to build the slice.
6. Require implementation changes to reference the model elements they realize.
7. Validate the SysML model and implementation tests in the same change set.

## 7. Use the model as an agent contract

An implementation-agent task should identify:

- the use-case usage being implemented,
- the requirements it must satisfy,
- the service requests and responses involved,
- the allowed model and generated-source roots to change,
- the verification cases that must pass,
- explicit non-goals.

This limits local optimization and prevents agents from inventing generalized infrastructure that is not present in the system model.

## 8. Preserve intentional minimalism

Current explicit non-goals include:

- enterprise multi-tenancy,
- organization or team administration,
- complex RBAC,
- microservice decomposition,
- distributed consensus,
- high-availability clustering,
- generic workflow engines,
- service meshes,
- pluggable persistence abstractions without a demonstrated need.

Intentional minimalism does not remove core integrity. Durable state history, deterministic recovery, atomic committed changes, and understandable provenance are fundamental to trusted personal memory and agent activity.

It also does not erase compatibility-critical domain distinctions. The RTG user graph keeps stable anchors, typed associated data objects, typed directed links, and direct identity-free anchor-data associations explicit while leaving indexes, persistence layout, query algorithms, and protocol encodings to realizations.
