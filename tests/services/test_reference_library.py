"""Tests for SDS-016: the engineering reference library service."""

from dataclasses import replace
from datetime import date

import pytest

from aet.core.errors import WorkflowError
from aet.models.reference import (
    AccessRestriction,
    ApplicabilityCriterion,
    ApplicabilityDimension,
    ApplicabilityVerdict,
    LicenceStatus,
    ReferenceApplicability,
    ReferenceAuthority,
    ReferenceDocument,
    ReferenceEdition,
    ReferenceObligation,
    ReferenceRevision,
    ReferenceSource,
    ReferenceSourceType,
    ReferenceStatus,
    ReferenceType,
)
from aet.models.validation import (
    RunStatus,
    Severity,
    ValidationResult,
    ValidationRun,
)
from aet.services.persistence import in_memory_repositories
from aet.services.reference_library import ReferenceLibrary
from aet.services.serialization import from_document, to_document
from aet.services.sqlite import all_tables, connect, sqlite_repositories


@pytest.fixture
def library() -> ReferenceLibrary:
    return ReferenceLibrary(in_memory_repositories())


def _annex14() -> ReferenceDocument:
    return ReferenceDocument(
        title="Aerodromes — Volume I — Aerodrome Design and Operations",
        authority=ReferenceAuthority.ICAO,
        document_number="Annex 14 Vol I",
        document_type=ReferenceType.SARP,
        obligation=ReferenceObligation.MIXED,
        discipline="airfield-ground-lighting",
        jurisdiction="international",
    )


def _catalogue(
    library: ReferenceLibrary,
) -> tuple[ReferenceDocument, ReferenceEdition, ReferenceRevision]:
    """A document with one edition and one in-force revision."""
    document = _annex14()
    assert library.register_document(document).success
    edition = ReferenceEdition(
        reference_id=document.reference_id,
        edition="8th Edition",
        publication_date=date(2022, 7, 1),
    )
    assert library.register_edition(edition).success
    revision = ReferenceRevision(
        reference_id=document.reference_id,
        edition_id=edition.edition_id,
        revision="Amendment 17",
        effective_date=date(2023, 11, 30),
        source=ReferenceSource(
            source_type=ReferenceSourceType.USER_PROVIDED,
            licence_status=LicenceStatus.RESTRICTED,
            official_url="https://example.invalid/annex14",
            local_reference_path="/mnt/controlled/annex14-amd17.pdf",
            access_restriction=AccessRestriction.CONTROLLED,
        ),
    )
    assert library.register_revision(revision).success
    return document, edition, revision


# -- §10.1 registration refuses a conflicting duplicate ---------------------


def test_a_catalogued_reference_is_retrievable_by_identifier(library):
    document, edition, revision = _catalogue(library)
    assert library.document(document.reference_id) == document
    assert library.editions_of(document.reference_id) == [edition]
    assert library.revisions_of(document.reference_id) == [revision]
    assert library.revisions_of_edition(edition.edition_id) == [revision]
    assert library.revision(revision.revision_id) == revision


def test_registering_the_same_record_twice_changes_nothing(library):
    document = _annex14()
    assert library.register_document(document).success
    assert library.register_document(document).success
    assert len(library.documents()) == 1


def test_the_same_publication_cannot_be_catalogued_twice(library):
    library.register_document(_annex14())
    duplicate = _annex14()  # same authority and number, new identifier
    outcome = library.register_document(duplicate)
    assert not outcome.success
    assert outcome.error_code == WorkflowError.code
    assert "already catalogued" in outcome.message
    assert len(library.documents()) == 1


def test_a_reference_is_never_silently_overwritten(library):
    document = _annex14()
    library.register_document(document)
    amended = replace(document, title="A different publication entirely")
    outcome = library.register_document(amended)
    assert not outcome.success
    assert library.document(document.reference_id).title == document.title


def test_an_edition_needs_its_document_and_a_revision_needs_its_edition(library):
    orphan_edition = ReferenceEdition(reference_id="nope", edition="1st Edition")
    assert not library.register_edition(orphan_edition).success

    document, _, _ = _catalogue(library)
    orphan_revision = ReferenceRevision(
        reference_id=document.reference_id, edition_id="nope", revision="Amendment 1"
    )
    assert not library.register_revision(orphan_revision).success


