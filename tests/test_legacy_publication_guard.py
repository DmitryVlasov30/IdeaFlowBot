from src.editorial.services.legacy_publication_guard import LegacyPublicationGuard


def test_timestamp_in_legacy_ad_window() -> None:
    advertising_data = {(10, 1_000.0)}

    assert LegacyPublicationGuard.timestamp_in_legacy_ad_window(
        1_100.0,
        advertising_data,
        shift_seconds=3_600,
    )
    assert not LegacyPublicationGuard.timestamp_in_legacy_ad_window(
        4_600.0,
        advertising_data,
        shift_seconds=3_600,
    )


def test_next_timestamp_after_legacy_ad_window_handles_overlap() -> None:
    advertising_data = {
        (10, 1_000.0),
        (11, 4_000.0),
    }

    assert LegacyPublicationGuard.next_timestamp_after_legacy_ad_window(
        1_100.0,
        advertising_data,
        shift_seconds=3_600,
    ) == 7_600.0


def test_next_timestamp_after_legacy_ad_window_returns_none_when_clear() -> None:
    advertising_data = {(10, 1_000.0)}

    assert LegacyPublicationGuard.next_timestamp_after_legacy_ad_window(
        4_600.0,
        advertising_data,
        shift_seconds=3_600,
    ) is None
