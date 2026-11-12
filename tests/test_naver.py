"""변환·설정·CLI를 브라우저 없이 검증합니다."""
from pathlib import Path
from html.parser import HTMLParser
import re
import pytest
from frame.cli import main
from frame.config_loader import load_experience_label
from frame.core.naver import NaverCounts, count_naver_body, markdown_to_naver, render_agent_instructions
from frame.adapters.naver_html import save_agent_instructions, save_naver_html
from frame.adapters.new_workspace import create_workspace


def test_conversion():
    result = markdown_to_naver('# 제목\n\n## 소제목\n문단 **굵게**\n이어짐\n\n- 하나\n- [문서](https://example.org/a)\n\n[내 경험 입력]\n\n## 출처\nhttps://example.org/?a=1&b=2\n### 점검표\n삭제')
    assert result.title == '제목'
    assert '# 제목' not in result.html
    for text in ['<h2>소제목</h2>', '<p>문단 <strong>굵게</strong> 이어짐</p>', '<ul>\n<li>하나</li>', '<a href="https://example.org/a">문서</a>', '<h2>출처</h2>', '?a=1&amp;b=2', '<strong>[내 경험 — 발행 전에 직접 채우세요]</strong>']:
        assert text in result.html
    assert result.has_experience_slots
    assert '삭제' not in result.plain
    assert '문서 (https://example.org/a)' in result.plain


@pytest.mark.parametrize('marker', ['### 점검표 확인', '## 점검표', '**점검표 대조 결과**', '---'])
def test_self_check_cutoff(marker):
    result = markdown_to_naver(f'# 제목\n본문\n## 출처\nhttps://example.org\n{marker}\n비공개 점검')
    assert '출처' in result.html
    assert '비공개' not in result.html
    assert marker not in result.plain


def test_custom_experience_and_html_safety():
    result = markdown_to_naver('# 제목\n**[직접 체험 메모]**\n<script>위험</script>\n[안전](javascript:alert)', '직접 체험')
    assert result.has_experience_slots
    assert '[내 경험 — 발행 전에 직접 채우세요]' in result.html
    assert '<script>' not in result.html
    assert 'javascript:' not in result.html
    assert not markdown_to_naver('# 제목\n본문').has_experience_slots


def test_html_file(tmp_path):
    source = tmp_path / '초안.md'
    source.write_text('원본', encoding='utf-8')
    path = save_naver_html(source, markdown_to_naver('# 제목 <안전>\n본문'))
    assert path == tmp_path / '초안.naver.html'
    text = path.read_text(encoding='utf-8')
    assert '<meta charset="utf-8">' in text
    assert '<title>제목 &lt;안전&gt;</title>' in text
    assert '<h1' not in text
    assert '<p>본문</p>' in text
    assert source.read_text(encoding='utf-8') == '원본'



@pytest.fixture
def workspace(tmp_path):
    (tmp_path / 'profile.toml').write_text('[writing]\nexperience_label="체험"', encoding='utf-8')
    folder = tmp_path / '초안'
    folder.mkdir()
    path = folder / '글.md'
    path.write_text('# 제목\n본문 [체험]', encoding='utf-8')
    return path


def test_label(workspace, tmp_path):
    assert load_experience_label(workspace) == '체험'
    assert load_experience_label(tmp_path.parent / 'draft.md') == '내 경험'


def test_invalid_label(workspace):
    (workspace.parent.parent / 'profile.toml').write_text('[writing]\nexperience_label=1', encoding='utf-8')
    assert main(['naver', 'draft', str(workspace)]) == 1


@pytest.mark.parametrize('text', ['# 제목\n---\n점검표', '본문만', ''])
def test_empty_draft_keeps_html(workspace, text):
    workspace.write_text(text, encoding='utf-8')
    assert main(['naver', 'draft', str(workspace)]) == 1
    assert workspace.with_suffix('.naver.html').is_file()


def test_cli_draft(workspace, capsys, monkeypatch):
    import socket
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('네트워크 호출 금지'))
    assert main(['naver', 'draft', str(workspace)]) == 0
    output = capsys.readouterr().out
    assert '경고: 경험 슬롯' in output
    assert '[본문 복사] → 편집기 본문 클릭 → Ctrl+V' in output
    assert '확인: 제목 1 · 소제목 0 · 목록 0 · 굵게 1 · 링크 0' in output
    assert str(workspace.with_suffix('.naver.html')) in output
    assert '[내 경험 — 발행 전에 직접 채우세요]' in workspace.with_suffix('.naver.html').read_text(encoding='utf-8')
    agent_path = workspace.with_suffix('.agent.txt')
    assert f'[실행 지시서] 저장: {agent_path}' in output
    instructions = agent_path.read_text(encoding='utf-8')
    assert workspace.with_suffix('.naver.html').resolve().as_uri() in instructions
    assert '경험 칸 1개는 비워 둔 채 저장한다 — 사람이 채운다' in instructions
    for path in (agent_path, workspace.with_suffix('.naver.html')):
        assert b'\r' not in path.read_bytes()


