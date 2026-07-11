library package BibliotekSoftwareValues {
    private import ScalarValues::*;
    private import ControlFunctions::*;

    doc /* Narrow language-neutral values shared only where no component owns their meaning. */

    attribute def Uuid {
        attribute value : String;
        doc /* Canonical lowercase textual UUID representation. */
    }

    attribute def Timestamp {
        attribute iso8601 : String;
        doc /* An ISO-8601 timestamp with an explicit offset. */
    }

    enum def JsonKind {
        enum nullValue;
        enum booleanValue;
        enum numberValue;
        enum stringValue;
        enum arrayValue;
        enum objectValue;
    }

    abstract attribute def JsonValue {
        attribute kind : JsonKind;
    }

    abstract attribute def JsonScalar :> JsonValue;

    attribute def JsonNull :> JsonScalar {
        :>> kind = JsonKind::nullValue;
    }

    attribute def JsonBoolean :> JsonScalar {
        :>> kind = JsonKind::booleanValue;
        attribute value : Boolean;
    }

    attribute def JsonNumber :> JsonScalar {
        :>> kind = JsonKind::numberValue;
        attribute value : Real;
    }

    attribute def JsonString :> JsonScalar {
        :>> kind = JsonKind::stringValue;
        attribute value : String;
    }

    attribute def JsonArray :> JsonValue {
        :>> kind = JsonKind::arrayValue;
        attribute values[0..*] ordered : JsonValue;
    }

    attribute def JsonMember {
        attribute key : String;
        attribute value : JsonValue;
    }

    attribute def JsonObject :> JsonValue {
        :>> kind = JsonKind::objectValue;
        attribute members[0..*] : JsonMember;
        doc /* Member keys are unique; member order has no semantic meaning. JsonValueEqual therefore compares objects by their key-to-value mapping rather than member occurrence order. */
    }

    calc def JsonValueEqual {
        in left : JsonValue;
        in right : JsonValue;
        doc /* Structural, kind-sensitive JSON equality. Object equality compares the unique key-to-value mapping and ignores member order; array equality preserves element order. */
        return equal : Boolean = left.kind == right.kind and left == right;
    }

    calc def JsonSequenceContains {
        in values[0..*] ordered : JsonValue;
        in candidate : JsonValue;
        return contained : Boolean = values->exists { in value; JsonValueEqual(value, candidate) };
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
