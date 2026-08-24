# Modeling altitude

The construct vocabulary does not change with altitude. What changes is what the model claims, and
therefore what it forbids. The same subject below — reviewing a submitted claim — is expressed three
ways. Read them together: the difference between them is the decision, not the syntax.

Nothing here obliges a model to reach software altitude. Model at the altitude the project means to
govern, and leave the rest to the implementer.

## Process altitude

The claim is who does what, in what order, across organizational boundaries. It forbids a review
that never reaches an adjudicator.

```sysml
package 'Claim Review Process' {
    part def Reviewer;
    part def Adjudicator;
    item def 'Submitted Claim';

    action def 'Review Claim' {
        in item claim : 'Submitted Claim';
        action assess;
        then action adjudicate;
    }
}
```

## System altitude

The claim is what the system is responsible for and what must hold. It forbids adjudicating a claim
that was never assessed, and forbids a decision without a recorded assessment.

```sysml
package 'Claim Review System' {
    item def 'Submitted Claim';
    item def Assessment;
    item def Decision;

    part def 'Review Service' {
        action assess {
            in item claim : 'Submitted Claim';
            out item assessment : Assessment;
        }
        action adjudicate {
            in item assessment : Assessment;
            out item decision : Decision;
        }
    }

    requirement def 'Decision Follows Assessment' {
        subject service : 'Review Service';
        require constraint { service.adjudicate.assessment != null }
    }
}
```

## Software altitude

The claim is that assessment and adjudication are separate boundaries, and that adjudication may not
reach into assessment state. It forbids one code unit that both scores a claim and decides it, and
forbids adjudication reading assessment's store directly.

Model this only when a competent fresh implementer merging the two would be a defect rather than a
legitimate choice. Where it is modeled, say what it forbids.

```sysml
package 'Claim Review Software' {
    item def Assessment;
    item def Decision;

    port def 'Assessment Access';

    part def 'Assessment Store' {
        port provides : 'Assessment Access';
        item held : Assessment[0..*];
    }

    part def 'Adjudication Engine' {
        port reads : ~'Assessment Access';
        item produced : Decision[0..*];
    }

    part def 'Review Service' {
        part store : 'Assessment Store';
        part engine : 'Adjudication Engine';
        connect store.provides to engine.reads;
    }

    requirement def 'Adjudication Does Not Own Assessments' {
        subject service : 'Review Service';
        require constraint {
        doc /*
         * Assessments shall be held only by the assessment store. An adjudication
         * engine that holds them does not conform, and neither does one code unit
         * realizing both parts.
         */
        }
    }
}
```
