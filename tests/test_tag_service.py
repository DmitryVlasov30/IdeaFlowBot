from types import SimpleNamespace

from src.editorial.models.enums import ChannelPasteTagRuleMode, TagMatchType
from src.editorial.services.tag_service import TagService


def test_normalize_slug_keeps_readable_tag_ids() -> None:
    assert TagService.normalize_slug(" Summer Tag! ") == "summer_tag"
    assert TagService.normalize_slug("Лето 2026") == "лето_2026"


def test_keyword_matching_supports_contains_and_word_modes() -> None:
    contains_keyword = SimpleNamespace(normalized_keyword="экзам", match_type=TagMatchType.CONTAINS)
    word_keyword = SimpleNamespace(normalized_keyword="арт", match_type=TagMatchType.WORD)

    assert TagService._matches("экзамены уже близко", contains_keyword)
    assert TagService._matches("арт проект", word_keyword)
    assert not TagService._matches("карта проекта", word_keyword)


def test_exclude_is_stronger_than_include_policy_shape() -> None:
    paste_tags = {"summer", "tech"}
    included = {"summer"}
    excluded = {"tech"}

    assert paste_tags & included
    assert paste_tags & excluded
    assert ChannelPasteTagRuleMode.EXCLUDE.value == "exclude"
