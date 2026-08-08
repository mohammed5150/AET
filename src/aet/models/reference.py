"""Engineering reference library domain models (SDS-016).

AET treats the DWG as the single source of truth for *project-derived*
engineering data. It is not a source of truth for the criteria that data is
judged against: those come from ICAO, the UAE GCAA, an aerodrome's own design
standards, a manufacturer's manual, or a project specification. This module
models the documents themselves — who published them, which edition and
revision, what they may be used for, and whether AET is allowed to hold a copy.

Nothing here states an engineering limit. A reference document records *where*
a criterion is written down; the criterion itself belongs to a controlled
standards module that SDS-016 §13 defers deliberately (SDS-012 §4 explains why
a limit asserted from memory is worse than no limit at all).

Three records, because a reference is not one thing:

``ReferenceDocument``
    The publication as an identity — ICAO Annex 14 Volume I — independent of
    which edition is on the shelf.
``ReferenceEdition``
    One issue of that publication: the 8th Edition, the 2022 issue.
``ReferenceRevision``
    One amendment state of an edition, with the dates that decide what was in
    force when. This is the record a validation finding cites, because
    "Annex 14" without an amendment does not identify a requirement.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from aet.core.errors import InputError
from aet.utils.ids import new_id, utc_now


class ReferenceAuthority(StrEnum):
    """Who published a reference (SDS-016 §6).

    The authority identifies the *source* only. It carries no engineering
    criteria and confers no automatic precedence: which authority governs a
    given project is a matter for the project's applicable regulations, not
    for this enumeration.
    """

    ICAO = "icao"
    UAE_GCAA = "uae-gcaa"
    FAA = "faa"
    EASA = "easa"
    AIRPORT_AUTHORITY = "airport-authority"
    MANUFACTURER = "manufacturer"
    PROJECT_STANDARD = "project-standard"
    OTHER = "other"

    @property
    def label(self) -> str:
        """The authority as it is written in a citation."""
        return _AUTHORITY_LABELS[self]


_AUTHORITY_LABELS: dict[ReferenceAuthority, str] = {
    ReferenceAuthority.ICAO: "ICAO",
    ReferenceAuthority.UAE_GCAA: "UAE GCAA",
    ReferenceAuthority.FAA: "FAA",
    ReferenceAuthority.EASA: "EASA",
    ReferenceAuthority.AIRPORT_AUTHORITY: "Airport Authority",
    ReferenceAuthority.MANUFACTURER: "Manufacturer",
    ReferenceAuthority.PROJECT_STANDARD: "Project Standard",
    ReferenceAuthority.OTHER: "Other",
}


class ReferenceType(StrEnum):
    """What kind of document a reference is (SDS-016 §7)."""

    REGULATION = "regulation"
    STANDARD = "standard"
    SARP = "sarp"
    PANS = "pans"
    MANUAL = "manual"
    AMC = "amc"
    GM = "gm"
    SOP = "sop"
    CIRCULAR = "circular"
    SAFETY_DECISION = "safety-decision"
    SAFETY_INFORMATION_BULLETIN = "safety-information-bulletin"
    ENGINEERING_STANDARD = "engineering-standard"
    AIRPORT_STANDARD = "airport-standard"
    TECHNICAL_GUIDANCE = "technical-guidance"
    OTHER = "other"


class ReferenceObligation(StrEnum):
    """How binding a document's material is (SDS-016 §7.1).

    Recorded per document rather than derived from :class:`ReferenceType`,
    because the type does not settle it: an ICAO Annex mixes Standards with
    Recommended Practices, and an AMC is neither mandatory nor merely
    advisory. A document whose material is not uniform is ``MIXED``, which
    says the obligation is decided clause by clause rather than pretending
    one answer covers the whole publication.
    """

    MANDATORY = "mandatory"
    RECOMMENDED = "recommended"
    GUIDANCE = "guidance"
    MIXED = "mixed"

    @property
    def carries_mandatory_material(self) -> bool:
        """Whether anything in the document can impose a requirement."""
        return self in (ReferenceObligation.MANDATORY, ReferenceObligation.MIXED)


class ReferenceStatus(StrEnum):
    """Lifecycle status of one revision (SDS-016 §10)."""

    DRAFT = "draft"
    IN_FORCE = "in-force"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


class ReferenceSourceType(StrEnum):
    """How AET came to know about a document (SDS-016 §11)."""

    #: Published openly by the authority and freely redistributable.
    PUBLIC_OFFICIAL = "public-official"
    #: Supplied by the operator from their own holdings.
    USER_PROVIDED = "user-provided"
    #: A copy held under a licence that permits local use only.
    LICENSED_COPY = "licensed-copy"
    #: Access is controlled by the publisher or the aerodrome.
    RESTRICTED = "restricted"
    #: AET holds metadata and a link, and no copy of the document at all.
    METADATA_ONLY = "metadata-only"


class LicenceStatus(StrEnum):
    """What the copyright position permits (SDS-016 §11)."""

    PUBLIC = "public"
    LICENSED = "licensed"
    RESTRICTED = "restricted"
    #: Not established. Treated as restricted, never as permissive.
    UNKNOWN = "unknown"


class AccessRestriction(StrEnum):
    """Who may read the held copy (SDS-016 §11)."""

    OPEN = "open"
    INTERNAL = "internal"
    CONTROLLED = "controlled"
    CONFIDENTIAL = "confidential"


@dataclass(frozen=True, slots=True)
class ReferenceSource:
    """Where a revision came from, and what may be done with it.

    The defaults are the safe ones: a source nobody has characterised holds no
    copy, has an unestablished licence, and is access-controlled. Getting the
    metadata wrong in this direction costs an operator one catalogue edit;
    getting it wrong in the other direction publishes somebody's copyrighted
    document (SDS-016 §11.2).

    AET never opens the file at ``local_reference_path``. The path is recorded
    so an engineer can find the document; nothing in the toolkit reads, copies,
    downloads, or embeds it.
    """

    source_type: ReferenceSourceType = ReferenceSourceType.METADATA_ONLY
    licence_status: LicenceStatus = LicenceStatus.UNKNOWN
    official_url: str = ""
    local_reference_path: str = ""
    access_restriction: AccessRestriction = AccessRestriction.CONTROLLED

    def __post_init__(self) -> None:
        """Reject a source that contradicts itself."""
        if (
            self.source_type is ReferenceSourceType.METADATA_ONLY
            and self.local_reference_path
        ):
            raise InputError(
                "A metadata-only source cannot name a local copy of the document",
                remediation=(
                    "Record the source type that matches the copy actually held "
                    "(user-provided, licensed-copy, restricted, or "
                    "public-official), or clear local_reference_path."
                ),
            )

    @property
    def redistributable(self) -> bool:
        """Whether the held copy may lawfully be published onward.

        True only when all three of source type, licence, and access agree
        that it may. An unknown licence is not a permissive one, so the
        default source answers ``False`` (SDS-016 §11.2).
        """
        return (
            self.source_type is ReferenceSourceType.PUBLIC_OFFICIAL
            and self.licence_status is LicenceStatus.PUBLIC
            and self.access_restriction is AccessRestriction.OPEN
        )


class ApplicabilityDimension(StrEnum):
    """A condition under which a reference applies (SDS-016 §9)."""

    COUNTRY = "country"
    AUTHORITY = "authority"
    AIRPORT = "airport"
    AERODROME = "aerodrome"
    RUNWAY = "runway"
    TAXIWAY = "taxiway"
    AIRCRAFT_CATEGORY = "aircraft-category"
    APPROACH_CATEGORY = "approach-category"
    LIGHTING_SYSTEM = "lighting-system"
    PROJECT_TYPE = "project-type"
    DESIGN_STAGE = "design-stage"
    DISCIPLINE = "discipline"


class ApplicabilityVerdict(StrEnum):
    """Whether a reference applies to a stated context (SDS-016 §9.2)."""

    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not-applicable"
    #: The context does not say enough to decide. Never treated as applicable.
    UNDETERMINED = "undetermined"


@dataclass(frozen=True, slots=True)
class ApplicabilityCriterion:
    """One dimension a reference is restricted to, and its permitted values."""

    dimension: ApplicabilityDimension
    values: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.values:
            raise InputError(
                f"Applicability criterion for '{self.dimension}' lists no values",
                remediation=(
                    "List the values the reference applies to, or omit the "
                    "criterion entirely to leave the dimension unrestricted."
                ),
            )

    def matches(self, stated: str) -> bool:
        """Whether a stated context value falls inside this restriction."""
        return stated.strip().casefold() in {
            value.strip().casefold() for value in self.values
        }


@dataclass(frozen=True, slots=True)
class ReferenceApplicability:
    """The conditions under which a reference applies.

    An unlisted dimension is unrestricted. Listing none at all means the
    reference applies everywhere, which is the right default for an ICAO Annex
    and the wrong one for an airport's own standard — so it is stated, not
    assumed.
    """

    criteria: tuple[ApplicabilityCriterion, ...] = ()

    def evaluate(
        self, context: Mapping[ApplicabilityDimension, str]
    ) -> ApplicabilityVerdict:
        """Decide whether this reference applies to a stated context.

        A definite exclusion wins over a gap: if the context contradicts any
        restriction the answer is ``NOT_APPLICABLE`` even when other
        dimensions are unstated. Otherwise an unstated restricted dimension
        yields ``UNDETERMINED`` rather than ``APPLICABLE``, because a
        reference silently assumed to apply is how the wrong standard gets
        cited (SDS-016 §9.2).
        """
        undetermined = False
        for criterion in self.criteria:
            stated = context.get(criterion.dimension, "").strip()
            if not stated:
                undetermined = True
                continue
            if not criterion.matches(stated):
                return ApplicabilityVerdict.NOT_APPLICABLE
        if undetermined:
            return ApplicabilityVerdict.UNDETERMINED
        return ApplicabilityVerdict.APPLICABLE


@dataclass(slots=True)
class ReferenceDocument:
    """A catalogued publication, independent of edition (SDS-016 §8.1)."""

    title: str
    authority: ReferenceAuthority
    document_number: str
    document_type: ReferenceType
    obligation: ReferenceObligation
    discipline: str = ""
    jurisdiction: str = ""
    applicability: ReferenceApplicability = field(
        default_factory=ReferenceApplicability
    )
    notes: str = ""
    reference_id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise InputError(
                "A reference document must have a title",
                remediation="Give the document its published title.",
            )
        if not self.document_number.strip():
            raise InputError(
                f"Reference '{self.title}' has no document number",
                remediation=(
                    "Give the document its published number, or a controlled "
                    "internal number for an unnumbered project standard."
                ),
            )

    @property
    def catalogue_key(self) -> str:
        """Authority and document number, the identity an operator knows.

        Two catalogue entries sharing this key are the same publication
        recorded twice, which the library refuses (SDS-016 §10.1).
        """
        return f"{self.authority.value}:{self.document_number.strip().casefold()}"

    @property
    def carries_mandatory_material(self) -> bool:
        """Whether anything in this document can impose a requirement."""
        return self.obligation.carries_mandatory_material


@dataclass(slots=True)
class ReferenceEdition:
    """One issue of a publication (SDS-016 §8.2)."""

    reference_id: str
    edition: str
    publication_date: date | None = None
    supersedes_edition_id: str = ""
    notes: str = ""
    edition_id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.edition.strip():
            raise InputError(
                "A reference edition must be named",
                remediation="Record the edition as the publisher states it.",
            )

    @property
    def edition_key(self) -> str:
        """Document and edition, the identity within a catalogue."""
        return f"{self.reference_id}:{self.edition.strip().casefold()}"


@dataclass(slots=True)
class ReferenceRevision:
    """One amendment state of an edition (SDS-016 §8.3, §10).

    This is the record a validation finding cites. ``reference_id`` is carried
    here as well as on the edition so every revision of a publication can be
    found without walking editions; the library refuses a revision whose
    document disagrees with its edition's, so the two cannot drift.
    """

    reference_id: str
    edition_id: str
    revision: str
    status: ReferenceStatus = ReferenceStatus.IN_FORCE
    publication_date: date | None = None
    effective_date: date | None = None
    superseded_date: date | None = None
    supersedes_revision_id: str = ""
    superseded_by_revision_id: str = ""
    source: ReferenceSource = field(default_factory=ReferenceSource)
    notes: str = ""
    revision_id: str = field(default_factory=new_id)
    recorded_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.revision.strip():
            raise InputError(
                "A reference revision must be named",
                remediation=(
                    "Record the amendment as the publisher states it, or "
                    "'base' for an edition issued without amendments."
                ),
            )

    @property
    def revision_key(self) -> str:
        """Edition and revision, the identity within a catalogue."""
        return f"{self.edition_id}:{self.revision.strip().casefold()}"

    @property
    def is_current(self) -> bool:
        """Whether this revision is in force and not superseded."""
        return (
            self.status is ReferenceStatus.IN_FORCE
            and not self.superseded_by_revision_id
        )


@dataclass(frozen=True, slots=True)
class ReferenceCitation:
    """An immutable pointer to the exact text a finding relies on.

    Frozen and self-describing on purpose. A finding carries the citation by
    value, so a later amendment to the catalogue cannot rewrite what an
    already-executed validation run cited — the auditability requirement of
    SDS-016 §10.3. It records identity and location only: whether the cited
    clause is mandatory is a property of the document and, for a ``MIXED``
    publication, of the clause, so the citation resolves rather than asserts it.
    """

    reference_id: str
    document_number: str
    authority: ReferenceAuthority
    edition: str
    revision: str
    revision_id: str = ""
    section: str = ""
    clause: str = ""
    #: Identifier of the controlled criterion this citation supports, once a
    #: criteria module exists to define one (SDS-016 §13.1).
    criterion_id: str = ""

    def __str__(self) -> str:
        """The citation as it appears in a report."""
        parts = [f"{self.authority.label} {self.document_number}".strip()]
        parts.append(self.edition)
        if self.revision:
            parts.append(f"Rev {self.revision}")
        if self.section:
            parts.append(f"§{self.section}")
        if self.clause:
            parts.append(f"clause {self.clause}")
        return ", ".join(part for part in parts if part)
