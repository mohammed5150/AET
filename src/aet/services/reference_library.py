"""The engineering reference library (SDS-016).

A catalogue of authoritative reference documents, their editions, and their
revisions, built on the repositories of SDS-002 §8.9 rather than a store of
its own. It is deliberately project-independent: the same ICAO Annex governs
every project, so a reference belongs to the toolkit, not to one project's
data (SDS-016 §12.1).

The library's job is to make a reference **citable and auditable**, which is
mostly a matter of refusing things:

- a publication catalogued twice under the same authority and number
- a revision registered against a document its edition does not belong to
- a record silently overwritten with different metadata
- a supersession that would quietly retire a revision already retired by
  something else
- a question about what was in force on a date the catalogue cannot answer

Nothing here evaluates an engineering criterion. The library says which
document, edition, revision, and clause a criterion lives in; what the
criterion *requires* belongs to the controlled standards module deferred by
SDS-016 §13.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from aet.core.errors import WorkflowError
from aet.core.logging import StructuredLogger, get_logger
from aet.core.outcome import Outcome
from aet.models.reference import (
    ApplicabilityDimension,
    ApplicabilityVerdict,
    ReferenceCitation,
    ReferenceDocument,
    ReferenceEdition,
    ReferenceRevision,
    ReferenceStatus,
)
from aet.services.persistence import Repositories
from aet.utils.ids import new_id


class ReferenceLibrary:
    """Registration and retrieval over the reference catalogue."""

    def __init__(
        self,
        repositories: Repositories,
        logger: StructuredLogger | None = None,
    ) -> None:
        self._repos = repositories
        self._logger = logger or get_logger("reference-library")

    # -- registration ------------------------------------------------------

    def register_document(
        self, document: ReferenceDocument
    ) -> Outcome[ReferenceDocument]:
        """Catalogue a publication, refusing a conflicting duplicate.

        Re-registering an identical record succeeds and changes nothing, so a
        catalogue can be loaded repeatedly. Re-registering the same identifier
        with different metadata, or the same authority and document number
        under a new identifier, fails: both would leave the catalogue holding
        two answers to one question (SDS-016 §10.1).
        """
        correlation_id = new_id()
        existing = self._repos.reference_documents.get(document.reference_id)
        if existing is not None and existing != document:
            return self._conflict(
                f"Reference '{document.reference_id}' is already catalogued "
                f"with different metadata",
                remediation=(
                    "Register a new reference for a different publication, or "
                    "record a new edition or revision for a changed document."
                ),
                correlation_id=correlation_id,
            )
        clash = next(
            (
                other
                for other in self.documents()
                if other.catalogue_key == document.catalogue_key
                and other.reference_id != document.reference_id
            ),
            None,
        )
        if clash is not None:
            return self._conflict(
                f"{document.authority.label} {document.document_number} is "
                f"already catalogued as '{clash.reference_id}'",
                remediation=(
                    "Use the existing reference, or correct the document "
                    "number if these are different publications."
                ),
                correlation_id=correlation_id,
            )
        self._repos.reference_documents.add(document)
        self._logger.audit(
            f"Reference catalogued: {document.authority.label} "
            f"{document.document_number} — {document.title}",
            operation="register-reference-document",
            correlation_id=correlation_id,
        )
        return Outcome.ok(document, correlation_id=correlation_id)

    def register_edition(self, edition: ReferenceEdition) -> Outcome[ReferenceEdition]:
        """Record one issue of a catalogued publication."""
        correlation_id = new_id()
        if self._repos.reference_documents.get(edition.reference_id) is None:
            return self._unknown(
                f"reference '{edition.reference_id}'",
                "Catalogue the reference document before its editions.",
                correlation_id,
            )
        existing = self._repos.reference_editions.get(edition.edition_id)
        if existing is not None and existing != edition:
            return self._conflict(
                f"Edition '{edition.edition_id}' is already recorded with "
                f"different metadata",
                remediation="Record a revision rather than rewriting an edition.",
                correlation_id=correlation_id,
            )
        clash = next(
            (
                other
                for other in self.editions_of(edition.reference_id)
                if other.edition_key == edition.edition_key
                and other.edition_id != edition.edition_id
            ),
            None,
        )
        if clash is not None:
            return self._conflict(
                f"Edition '{edition.edition}' is already recorded as "
                f"'{clash.edition_id}'",
                remediation="Use the existing edition, or name this one differently.",
                correlation_id=correlation_id,
            )
        self._repos.reference_editions.add(edition)
        self._logger.audit(
            f"Reference edition recorded: {edition.edition}",
            operation="register-reference-edition",
            correlation_id=correlation_id,
        )
        return Outcome.ok(edition, correlation_id=correlation_id)

    def register_revision(
        self, revision: ReferenceRevision
    ) -> Outcome[ReferenceRevision]:
        """Record one amendment state of an edition.

        The revision's document must be the document its edition belongs to.
        Accepting a mismatch would let a finding cite an amendment of one
        publication as if it amended another.
        """
        correlation_id = new_id()
        edition = self._repos.reference_editions.get(revision.edition_id)
        if edition is None:
            return self._unknown(
                f"edition '{revision.edition_id}'",
                "Record the edition before its revisions.",
                correlation_id,
            )
        if edition.reference_id != revision.reference_id:
            return self._conflict(
                f"Revision '{revision.revision}' names reference "
                f"'{revision.reference_id}', but its edition belongs to "
                f"'{edition.reference_id}'",
                remediation="Record the revision against its own edition.",
                correlation_id=correlation_id,
            )
        existing = self._repos.reference_revisions.get(revision.revision_id)
        if existing is not None and existing != revision:
            return self._conflict(
                f"Revision '{revision.revision_id}' is already recorded with "
                f"different metadata",
                remediation=(
                    "Record a new revision and supersede the old one, so the "
                    "history stays readable."
                ),
                correlation_id=correlation_id,
            )
        clash = next(
            (
                other
                for other in self.revisions_of_edition(revision.edition_id)
                if other.revision_key == revision.revision_key
                and other.revision_id != revision.revision_id
            ),
            None,
        )
        if clash is not None:
            return self._conflict(
                f"Revision '{revision.revision}' is already recorded as "
                f"'{clash.revision_id}'",
                remediation="Use the existing revision, or name this one differently.",
                correlation_id=correlation_id,
            )
        self._repos.reference_revisions.add(revision)
        self._logger.audit(
            f"Reference revision recorded: {revision.revision} " f"({revision.status})",
            operation="register-reference-revision",
            correlation_id=correlation_id,
        )
        return Outcome.ok(revision, correlation_id=correlation_id)

    def supersede(
        self,
        superseded_revision_id: str,
        superseding_revision_id: str,
        *,
        on: date | None = None,
    ) -> Outcome[ReferenceRevision]:
        """Retire one revision in favour of another, explicitly.

        Supersession is the only way a revision leaves force, and it never
        deletes anything: the retired revision keeps its record, gains
        ``SUPERSEDED`` status, the date it was retired, and a pointer to what
        replaced it. Findings that cited it stay readable, and the chain from
        an old finding to the text it relied on stays walkable
        (SDS-016 §10.2).

        Returns the retired revision — the record this call changed.
        """
        correlation_id = new_id()
        superseded = self._repos.reference_revisions.get(superseded_revision_id)
        superseding = self._repos.reference_revisions.get(superseding_revision_id)
        if superseded is None:
            return self._unknown(
                f"revision '{superseded_revision_id}'",
                "Record the revision before superseding it.",
                correlation_id,
            )
        if superseding is None:
            return self._unknown(
                f"revision '{superseding_revision_id}'",
                "Record the superseding revision first.",
                correlation_id,
            )
        if superseded_revision_id == superseding_revision_id:
            return self._conflict(
                "A revision cannot supersede itself",
                remediation="Name the revision that replaces it.",
                correlation_id=correlation_id,
            )
        if superseded.reference_id != superseding.reference_id:
            return self._conflict(
                "A revision can only be superseded by a revision of the same "
                "reference document",
                remediation=(
                    "Withdraw the revision instead if a different publication "
                    "replaced it."
                ),
                correlation_id=correlation_id,
            )
        if superseding.status is not ReferenceStatus.IN_FORCE:
            return self._conflict(
                f"Revision '{superseding.revision}' is {superseding.status}, so "
                f"it cannot supersede anything",
                remediation="Bring the superseding revision into force first.",
                correlation_id=correlation_id,
            )
        already = superseded.superseded_by_revision_id
        if already and already != superseding_revision_id:
            return self._conflict(
                f"Revision '{superseded.revision}' was already superseded by "
                f"'{already}'",
                remediation=(
                    "Correct the catalogue rather than recording a second "
                    "supersession of the same revision."
                ),
                correlation_id=correlation_id,
            )

        superseded.status = ReferenceStatus.SUPERSEDED
        superseded.superseded_by_revision_id = superseding_revision_id
        superseded.superseded_date = on or superseding.effective_date
        superseding.supersedes_revision_id = superseded_revision_id
        self._repos.reference_revisions.add(superseded)
        self._repos.reference_revisions.add(superseding)
        self._logger.audit(
            f"Reference revision '{superseded.revision}' superseded by "
            f"'{superseding.revision}'",
            operation="supersede-reference-revision",
            correlation_id=correlation_id,
        )
        return Outcome.ok(superseded, correlation_id=correlation_id)

    # -- retrieval ---------------------------------------------------------

    def document(self, reference_id: str) -> ReferenceDocument | None:
        """One catalogued publication, or ``None`` if it is not catalogued."""
        return self._repos.reference_documents.get(reference_id)

    def documents(self) -> list[ReferenceDocument]:
        """Every catalogued publication."""
        return self._repos.reference_documents.list()

    def edition(self, edition_id: str) -> ReferenceEdition | None:
        """One recorded edition, or ``None``."""
        return self._repos.reference_editions.get(edition_id)

    def editions_of(self, reference_id: str) -> list[ReferenceEdition]:
        """Every recorded edition of one publication."""
        return [
            edition
            for edition in self._repos.reference_editions.list()
            if edition.reference_id == reference_id
        ]

    def revision(self, revision_id: str) -> ReferenceRevision | None:
        """One recorded revision, or ``None``."""
        return self._repos.reference_revisions.get(revision_id)

    def revisions_of_edition(self, edition_id: str) -> list[ReferenceRevision]:
        """Every recorded revision of one edition."""
        return [
            revision
            for revision in self._repos.reference_revisions.list()
            if revision.edition_id == edition_id
        ]

    def revisions_of(self, reference_id: str) -> list[ReferenceRevision]:
        """Every recorded revision of one publication, across its editions."""
        return [
            revision
            for revision in self._repos.reference_revisions.list()
            if revision.reference_id == reference_id
        ]

    def revision_in_force(
        self, reference_id: str, *, on: date | None = None
    ) -> Outcome[ReferenceRevision]:
        """The revision in force now, or on a stated day.

        Fails rather than guessing. No candidate, two candidates, or a
        candidate whose effective date the catalogue does not record are all
        reported as failures with the reason named, because each means the
        catalogue cannot answer the question — and an engineering check run
        against a guessed revision is worse than one that did not run
        (SDS-016 §10.4).
        """
        correlation_id = new_id()
        if self._repos.reference_documents.get(reference_id) is None:
            return self._unknown(
                f"reference '{reference_id}'",
                "Catalogue the reference document first.",
                correlation_id,
            )
        revisions = self.revisions_of(reference_id)
        if on is None:
            candidates = [revision for revision in revisions if revision.is_current]
        else:
            historic = [
                revision
                for revision in revisions
                if revision.status
                in (ReferenceStatus.IN_FORCE, ReferenceStatus.SUPERSEDED)
            ]
            undated = [
                revision.revision
                for revision in historic
                if revision.effective_date is None
            ]
            if undated:
                return self._conflict(
                    f"The catalogue records no effective date for revision(s) "
                    f"{', '.join(sorted(undated))}, so what was in force on "
                    f"{on.isoformat()} cannot be determined",
                    remediation="Record the effective date of every revision.",
                    correlation_id=correlation_id,
                )
            candidates = [
                revision
                for revision in historic
                # mypy: the undated guard above proved these are not None.
                if revision.effective_date is not None
                and revision.effective_date <= on
                and (revision.superseded_date is None or on < revision.superseded_date)
            ]
        if not candidates:
            when = f" on {on.isoformat()}" if on else ""
            return self._conflict(
                f"No revision of reference '{reference_id}' is in force{when}",
                remediation=(
                    "Record the revision that applies, and its effective date."
                ),
                correlation_id=correlation_id,
            )
        if len(candidates) > 1:
            names = ", ".join(sorted(revision.revision for revision in candidates))
            when = f" on {on.isoformat()}" if on else ""
            return self._conflict(
                f"{len(candidates)} revisions of reference '{reference_id}' are "
                f"recorded in force{when}: {names}",
                remediation=(
                    "Record the supersession between them so one revision is "
                    "current."
                ),
                correlation_id=correlation_id,
            )
        return Outcome.ok(candidates[0], correlation_id=correlation_id)

    # -- citation and applicability ---------------------------------------

    def cite(
        self,
        revision_id: str,
        *,
        section: str = "",
        clause: str = "",
        criterion_id: str = "",
    ) -> Outcome[ReferenceCitation]:
        """Build the citation a validation finding carries.

        Assembled from the stored records rather than from strings a caller
        supplies, so a citation cannot claim an edition or revision the
        catalogue does not hold. A superseded revision may be cited — a
        historical run cited what was in force at the time, and re-stating it
        later must stay possible.
        """
        correlation_id = new_id()
        revision = self._repos.reference_revisions.get(revision_id)
        if revision is None:
            return self._unknown(
                f"revision '{revision_id}'",
                "Record the revision before citing it.",
                correlation_id,
            )
        edition = self._repos.reference_editions.get(revision.edition_id)
        if edition is None:
            return self._unknown(
                f"edition '{revision.edition_id}'",
                "Record the edition the revision amends.",
                correlation_id,
            )
        document = self._repos.reference_documents.get(revision.reference_id)
        if document is None:
            return self._unknown(
                f"reference '{revision.reference_id}'",
                "Catalogue the reference document the revision belongs to.",
                correlation_id,
            )
        return Outcome.ok(
            ReferenceCitation(
                reference_id=document.reference_id,
                document_number=document.document_number,
                authority=document.authority,
                edition=edition.edition,
                revision=revision.revision,
                revision_id=revision.revision_id,
                section=section,
                clause=clause,
                criterion_id=criterion_id,
            ),
            correlation_id=correlation_id,
        )

    def evaluate_applicability(
        self,
        reference_id: str,
        context: Mapping[ApplicabilityDimension, str],
    ) -> Outcome[ApplicabilityVerdict]:
        """Whether a catalogued reference applies to a stated context."""
        correlation_id = new_id()
        document = self._repos.reference_documents.get(reference_id)
        if document is None:
            return self._unknown(
                f"reference '{reference_id}'",
                "Catalogue the reference document first.",
                correlation_id,
            )
        return Outcome.ok(
            document.applicability.evaluate(context), correlation_id=correlation_id
        )

    # -- helpers -----------------------------------------------------------

    def _conflict[T](
        self,
        message: str,
        *,
        remediation: str,
        correlation_id: str,
    ) -> Outcome[T]:
        """A catalogue state conflict, reported rather than resolved."""
        error = WorkflowError(message, remediation=remediation)
        self._logger.error(
            message,
            operation="reference-library",
            correlation_id=correlation_id,
            error_code=error.code,
        )
        return Outcome.from_error(error, correlation_id=correlation_id)

    def _unknown[T](
        self, subject: str, remediation: str, correlation_id: str
    ) -> Outcome[T]:
        return self._conflict(
            f"Unknown {subject}",
            remediation=remediation,
            correlation_id=correlation_id,
        )
