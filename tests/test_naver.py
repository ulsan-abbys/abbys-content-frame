"""변환·설정·CLI를 브라우저 없이 검증합니다."""
from pathlib import Path
import pytest
from frame.cli import main
from frame.config_loader import load_naver_settings
from frame.core.naver import markdown_to_naver, NaverLoginRequired
from frame.adapters.naver_html import save_naver_html
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
    assert '<h1>제목 &lt;안전&gt;</h1>' in text
    assert '<p>본문</p>' in text
    assert source.read_text(encoding='utf-8') == '원본'


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / 'profile.toml').write_text('[naver]\nblog_id="sample_blog"\n[writing]\nexperience_label="체험"', encoding='utf-8')
    folder = tmp_path / '초안'
    folder.mkdir()
    path = folder / '글.md'
    path.write_text('# 제목\n본문 [체험]', encoding='utf-8')
    return path


def test_blog_id_precedence(workspace):
    assert load_naver_settings(workspace, None) == ('sample_blog', '체험')
    assert load_naver_settings(workspace, 'override') == ('override', '체험')
    assert load_naver_settings(workspace, '') == ('', '체험')


def test_no_profile_uses_default_label_and_cli_id(tmp_path):
    path = tmp_path / 'draft.md'
    assert load_naver_settings(path, 'example') == ('example', '내 경험')
    assert load_naver_settings(path, None) == ('', '내 경험')


def test_empty_draft_keeps_html_but_never_opens_browser(workspace):
    workspace.write_text('# 제목\n---\n점검표', encoding='utf-8')
    saver = FakeSaver()
    assert main(['naver', 'draft', str(workspace)], draft_saver=saver) == 1
    assert workspace.with_suffix('.naver.html').is_file()
    assert not saver.saved


class FakeSaver:
    def __init__(self, error=None):
        self.saved = []
        self.logged_in = False
        self.error = error

    def login(self):
        self.logged_in = True

    def save_draft(self, blog_id, draft, *, close=False):
        if self.error:
            raise self.error
        self.saved.append((blog_id, draft, close))


def test_cli_draft(workspace, capsys):
    saver = FakeSaver()
    assert main(['naver', 'draft', str(workspace), '--blog-id', 'override', '--close'], draft_saver=saver) == 0
    blog_id, draft, close = saver.saved[0]
    assert (blog_id, draft.title, close) == ('override', '제목', True)
    assert draft.has_experience_slots
    assert '경고' in capsys.readouterr().out
    assert workspace.with_suffix('.naver.html').is_file()


def test_cli_login():
    saver = FakeSaver()
    assert main(['naver', 'login'], draft_saver=saver) == 0
    assert saver.logged_in


@pytest.mark.parametrize('error,code', [(NaverLoginRequired('frame naver login 먼저'), 2), (RuntimeError('본문 단계 실패'), 1)])
def test_cli_failure_keeps_html(workspace, error, code, capsys):
    assert main(['naver', 'draft', str(workspace)], draft_saver=FakeSaver(error)) == code
    assert workspace.with_suffix('.naver.html').is_file()
    assert str(error) in capsys.readouterr().out


def test_cli_missing_blog_id(workspace, capsys):
    saver = FakeSaver()
    assert main(['naver', 'draft', str(workspace), '--blog-id', ''], draft_saver=saver) == 2
    assert not saver.saved
    assert 'blog_id' in capsys.readouterr().out
    assert workspace.with_suffix('.naver.html').is_file()


def test_new_workspace_naver_profile(tmp_path):
    destination = tmp_path / '작업실'
    create_workspace(str(destination), Path('config/profile.example.toml'), field='생활', name='예시', region='지역')
    text = (destination / 'profile.toml').read_text(encoding='utf-8')
    assert '[naver]\nblog_id = ""' in text


@pytest.mark.parametrize('blog_id', ['https://example.org', '../elsewhere', 'id?x=1'])
def test_invalid_id_never_opens_browser(workspace, blog_id):
    saver = FakeSaver()
    assert main(['naver', 'draft', str(workspace), '--blog-id', blog_id], draft_saver=saver) == 2
    assert not saver.saved
