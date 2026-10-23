"""discord_message: rendering, escaping, link formatting and splitting."""

import re

import pytest

from src.services.discord_message import (
    DEFAULT_MESSAGES, EVENT_PLACEHOLDERS, LINK_PRESETS, PLACEHOLDER_NAMES,
    escape_markdown, format_host_links, preview_fields, render, split_message,
)
from src.services.notification_manager import NOTIFICATION_EVENTS
from src.utils.template_utils import HostLinkPart, HostLinks


def _host(host_id, name, *urls):
    return HostLinks(host_id=host_id, host_name=name, parts=[
        HostLinkPart(url=u, part_number=i, file_name='', file_size=None)
        for i, u in enumerate(urls)
    ])


class TestDefaults:
    def test_defaults_cover_every_event(self):
        assert set(DEFAULT_MESSAGES) == set(NOTIFICATION_EVENTS)

    def test_placeholders_cover_every_event(self):
        assert set(EVENT_PLACEHOLDERS) == set(NOTIFICATION_EVENTS)

    def test_defaults_contain_no_link_placeholders(self):
        for text in DEFAULT_MESSAGES.values():
            for link in ('#hostLinks#', '#hostLink#', '#galleryLink#'):
                assert link not in text

    def test_default_renders_without_fields(self):
        assert render(DEFAULT_MESSAGES['filehost_upload_completed'], {}) == \
            '✅ File host upload complete'
        assert render(DEFAULT_MESSAGES['gallery_failed'], {}) == '❌ Gallery failed'
        assert render(DEFAULT_MESSAGES['gallery_completed'], {}) == '✅ Gallery uploaded'
        assert render(DEFAULT_MESSAGES['disk_space_warning'], {}) == \
            '⚠️ Disk space is running low'

    def test_gallery_default_with_failures(self):
        fields = {'gallery_name': 'My Set', 'failed_hosts': 'Keep2Share'}
        assert render(DEFAULT_MESSAGES['gallery_completed'], fields) == \
            '✅ Gallery uploaded: My Set\n⚠️ Failed on: Keep2Share'

    def test_filehost_default_with_fields(self):
        fields = {'gallery_name': 'My Set', 'host_name': 'Rapidgator'}
        assert render(DEFAULT_MESSAGES['filehost_upload_completed'], fields) == \
            '✅ Rapidgator upload complete: My Set'

    def test_presets_only_for_link_events(self):
        assert set(LINK_PRESETS) == {'gallery_completed', 'filehost_upload_completed'}
        assert '#hostLinks#' in LINK_PRESETS['gallery_completed']
        assert '#hostLink#' in LINK_PRESETS['filehost_upload_completed']

    def test_gallery_preset_renders_everything(self):
        fields = {
            'gallery_name': 'My Set', 'picture_count': '12', 'folder_size': '3.0 MiB',
            'gallery_link': 'https://imx.to/g/abc',
            'host_links': '[Rapidgator](https://rg.to/file/x)', 'failed_hosts': '',
        }
        out = render(LINK_PRESETS['gallery_completed'], fields)
        assert out == (
            '✅ **My Set** — 12 images, 3.0 MiB\n'
            '🖼️ [Gallery](https://imx.to/g/abc)\n'
            '📦 Downloads:\n'
            '[Rapidgator](https://rg.to/file/x)'
        )


class TestEscaping:
    @pytest.mark.parametrize("name,expected", [
        ('#hostLinks#', r'\#hostLinks\#'),
        ('[x](https://evil)', r'\[x\]\(https\://evil\)'),
        ('**b**', r'\*\*b\*\*'),
        ('a_b|c~d', r'a\_b\|c\~d'),
        ('`code`', r'\`code\`'),
        ('> quote <@1>', r'\> quote \<@1\>'),
        ('back\\slash', 'back\\\\slash'),
    ])
    def test_escape_markdown(self, name, expected):
        assert escape_markdown(name) == expected

    def test_name_is_never_expanded(self):
        out = render('#galleryName#', {'gallery_name': '#hostLinks#', 'host_links': 'LEAK'})
        assert 'LEAK' not in out
        assert out == r'\#hostLinks\#'

    def test_name_cannot_forge_a_link(self):
        out = render('#galleryName#', {'gallery_name': '[x](https://evil)'})
        assert '](' not in out

    def test_link_fields_are_not_escaped(self):
        assert render('[G](#galleryLink#)', {'gallery_link': 'https://imx.to/g/a_b'}) == \
            '[G](https://imx.to/g/a_b)'

    def test_unknown_hash_words_kept(self):
        assert render('Set #5# and #nope#', {}) == 'Set #5# and #nope#'

    def test_placeholder_next_to_unknown_hash_word(self):
        assert render('#5#galleryName#', {'gallery_name': 'A'}) == '#5A'


