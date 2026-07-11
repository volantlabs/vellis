library package BibliotekSoftwareValues {
    private import ScalarValues::*;

    doc /* Narrow language-neutral values shared only where no component owns their meaning. */

    attribute def Uuid {
        attribute value : String;
        doc /* Canonical lowercase textual UUID representation. */
    }

    attribute def Timestamp {
        attribute iso8601 : String;
        doc /* An ISO-8601 timestamp with an explicit offset. */
    }

    attribute def JsonScalar {
        doc /* One JSON null, Boolean, number, or string value. Boolean and number are distinct kinds. */
    }

    attribute def JsonValue {
        doc /* A JSON scalar, array of JSON values, or object with string keys and JSON values. */
    }

    attribute def JsonObject :> JsonValue {
        doc /* A JSON value whose top-level kind is object. */
    }

    attribute def FileSystemRootPath {
        attribute value : String;
        doc /* Caller-supplied filesystem root; unlike a document path, it is not relative to itself. */
    }

    attribute def FileSystemFilePath {
        attribute value : String;
        doc /* Caller-supplied filesystem file path, not a directory root or component-relative document path. */
    }
}
