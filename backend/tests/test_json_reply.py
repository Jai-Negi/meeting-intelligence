import pytest

from app.tools.json_reply import JSONReplyError, parse_json_reply


@pytest.mark.parametrize(
    "raw",
    [
        '[{"a": 1}]',
        '  [{"a": 1}]  \n',
        '```json\n[{"a": 1}]\n```',
        '```JSON\n[{"a": 1}]\n```',
        '```\n[{"a": 1}]\n```',
        'Here are the action items:\n[{"a": 1}]',
        '[{"a": 1}]\n\nLet me know if you need anything else.',
        'Sure, here you go:\n```json\n[{"a": 1}]\n```\nHope that helps.',
        'The list [as requested] is: [{"a": 1}]',
    ],
)
def test_json_is_found_however_the_model_wraps_it(raw):
    assert parse_json_reply(raw) == [{"a": 1}]


def test_objects_are_found_as_well_as_arrays():
    assert parse_json_reply('Draft below.\n{"subject": "Hi", "body": "Text"}') == {
        "subject": "Hi",
        "body": "Text",
    }


def test_an_empty_array_is_a_valid_reply():
    assert parse_json_reply("[]") == []


@pytest.mark.parametrize("raw", ["", "   ", "no json here at all", "[not, valid", "```json\n```", None])
def test_replies_without_json_raise(raw):
    with pytest.raises(JSONReplyError):
        parse_json_reply(raw)


def test_a_reply_full_of_stray_brackets_gives_up_quickly():
    with pytest.raises(JSONReplyError):
        parse_json_reply("[" * 10_000)