def test_a_revision_cannot_name_a_document_its_edition_does_not_belong_to(library):
    _, edition, _ = _catalogue(library)
    other = ReferenceDocument(
        title="Civil Aviation Regulations Part IX",
        authority=ReferenceAuthority.UAE_GCAA,
        document_number="CAR Part IX",
        document_type=ReferenceType.REGULATION,
        obligation=ReferenceObligation.MANDATORY,
    )
    library.register_document(other)
    outcome = library.register_revision(
        ReferenceRevision(
            reference_id=other.reference_id,
            edition_id=edition.edition_id,
            revision="Amendment 1",
        )
    )
    assert not outcome.success
    assert "belongs to" in outcome.message


def test_a_second_edition_or_revision_of_the_same_name_is_refused(library):
    document, edition, _ = _catalogue(library)
    duplicate_edition = ReferenceEdition(
        reference_id=document.reference_id, edition="8TH edition"
    )
    assert not library.register_edition(duplicate_edition).success
    duplicate_revision = ReferenceRevision(
        reference_id=document.reference_id,
        edition_id=edition.edition_id,
        revision="amendment 17",
    )
    assert not library.register_revision(duplicate_revision).success
    assert len(library.revisions_of(document.reference_id)) == 1


# -- §10.2 supersession -----------------------------------------------------


def _amendment_18(
    library: ReferenceLibrary, document: ReferenceDocument, edition: ReferenceEdition
) -> ReferenceRevision:
    revision = ReferenceRevision(
        reference_id=document.reference_id,
        edition_id=edition.edition_id,
        revision="Amendment 18",
        effective_date=date(2024, 11, 28),
    )
    assert library.register_revision(revision).success
    return revision


def test_superseding_retires_the_old_revision_without_deleting_it(library):
    document, edition, amendment_17 = _catalogue(library)
    amendment_18 = _amendment_18(library, document, edition)

    outcome = library.supersede(amendment_17.revision_id, amendment_18.revision_id)
    assert outcome.success

    retired = library.revision(amendment_17.revision_id)
    assert retired is not None
    assert retired.status is ReferenceStatus.SUPERSEDED
    assert retired.superseded_by_revision_id == amendment_18.revision_id
    assert retired.superseded_date == date(2024, 11, 28)
    assert not retired.is_current
    # The record survives: history stays walkable in both directions.
    assert retired in library.revisions_of(document.reference_id)
    current = library.revision(amendment_18.revision_id)
    assert current is not None
    assert current.supersedes_revision_id == amendment_17.revision_id


def test_a_revision_already_superseded_is_not_quietly_retired_again(library):
    document, edition, amendment_17 = _catalogue(library)
    amendment_18 = _amendment_18(library, document, edition)
    other = ReferenceRevision(
        reference_id=document.reference_id,
        edition_id=edition.edition_id,
        revision="Amendment 18a",
        effective_date=date(2025, 1, 1),
    )
    library.register_revision(other)
    library.supersede(amendment_17.revision_id, amendment_18.revision_id)

    outcome = library.supersede(amendment_17.revision_id, other.revision_id)
    assert not outcome.success
    assert "already superseded" in outcome.message
    retired = library.revision(amendment_17.revision_id)
    assert retired is not None
    assert retired.superseded_by_revision_id == amendment_18.revision_id


def test_recording_the_same_supersession_twice_is_accepted(library):
    document, edition, amendment_17 = _catalogue(library)
    amendment_18 = _amendment_18(library, document, edition)
    assert library.supersede(amendment_17.revision_id, amendment_18.revision_id).success
    assert library.supersede(amendment_17.revision_id, amendment_18.revision_id).success


