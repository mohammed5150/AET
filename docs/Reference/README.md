# Engineering Reference Library

This directory documents how AET refers to authoritative engineering
references. **It holds none of them.**

AET records where a reference document is; it never opens, copies, downloads,
parses, or redistributes one. The reasoning is in
[ADR-003](../ADR/ADR-003-controlled-reference-documents.md); the architecture
is in
[SDS-016](../SDS/SDS-016-Engineering-Reference-and-Standards-Architecture.md).

## What is in version control

- this README
- `.gitignore`, which refuses document binaries so a controlled document
  dropped in here while working cannot be committed by mistake

Nothing else. There are no placeholder directories, because empty directories
holding nothing serve nobody.

## Where the documents live

On whatever controlled storage the operator already uses — the network share,
the document-control system, the licensed reader. `local_reference_path` on a
`ReferenceSource` points there, and is expected to differ between machines. A
catalogue entry is citable whether or not the path resolves on this one:
authority, document number, edition, and revision identify the document.

The layout below is a recommendation for that storage, mirrored here only so
paths recorded in the catalogue stay predictable:

```text
<controlled storage>/AGL/
├── ICAO/
├── UAE_GCAA/
├── FAA/
├── EASA/
├── Airport_Specific/
└── Other/
```

## Before adding anything here

Ask whether the document may lawfully be published from a public repository.
For ICAO, GCAA, FAA, and EASA material, for aerodrome design standards, and
for project specifications, the answer is usually no — and a document
committed once stays in the git history after any later deletion.

If a document genuinely is freely redistributable, record that explicitly on
its revision: a `PUBLIC_OFFICIAL` source type, a `PUBLIC` licence status, and
`OPEN` access. An uncharacterised document is treated as restricted.

## Cataloguing a reference

```python
from datetime import date

from aet.models.reference import (
    LicenceStatus,
    ReferenceAuthority,
    ReferenceDocument,
    ReferenceEdition,
    ReferenceObligation,
    ReferenceRevision,
    ReferenceSource,
    ReferenceSourceType,
    ReferenceType,
)
from aet.services.reference_library import ReferenceLibrary

library = ReferenceLibrary(repositories)

document = ReferenceDocument(
    title="Aerodromes — Volume I — Aerodrome Design and Operations",
    authority=ReferenceAuthority.ICAO,
    document_number="Annex 14 Vol I",
    document_type=ReferenceType.SARP,
    # An Annex mixes Standards with Recommended Practices, so neither
    # MANDATORY nor GUIDANCE describes the whole publication.
    obligation=ReferenceObligation.MIXED,
    discipline="airfield-ground-lighting",
)
library.register_document(document)

edition = ReferenceEdition(
    reference_id=document.reference_id,
    edition="8th Edition",
    publication_date=date(2022, 7, 1),
)
library.register_edition(edition)

library.register_revision(
    ReferenceRevision(
        reference_id=document.reference_id,
        edition_id=edition.edition_id,
        revision="Amendment 17",
        effective_date=date(2023, 11, 30),
        source=ReferenceSource(
            source_type=ReferenceSourceType.USER_PROVIDED,
            licence_status=LicenceStatus.RESTRICTED,
            official_url="https://www.icao.int/",
            local_reference_path="/mnt/controlled/AGL/ICAO/annex14-v1-amd17.pdf",
        ),
    )
)
```

## Citing a clause

A citation locates the text through an ordered path, to whatever depth the
publisher's own structure has:

```python
from aet.models.reference import LocatorKind, LocatorPart

library.cite(
    amendment_17_revision_id,
    location=[
        LocatorPart(LocatorKind.CHAPTER, "5"),
        LocatorPart(LocatorKind.SUBSECTION, "5.3.17"),
        LocatorPart(LocatorKind.PARAGRAPH, "5.3.17.5"),
    ],
)
```

Use `LocatorKind.OTHER` for a locator whose form none of the kinds describes —
an EASA rule reference such as `CS ADR-DSN.M.615`, or a GCAA Subpart. Record
the value exactly as the publisher prints it. The shorthand
`cite(..., section=..., clause=...)` remains valid for the simple two-level
case, but a citation states its location one way or the other, never both.

Editions and revisions are recorded as the publisher states them. AET does not
verify that a revision is still current — that requires consulting the
publisher, and a filename that looks current is not evidence that a document
is.
