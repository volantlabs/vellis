library package BibliotekRtgDiagnostics {
    private import ScalarValues::*;

    attribute def RtgDiagnostic {
        attribute code : String;
        attribute 'message' : String;
        attribute path[0..*] : String;
        attribute remedy : String;
    }
}