def test_supersession_across_documents_or_by_a_retired_revision_is_refused(library):
    document, edition, amendment_17 = _catalogue(library)
    amendment_18 = _amendment_18(library, document, edition)

    other_document = ReferenceDocument(
        title="Aerodrome Design Manual Part 4",
        authority=ReferenceAuthority.ICAO,
        document_number="Doc 9157-4",
        document_type=ReferenceType.MANUAL,
        obligation=ReferenceObligation.GUIDANCE,
    )
    library.register_document(other_document)
    other_edition = ReferenceEdition(
        reference_id=other_document.reference_id, edition="5th Edition"
    )
    library.register_edition(other_edition)
    unrelated = ReferenceRevision(
        reference_id=other_document.reference_id,
        edition_id=other_edition.edition_id,
        revision="base",
    )
    library.register_revision(unrelated)

    assert not library.supersede(
        amendment_17.revision_id, unrelated.revision_id
    ).success
    assert not library.supersede(
        amendment_17.revision_id, amendment_17.revision_id
    ).success

    withdrawn = ReferenceRevision(
        reference_id=document.reference_id,
        edition_id=edition.edition_id,
        revision="Amendment 19 (withdrawn)",
        status=ReferenceStatus.WITHDRAWN,
    )
    library.register_revision(withdrawn)
    outcome = library.supersede(amendment_18.revision_id, withdrawn.revision_id)
    assert not outcome.success
    assert "cannot supersede" in outcome.message


def test_superseding_an_unknown_revision_fails_with_remediation(library):
    _, _, amendment_17 = _catalogue(library)
    outcome = library.supersede("nope", amendment_17.revision_id)
    assert not outcome.success
    assert outcome.remediation


# -- §10.4 what was in force ------------------------------------------------


def test_the_current_revision_is_the_one_not_superseded(library):
    document, edition, amendment_17 = _catalogue(library)
    amendment_18 = _amendment_18(library, document, edition)
    library.supersede(amendment_17.revision_id, amendment_18.revision_id)

    outcome = library.revision_in_force(document.reference_id)
    assert outcome.success
    assert outcome.payload == library.revision(amendment_18.revision_id)


def test_an_historic_query_answers_with_the_revision_of_the_day(library):
    document, edition, amendment_17 = _catalogue(library)
    amendment_18 = _amendment_18(library, document, edition)
    library.supersede(amendment_17.revision_id, amendment_18.revision_id)

    earlier = library.revision_in_force(document.reference_id, on=date(2024, 6, 1))
    assert earlier.success
    assert earlier.payload is not None
    assert earlier.payload.revision == "Amendment 17"

    later = library.revision_in_force(document.reference_id, on=date(2025, 6, 1))
    assert later.success
    assert later.payload is not None
    assert later.payload.revision == "Amendment 18"


def test_a_date_before_anything_took_effect_has_no_answer(library):
    document, _, _ = _catalogue(library)
    outcome = library.revision_in_force(document.reference_id, on=date(2020, 1, 1))
    assert not outcome.success
    assert "in force" in outcome.message


def test_an_unrecorded_supersession_is_reported_rather_than_guessed(library):
    document, edition, _ = _catalogue(library)
    _amendment_18(library, document, edition)  # no supersession recorded
    outcome = library.revision_in_force(document.reference_id)
    assert not outcome.success
    assert "2 revisions" in outcome.message
    assert "Amendment 17" in outcome.message


def test_a_missing_effective_date_makes_an_historic_query_undeterminable(library):
    document, edition, _ = _catalogue(library)
    library.register_revision(
        ReferenceRevision(
            reference_id=document.reference_id,
            edition_id=edition.edition_id,
            revision="Amendment 18",
        )
    )
    outcome = library.revision_in_force(document.reference_id, on=date(2024, 6, 1))
    assert not outcome.success
    assert "no effective date" in outcome.message


def test_asking_about_an_uncatalogued_reference_fails(library):
    assert not library.revision_in_force("nope").success
    assert not library.cite("nope").success
    assert not library.evaluate_applicability("nope", {}).success


# -- §10.3 citation ---------------------------------------------------------


