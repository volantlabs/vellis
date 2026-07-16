library package BibliotekRtgChangeValues {
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;

    attribute def RtgResourceIdentifier {
        attribute uuid[0..1] : Uuid;
        attribute migrationId[0..1] : String;
        doc /* Exactly one representation identifies an existing or caller-assigned RTG resource. */
    }
    attribute def RtgChangeReference {
        attribute resourceId[0..1] : RtgResourceIdentifier;
        attribute localRef[0..1] : String;
        doc /* Exactly one existing/caller identity or one batch-local identity identifies a target. */
    }
}
