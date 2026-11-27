"""Copy only public assets into Vercel's static output; never runtime data or credentials."""
import hashlib,shutil
from pathlib import Path

def build(root=None):
    root=Path(root) if root else Path(__file__).resolve().parent
    public=root/'public';shutil.copytree(root/'static',public,dirs_exist_ok=True)
    digest=lambda name:hashlib.sha256((public/name).read_bytes()).hexdigest()[:16]
    # Version both the entry module and its import so cached visitors get new code.
    app=public/'app.js';text=app.read_text(encoding='utf-8')
    app.write_text(text.replace("'./map.js'",f"'./map.js?v={digest('map.js')}'"),encoding='utf-8')
    for page in public.glob('*.html'):
        html=page.read_text(encoding='utf-8')
        html=html.replace('src="/app.js"',f'src="/app.js?v={digest("app.js")}"')
        html=html.replace('href="/style.css"',f'href="/style.css?v={digest("style.css")}"')
        for name,attr in [('campus-theme.css','href'),('campus-theme.js','src'),('mobile.css','href'),('wide.css','href'),('settings.css','href'),('settings.js','src'),('motion.css','href'),('motion.js','src')]:
            if (public/name).exists():html=html.replace(f'{attr}="/{name}"',f'{attr}="/{name}?v={digest(name)}"')
        page.write_text(html,encoding='utf-8')
    return public

if __name__=='__main__':build();print('Prepared versioned public map assets.')
