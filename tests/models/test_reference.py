"""Tests for SDS-016: reference library domain models."""

from datetime import UTC, date

import pytest

from aet.core.errors import InputError
from aet.models.reference import (
    AccessRestriction,
    ApplicabilityCriterion,
    ApplicabilityDimension,
    ApplicabilityVerdict,
    LicenceStatus,
    ReferenceApplicability,
    ReferenceAuthority,
    ReferenceCitation,
    ReferenceDocument,
    ReferenceEdition,
    ReferenceObligation,
    ReferenceRevision,
    ReferenceSource,
    ReferenceSourceType,
    ReferenceStatus,
    ReferenceType,
)


def _document(
    *,
    title: str = "Aerodrome Design Manual Part 4 — Visual Aids",
    authority: ReferenceAuthority = ReferenceAuthority.ICAO,
    document_number: str = "Doc 9157-4",
    document_type: ReferenceType = ReferenceType.MANUAL,
    obligation: ReferenceObligation = ReferenceObligation.GUIDANCE,
) -> ReferenceDocument:
    return ReferenceDocument(
        title=title,
        authority=authority,
        document_number=document_number,
        document_type=document_type,
        obligation=obligation,
    )


# -- §8.1 creation and identity --------------------------------------------


def test_a_reference_gets_a_stable_unique_identifier():
    first, second = _document(), _document(document_number="Doc 9157-5")
    assert first.reference_id
    assert first.reference_id != second.reference_id
    assert first.created_at.tzinfo is UTC


def test_authority_and_document_type_are_explicit_on_every_reference():
    document = _document(
        authority=ReferenceAuthority.UAE_GCAA,
        document_type=ReferenceType.REGULATION,
    )
    assert document.authority is ReferenceAuthority.UAE_GCAA
    assert document.document_type is ReferenceType.REGULATION


def test_authorities_render_with_a_readable_label():
    assert ReferenceAuthority.UAE_GCAA.label == "UAE GCAA"
    assert ReferenceAuthority.ICAO.label == "ICAO"


def test_a_reference_without_a_title_or_number_is_refused():
    with pytest.raises(InputError):
        _document(title="   ")
    with pytest.raises(InputError):
        _document(document_number="")


def test_the_catalogue_key_ignores_case_and_surrounding_space():
    assert _document(document_number=" doc 9157-4 ").catalogue_key == (
        _document(document_number="Doc 9157-4").catalogue_key
    )


# -- §7.1 mandatory material is distinguishable from guidance ---------------


@pytest.mark.parametrize(
    ("obligation", "mandatory"),
    [
        (ReferenceObligation.MANDATORY, True),
        (ReferenceObligation.MIXED, True),
        (ReferenceObligation.RECOMMENDED, False),
        (ReferenceObligation.GUIDANCE, False),
    ],
)
def test_only_mandatory_and_mixed_documents_can_impose_requirements(
    obligation, mandatory
):
    assert _document(obligation=obligation).carries_mandatory_material is mandatory
    assert obligation.carries_mandatory_material is mandatory


def test_a_document_type_does_not_decide_its_obligation():
    """An Annex mixes Standards with Recommended Practices; a manual guides."""
    sarp = _document(
        document_type=ReferenceType.SARP, obligation=ReferenceObligation.MIXED
    )
    manual = _document(
        document_type=ReferenceType.MANUAL, obligation=ReferenceObligation.GUIDANCE
    )
    assert sarp.carries_mandatory_material
    assert not manual.carries_mandatory_material


# -- §8.2, §8.3 editions and revisions --------------------------------------


def test_an_edition_and_revision_carry_their_own_identity_and_dates():
    edition = ReferenceEdition(
        reference_id="ref-1",
        edition="8th Edition",
        publication_date=date(2022, 7, 1),
    )
    revision = ReferenceRevision(
        reference_id="ref-1",
        edition_id=edition.edition_id,
        revision="Amendment 17",
        effective_date=date(2023, 11, 30),
    )
    assert edition.edition_id
    assert revision.revision_id
    assert edition.publication_date == date(2022, 7, 1)
    assert revision.effective_date == date(2023, 11, 30)
    assert revision.status is ReferenceStatus.IN_FORCE
    assert revision.is_current


def test_an_unnamed_edition_or_revision_is_refused():
    with pytest.raises(InputError):
        ReferenceEdition(reference_id="ref-1", edition=" ")
    with pytest.raises(InputError):
        ReferenceRevision(reference_id="ref-1", edition_id="ed-1", revision="")


def test_a_superseded_revision_is_not_current():
    revision = ReferenceRevision(
        reference_id="ref-1",
        edition_id="ed-1",
        revision="Amendment 16",
        status=ReferenceStatus.SUPERSEDED,
        superseded_by_revision_id="rev-17",
    )
    assert not revision.is_current


# -- §11 source and licensing metadata --------------------------------------


def test_an_uncharacterised_source_defaults_to_the_safe_position():
    source = ReferenceSource()
    assert source.source_type is ReferenceSourceType.METADATA_ONLY
    assert source.licence_status is LicenceStatus.UNKNOWN
    assert source.access_restriction is AccessRestriction.CONTROLLED
    assert not source.redistributable


def test_only_an_open_public_official_source_is_redistributable():
    assert ReferenceSource(
        source_type=ReferenceSourceType.PUBLIC_OFFICIAL,
        licence_status=LicenceStatus.PUBLIC,
        access_restriction=AccessRestriction.OPEN,
        official_url="https://example.invalid/doc.pdf",
    ).redistributable