class TestFormatHostLinks:
    def test_single_and_multi_part(self):
        out = format_host_links([
            _host('tezfiles', 'TezFiles', 'https://tezfiles.com/file/z'),
            _host('rapidgator', 'Rapidgator', 'https://rg.to/a', 'https://rg.to/b', 'https://rg.to/c'),
        ])
        assert out == (
            '[TezFiles](https://tezfiles.com/file/z)\n'
            '**Rapidgator**: [Part 1](https://rg.to/a) · [Part 2](https://rg.to/b)'
            ' · [Part 3](https://rg.to/c)'
        )

    def test_encodes_parens_and_spaces_in_url(self):
        out = format_host_links([_host('x', 'X', 'https://x.com/a (1).zip')])
        assert out == '[X](https://x.com/a%20%281%29.zip)'

    def test_host_name_escaped(self):
        assert format_host_links([_host('x', 'A_B', 'u')]) == r'[A\_B](u)'

    def test_empty(self):
        assert format_host_links([]) == ''


class TestSplit:
    def test_empty(self):
        assert split_message('') == []

    def test_exact_limit_is_one_chunk(self):
        text = 'a' * 2000
        assert split_message(text) == [text]

    def test_one_over_splits_on_line(self):
        text = 'a' * 1000 + '\n' + 'b' * 1000
        assert split_message(text) == ['a' * 1000, 'b' * 1000]

    def test_long_link_line_breaks_between_links(self):
        urls = [f'https://rapidgator.net/file/{i:032d}' for i in range(60)]
        line = format_host_links([_host('rg', 'Rapidgator', *urls)])
        assert len(line) > 2000
        chunks = split_message('header\n' + line)
        assert len(chunks) > 1
        assert all(len(c) <= 2000 for c in chunks)
        joined = '\n'.join(chunks)
        for i, url in enumerate(urls):
            link = f'[Part {i + 1}]({url})'
            assert sum(c.count(link) for c in chunks) == 1
            assert link in joined

    def test_unbreakable_run_is_hard_cut(self):
        chunks = split_message('x' * 4500)
        assert [len(c) for c in chunks] == [2000, 2000, 500]


class TestPreview:
    @pytest.mark.parametrize("event_id", sorted(NOTIFICATION_EVENTS))
    def test_preview_fields_render_every_event(self, event_id):
        fields = preview_fields(event_id)
        templates = [DEFAULT_MESSAGES[event_id]]
        if event_id in LINK_PRESETS:
            templates.append(LINK_PRESETS[event_id])
        for template in templates:
            out = render(template, fields)
            assert out
            for name in PLACEHOLDER_NAMES:
                assert f'#{name}#' not in out

    def test_event_placeholders_are_known_names(self):
        for entries in EVENT_PLACEHOLDERS.values():
            for placeholder, label, tooltip, preview in entries:
                assert re.fullmatch(r'#(\w+)#', placeholder)
                assert placeholder.strip('#') in PLACEHOLDER_NAMES


class TestBlankLines:
    def test_lines_emptied_by_conditionals_are_dropped(self):
        template = 'A\n[if galleryLink]#galleryLink#[/if]\nB'
        assert render(template, {}) == 'A\nB'

    def test_blank_lines_the_user_wrote_are_kept(self):
        assert render('A\n\nB', {}) == 'A\n\nB'