def test_a_citation_is_assembled_from_the_stored_records(library):
    document, _, revision = _catalogue(library)
    outcome = library.cite(
        revision.revision_id,
        section="5.3.17",
        clause="5.3.17.5",
        criterion_id="AGL-C-1",
    )
    assert outcome.success
    citation = outcome.payload
    assert citation is not None
    assert citation.reference_id == document.reference_id
    assert citation.document_number == "Annex 14 Vol I"
    assert citation.authority is ReferenceAuthority.ICAO
    assert citation.edition == "8th Edition"
    assert citation.revision == "Amendment 17"
    assert citation.revision_id == revision.revision_id
    assert citation.criterion_id == "AGL-C-1"
    assert str(citation).startswith("ICAO Annex 14 Vol I, 8th Edition")


def test_a_superseded_revision_can_still_be_cited(library):
    document, edition, amendment_17 = _catalogue(library)
    amendment_18 = _amendment_18(library, document, edition)
    library.supersede(amendment_17.revision_id, amendment_18.revision_id)
    # A historical run cited what was in force then; re-stating it must work.
    assert library.cite(amendment_17.revision_id).success


# -- §9 applicability through the library -----------------------------------


def test_applicability_is_evaluated_against_the_catalogued_conditions(library):
    document = ReferenceDocument(
        title="Zayed International Airport AGL Design Standard",
        authority=ReferenceAuthority.AIRPORT_AUTHORITY,
        document_number="ZIA-AGL-STD-001",
        document_type=ReferenceType.AIRPORT_STANDARD,
        obligation=ReferenceObligation.MANDATORY,
        applicability=ReferenceApplicability(
            criteria=(
                ApplicabilityCriterion(
                    dimension=ApplicabilityDimension.AIRPORT, values=("OMAA",)
                ),
            )
        ),
    )
    library.register_document(document)

    applies = library.evaluate_applicability(
        document.reference_id, {ApplicabilityDimension.AIRPORT: "OMAA"}
    )
    assert applies.payload is ApplicabilityVerdict.APPLICABLE

    elsewhere = library.evaluate_applicability(
        document.reference_id, {ApplicabilityDimension.AIRPORT: "OMDB"}
    )
    assert elsewhere.payload is ApplicabilityVerdict.NOT_APPLICABLE

    unstated = library.evaluate_applicability(document.reference_id, {})
    assert unstated.payload is ApplicabilityVerdict.UNDETERMINED


# -- §12.1 persistence reuses the existing store ----------------------------


def test_reference_records_round_trip_through_the_document_conversion():
    document = _annex14()
    edition = ReferenceEdition(
        reference_id=document.reference_id,
        edition="8th Edition",
        publication_date=date(2022, 7, 1),
    )
    revision = ReferenceRevision(
        reference_id=document.reference_id,
        edition_id=edition.edition_id,
        revision="Amendment 17",
        effective_date=date(2023, 11, 30),
        source=ReferenceSource(
            source_type=ReferenceSourceType.LICENSED_COPY,
            licence_status=LicenceStatus.LICENSED,
            local_reference_path="/mnt/controlled/annex14.pdf",
        ),
    )
    for instance in (document, edition, revision):
        assert from_document(type(instance), to_document(instance)) == instance


def test_dates_survive_the_round_trip_as_dates_not_strings():
    edition = ReferenceEdition(
        reference_id="ref-1", edition="8th Edition", publication_date=date(2022, 7, 1)
    )
    restored = from_document(ReferenceEdition, to_document(edition))
    assert restored.publication_date == date(2022, 7, 1)
    assert isinstance(restored.publication_date, date)


def test_applicability_and_source_survive_as_value_objects():
    document = _annex14()
    document.applicability = ReferenceApplicability(
        criteria=(
            ApplicabilityCriterion(
                dimension=ApplicabilityDimension.COUNTRY, values=("AE", "SA")
            ),
        )
    )
    restored = from_document(ReferenceDocument, to_document(document))
    assert isinstance(restored.applicability, ReferenceApplicability)
    assert restored.applicability.criteria[0].dimension is (
        ApplicabilityDimension.COUNTRY
    )
    assert restored.applicability.criteria[0].values == ("AE", "SA")