@pytest.mark.parametrize(
    "source",
    [
        ReferenceSource(
            source_type=ReferenceSourceType.LICENSED_COPY,
            licence_status=LicenceStatus.LICENSED,
            access_restriction=AccessRestriction.OPEN,
            local_reference_path="/controlled/annex14.pdf",
        ),
        ReferenceSource(
            source_type=ReferenceSourceType.PUBLIC_OFFICIAL,
            licence_status=LicenceStatus.UNKNOWN,
            access_restriction=AccessRestriction.OPEN,
        ),
        ReferenceSource(
            source_type=ReferenceSourceType.PUBLIC_OFFICIAL,
            licence_status=LicenceStatus.PUBLIC,
            access_restriction=AccessRestriction.CONTROLLED,
        ),
        ReferenceSource(
            source_type=ReferenceSourceType.RESTRICTED,
            licence_status=LicenceStatus.RESTRICTED,
            local_reference_path="/controlled/gcaa-car.pdf",
        ),
    ],
)
def test_anything_short_of_open_public_and_licensed_is_not_redistributable(source):
    assert not source.redistributable


def test_a_metadata_only_source_cannot_claim_to_hold_a_copy():
    with pytest.raises(InputError):
        ReferenceSource(
            source_type=ReferenceSourceType.METADATA_ONLY,
            local_reference_path="/controlled/annex14.pdf",
        )


def test_a_controlled_copy_records_where_it_is_without_the_toolkit_reading_it():
    source = ReferenceSource(
        source_type=ReferenceSourceType.USER_PROVIDED,
        licence_status=LicenceStatus.RESTRICTED,
        official_url="https://example.invalid/catalogue",
        local_reference_path="/mnt/controlled/annex14-amd17.pdf",
    )
    # The path is metadata. Nothing in the model opens it, and it need not
    # exist on this machine for the reference to be citable.
    assert source.local_reference_path == "/mnt/controlled/annex14-amd17.pdf"
    assert not source.redistributable


# -- §9 applicability -------------------------------------------------------


def test_a_reference_with_no_stated_conditions_applies_everywhere():
    assert ReferenceApplicability().evaluate({}) is ApplicabilityVerdict.APPLICABLE


def test_a_context_matching_every_restriction_is_applicable():
    applicability = ReferenceApplicability(
        criteria=(
            ApplicabilityCriterion(
                dimension=ApplicabilityDimension.COUNTRY, values=("AE",)
            ),
            ApplicabilityCriterion(
                dimension=ApplicabilityDimension.LIGHTING_SYSTEM,
                values=("taxiway-centreline", "stop-bar"),
            ),
        )
    )
    verdict = applicability.evaluate(
        {
            ApplicabilityDimension.COUNTRY: "ae",
            ApplicabilityDimension.LIGHTING_SYSTEM: " Stop-Bar ",
        }
    )
    assert verdict is ApplicabilityVerdict.APPLICABLE


def test_a_contradicted_restriction_is_not_applicable():
    applicability = ReferenceApplicability(
        criteria=(
            ApplicabilityCriterion(
                dimension=ApplicabilityDimension.AIRPORT, values=("OMAA",)
            ),
        )
    )
    verdict = applicability.evaluate({ApplicabilityDimension.AIRPORT: "OMDB"})
    assert verdict is ApplicabilityVerdict.NOT_APPLICABLE


def test_an_unstated_restriction_is_undetermined_rather_than_applicable():
    applicability = ReferenceApplicability(
        criteria=(
            ApplicabilityCriterion(
                dimension=ApplicabilityDimension.APPROACH_CATEGORY, values=("CAT-III",)
            ),
        )
    )
    assert applicability.evaluate({}) is ApplicabilityVerdict.UNDETERMINED
    assert (
        applicability.evaluate({ApplicabilityDimension.APPROACH_CATEGORY: "  "})
        is ApplicabilityVerdict.UNDETERMINED
    )


def test_a_definite_exclusion_wins_over_an_unstated_dimension():
    applicability = ReferenceApplicability(
        criteria=(
            ApplicabilityCriterion(
                dimension=ApplicabilityDimension.AIRPORT, values=("OMAA",)
            ),
            ApplicabilityCriterion(
                dimension=ApplicabilityDimension.DESIGN_STAGE, values=("detailed",)
            ),
        )
    )
    verdict = applicability.evaluate({ApplicabilityDimension.AIRPORT: "OMDB"})
    assert verdict is ApplicabilityVerdict.NOT_APPLICABLE


def test_a_criterion_restricting_nothing_is_refused():
    with pytest.raises(InputError):
        ApplicabilityCriterion(dimension=ApplicabilityDimension.COUNTRY, values=())


# -- §10.3 citations --------------------------------------------------------


def test_a_citation_renders_the_clause_it_points_at():
    citation = ReferenceCitation(
        reference_id="ref-1",
        document_number="Annex 14 Vol I",
        authority=ReferenceAuthority.ICAO,
        edition="8th Edition",
        revision="Amendment 17",
        section="5.3.17",
        clause="5.3.17.5",
    )
    rendered = str(citation)
    assert rendered == (
        "ICAO Annex 14 Vol I, 8th Edition, Rev Amendment 17, §5.3.17, clause 5.3.17.5"
    )


def test_a_citation_omits_the_parts_it_does_not_have():
    citation = ReferenceCitation(
        reference_id="ref-1",
        document_number="CAR Part IX",
        authority=ReferenceAuthority.UAE_GCAA,
        edition="Issue 5",
        revision="",
    )
    assert str(citation) == "UAE GCAA CAR Part IX, Issue 5"


def test_a_citation_is_immutable():
    citation = ReferenceCitation(
        reference_id="ref-1",
        document_number="Doc 9157-4",
        authority=ReferenceAuthority.ICAO,
        edition="2nd Edition",
        revision="base",
    )
    with pytest.raises(AttributeError):
        citation.revision = "Amendment 1"  # type: ignore[misc]