@pytest.mark.parametrize('slots', [0, 1, 2])
def test_agent_instructions(slots):
    draft = markdown_to_naver(
        '# 제목\n## 소제목\n**강조**\n- [링크](https://example.org)\n'
        + '\n'.join('[체험 메모]' for _ in range(slots)), '체험',
    )
    uri = 'file:///C:/draft%20folder/%EC%B4%88%EC%95%88.naver.html'
    text = render_agent_instructions(draft, uri)
    assert text.splitlines()[0] == '아래 순서만 따라 네이버 블로그 임시저장까지 진행해 줘. 발행은 절대 누르지 마.'
    assert uri in text
    assert count_naver_body(draft.html).confirmation() in text
    for phrase in (
        '굵게가 문단 전체로 번지면 실패', '로그인하지 말 것', '이미 로그인된 세션만',
        '로그인 화면', '캡차', '보호조치', "'과도한 접근'", '즉시 중단하고 화면 문구를 보고',
        '본문 타이핑 금지', '복사 버튼+Ctrl+V만', '다른 작업과 동시에 돌리지 말 것', '한 번에 한 편',
        '[본문 복사]', '[제목 복사]', '저장하지 말고 중단', '임시저장함에 제목이 보이는지',
    ):
        assert phrase in text
    assert [line[:2] for line in text.splitlines() if re.match(r'\d\)', line)] == [f'{n})' for n in range(1, 8)]
    if slots:
        assert f'경험 칸 {slots}개는 비워 둔 채 저장한다 — 사람이 채운다' in text
    else:
        assert '경험 칸' not in text
    assert '`frame naver capture-script` 출력(사람이 붙여 줌)' in text.splitlines()[-1]
    assert '에이전트가 아니라 사람이 수행한다' in text.splitlines()[-1]


def test_agent_file_uri_and_encoding(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = Path('한글 공백')
    folder.mkdir()
    source = folder / '초안.md'
    draft = markdown_to_naver('# 제목\n본문')
    html_path = save_naver_html(source, draft)
    path = save_agent_instructions(source, draft, html_path)
    assert path == source.with_suffix('.agent.txt')
    data = path.read_bytes()
    text = data.decode('utf-8')
    assert not data.startswith(b'\xef\xbb\xbf')
    assert b'\r' not in data
    uri = html_path.resolve().as_uri()
    assert uri.startswith('file:///') and '%20' in uri and '%EC%B4%88' in uri
    assert '\\' not in uri and '한글' not in uri
    assert f'초안 위치: {uri}' in text


@pytest.mark.parametrize('args', [['login'], ['draft', 'x.md', '--browser'], ['draft', 'x.md', '--blog-id', 'id'], ['draft', 'x.md', '--close']])
def test_removed_commands_rejected(args):
    with pytest.raises(SystemExit) as exc:
        main(['naver', *args])
    assert exc.value.code == 2


def test_missing_draft(tmp_path):
    assert main(['naver', 'draft', str(tmp_path / 'missing.md')]) == 1


def test_new_workspace_profile(tmp_path):
    destination = tmp_path / '작업실'
    create_workspace(str(destination), Path('config/profile.example.toml'), field='생활', name='예시', region='지역')
    text = (destination / 'profile.toml').read_text(encoding='utf-8')
    assert '[naver]' not in text
    assert 'experience_label' in text


@pytest.mark.parametrize('html, expected', [
    ('', NaverCounts()),
    ('&lt;h2&gt;문자&lt;/h2&gt;<!-- <li> --><p>strong a li</p>', NaverCounts()),
    ('<h2>소제목</h2><ul><li><strong>굵게</strong></li><li><a href="https://example.org">링크</a></li></ul><b>굵게</b>', NaverCounts(1, 2, 2, 1)),
])
def test_count_naver_body(html, expected):
    assert count_naver_body(html) == expected


def test_generated_counts_and_copy_boundary(tmp_path):
    draft = markdown_to_naver('# 제목\n## 첫째\n**강조**\n- 하나\n- [둘](https://example.org)\n## 출처\n[내 경험]\n---\n## 제외')
    assert count_naver_body(draft.html) == NaverCounts(2, 2, 2, 1)
    text = save_naver_html(tmp_path / 'draft.md', draft).read_text(encoding='utf-8')

    class Structure(HTMLParser):
        def __init__(self):
            super().__init__()
            self.divs = []
            self.parents = {}

        def handle_starttag(self, tag, attrs):
            ident = dict(attrs).get('id')
            if ident:
                self.parents[ident] = tuple(self.divs)
            if tag == 'div':
                self.divs.append(ident)

        def handle_endtag(self, tag):
            if tag == 'div':
                self.divs.pop()

    structure = Structure()
    structure.feed(text)
    assert structure.parents['frame-body'] == ()
    assert structure.parents['frame-bar'] == ()
    for ident in ('copy-body', 'copy-title', 'copy-status', 'frame-confirmation'):
        assert structure.parents[ident] == ('frame-bar',)
    assert f'<div id="frame-body">{draft.html}</div>' in text
    assert count_naver_body(draft.html).confirmation() in text
    assert not re.search(r'\.innerHTML\s*(?:[+]?=)', text)
    assert "navigator.clipboard.write" in text
    assert "'text/html'" in text and "'text/plain'" in text
    assert "range.selectNodeContents(target)" in text
    assert "if (!document.execCommand('copy'))" in text
    assert 'titleEl.textContent = document.title' in text
