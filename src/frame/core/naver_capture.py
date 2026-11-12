"""사용자가 개발자도구에서 실행하는 읽기 전용 수집 코드."""

CAPTURE_SCRIPT = r"""(() => {
  const f=document.querySelector('#mainFrame'); const d=(f&&f.contentDocument)||document;
  const title = d.querySelector('.se-documentTitle .se-text-paragraph, .se-title-text, #title');
  const root = d.querySelector('.se-main-container, .se-content, #body, #frame-body') || d.body;
  const selector = 'p,h1,h2,h3,h4,h5,h6,li,.se-text-paragraph';
  const style = e => (d.defaultView || window).getComputedStyle(e);
  const weight = e => {
    const w = style(e).fontWeight;
    return w === 'bold' ? 700 : w === 'normal' ? 400 : (parseFloat(w) || 400);
  };
  const text = e => (e.innerText || '').trim();
  const blocks = Array.from(root.querySelectorAll(selector))
    .filter(e => !e.closest('.se-documentTitle') && !e.querySelector(selector))
    .map(e => ({tag: e.tagName.toLowerCase(), cls: String(e.className || '').slice(0, 200),
      text: text(e), fontSize: parseFloat(style(e).fontSize) || 0, fontWeight: weight(e),
      inList: e.closest('ul,ol,.se-list,[class*="list"]') != null,
      bulletPrefix: /^(?:[•·*\-]|\d+[.)])\s*/u.test(text(e))}))
    .filter(b => b.text);
  const links = Array.from(root.querySelectorAll('a[href]'))
    .map(e => ({text: text(e), href: e.href}));
  const bolds = [...new Set(Array.from(root.querySelectorAll('b,strong,span,font'))
    .filter(e => weight(e) >= 600).map(text).filter(Boolean))];
  const result = {title: title ? (title.tagName.toLowerCase() === 'input' ? title.value : text(title)) : '',
    blocks, links, bolds, meta: {url: location.href, at: new Date().toISOString(), schema: 1}};
  const json = JSON.stringify(result);
  if (typeof copy === 'function') { try { copy(JSON.stringify(result)); } catch (_) {} }
  return json;
})()"""