def test_the_catalogue_survives_process_exit(tmp_path):
    database = tmp_path / "aet.db"
    written = ReferenceLibrary(sqlite_repositories(connect(database)))
    document, edition, revision = _catalogue(written)

    read = ReferenceLibrary(sqlite_repositories(connect(database)))
    assert read.document(document.reference_id) == document
    assert read.editions_of(document.reference_id) == [edition]
    stored = read.revision(revision.revision_id)
    assert stored is not None
    assert stored.source.local_reference_path == "/mnt/controlled/annex14-amd17.pdf"
    assert stored.effective_date == date(2023, 11, 30)


def test_the_reference_tables_join_the_existing_schema(tmp_path):
    connection = connect(tmp_path / "aet.db")
    sqlite_repositories(connection)
    tables = set(all_tables(connection))
    assert {
        "reference_documents",
        "reference_editions",
        "reference_revisions",
    } <= tables
    # No second store: the reference tables sit beside the project ones.
    assert {"projects", "assets", "validation_results"} <= tables


def test_references_belong_to_no_project(tmp_path):
    """A project-scoped read never returns a library entity (§12.1)."""
    for repositories in (
        in_memory_repositories(),
        sqlite_repositories(connect(tmp_path / "aet.db")),
    ):
        library = ReferenceLibrary(repositories)
        document, _, _ = _catalogue(library)
        assert repositories.reference_documents.list_for_project("p1") == []
        assert repositories.reference_documents.get(document.reference_id) is not None


# -- §10.3 historical findings keep the reference they were judged against --


def test_an_amended_reference_does_not_rewrite_an_existing_validation_run():
    """The auditability requirement, end to end.

    A run cites Amendment 17. The catalogue later moves to Amendment 18. The
    finding must still say Amendment 17, because that is what the engineer
    checked against.
    """
    repositories = in_memory_repositories()
    library = ReferenceLibrary(repositories)
    document, edition, amendment_17 = _catalogue(library)

    cited = library.cite(amendment_17.revision_id, clause="5.3.17.5")
    run = ValidationRun(project_id="p1", rule_ids=["agl.spacing"])
    run.status = RunStatus.COMPLETED
    finding = ValidationResult(
        rule_id="agl.spacing",
        severity=Severity.WARNING,
        passed=False,
        message="Taxiway edge-light spacing exceeds the configured criterion",
        evidence={"samples": "TEC102-01/067"},
        citation=cited.payload,
        run_id=run.run_id,
    )
    repositories.validation_runs.add(run)
    repositories.validation_results.add(finding)

    # The reference library moves on.
    amendment_18 = _amendment_18(library, document, edition)
    library.supersede(amendment_17.revision_id, amendment_18.revision_id)

    stored = repositories.validation_results.get(finding.result_id)
    assert stored is not None
    assert stored.citation is not None
    assert stored.citation.revision == "Amendment 17"
    assert stored.citation.revision_id == amendment_17.revision_id
    assert stored.citation.clause == "5.3.17.5"
    # And the revision it points at is still resolvable, marked superseded.
    historic = library.revision(stored.citation.revision_id)
    assert historic is not None
    assert historic.status is ReferenceStatus.SUPERSEDED
    assert library.revision_in_force(document.reference_id).payload == (
        library.revision(amendment_18.revision_id)
    )


def test_a_persisted_finding_keeps_its_citation(tmp_path):
    repositories = sqlite_repositories(connect(tmp_path / "aet.db"))
    library = ReferenceLibrary(repositories)
    _, _, revision = _catalogue(library)
    citation = library.cite(revision.revision_id, section="5.3.17").payload

    finding = ValidationResult(
        rule_id="agl.spacing",
        severity=Severity.ERROR,
        passed=False,
        message="m",
        citation=citation,
    )
    repositories.validation_results.add(finding)

    reread = sqlite_repositories(connect(tmp_path / "aet.db"))
    stored = reread.validation_results.get(finding.result_id)
    assert stored is not None
    assert stored.citation == citation
    assert stored.citation is not None
    assert stored.citation.authority is ReferenceAuthority.ICAO


def test_a_finding_without_a_citation_claims_none():
    finding = ValidationResult(
        rule_id="agl.asset.location",
        severity=Severity.WARNING,
        passed=True,
        message="All assets have UTM coordinates",
    )
    assert finding.citation is None
    assert from_document(ValidationResult, to_document(finding)) == finding
