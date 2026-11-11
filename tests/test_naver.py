"""변환·설정·CLI를 브라우저 없이 검증합니다."""
from pathlib import Path
import pytest
from frame.cli import main
from frame.config_loader import load_experience_label
from frame.core.naver import markdown_to_naver
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
    assert '평소 쓰는 크롬에서 네이버 블로그 글쓰기 열기 → HTML 파일을 브라우저로 열어 Ctrl+A, Ctrl+C → 에디터 본문에 Ctrl+V → 제목 입력 → 임시저장 → 발행은 직접' in output
    assert str(workspace.with_suffix('.naver.html')) in output
    assert '[내 경험 — 발행 전에 직접 채우세요]' in workspace.with_suffix('.naver.html').read_text(encoding='utf-8')


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
