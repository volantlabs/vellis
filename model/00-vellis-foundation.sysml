package VellisFoundation {
    /*
     * Stable participant concepts shared across the Vellis model.
     *
     * This package intentionally models only the distinctions needed by the
     * current use cases: one human owner and software systems that may act on
     * the owner's behalf or interact with Vellis.
     */

    abstract part def Vellis_Actor;

    abstract part def Person :> Vellis_Actor;

    abstract part def Software :> Vellis_Actor;

    part def Vellis_Owner :> Person {
        doc /*
         * The single authoritative human owner of one Vellis installation
         * and its data, applications, automations, and agent integrations.
         */
    }
}
