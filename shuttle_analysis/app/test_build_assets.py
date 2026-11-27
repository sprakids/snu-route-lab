import tempfile,unittest
from pathlib import Path
from build_static import build

class AssetVersionsTests(unittest.TestCase):
    def setup_tree(self,root):
        p=root/'static';p.mkdir();(p/'app.js').write_text("import {RouteMap} from './map.js';\nconst version=1;",encoding='utf-8')
        (p/'map.js').write_text('export class RouteMap {}',encoding='utf-8');(p/'style.css').write_text('body{color:black}',encoding='utf-8')
        (p/'index.html').write_text('<link href="/style.css"><script src="/app.js" type="module"></script>',encoding='utf-8')
    def test_build_versions_assets_without_modifying_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.setup_tree(root);before=(root/'static/app.js').read_bytes();public=build(root)
            self.assertIn('/app.js?v=',(public/'index.html').read_text());self.assertIn('/style.css?v=',(public/'index.html').read_text())
            self.assertIn('./map.js?v=',(public/'app.js').read_text());self.assertEqual(before,(root/'static/app.js').read_bytes())
    def test_map_change_changes_both_import_and_entry_asset_version(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.setup_tree(root);build(root);old=(root/'public/index.html').read_text()
            (root/'static/map.js').write_text('export class RouteMap { updated=true; }',encoding='utf-8');build(root)
            self.assertNotEqual(old,(root/'public/index.html').read_text())
    def test_wide_layout_changes_invalidate_stylesheet_link(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.setup_tree(root)
            (root/'static/wide.css').write_text('body{--wide-panel:360px}',encoding='utf-8')
            with (root/'static/index.html').open('a',encoding='utf-8') as page:page.write('<link href="/wide.css">')
            build(root);old=(root/'public/index.html').read_text()
            self.assertIn('/wide.css?v=',old)
            (root/'static/wide.css').write_text('body{--wide-panel:320px}',encoding='utf-8');build(root)
            self.assertNotEqual(old,(root/'public/index.html').read_text())
    def test_settings_changes_invalidate_app_and_policy_asset_links(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.setup_tree(root)
            (root/'static/settings.js').write_text('const preference=1;',encoding='utf-8')
            (root/'static/settings.css').write_text('dialog{color:black}',encoding='utf-8')
            markup='<script src="/settings.js"></script><link href="/settings.css">'
            (root/'static/privacy.html').write_text(markup,encoding='utf-8')
            with (root/'static/index.html').open('a',encoding='utf-8') as page:page.write(markup)
            build(root)
            old={name:(root/'public'/name).read_text() for name in ('index.html','privacy.html')}
            for text in old.values():self.assertIn('/settings.js?v=',text);self.assertIn('/settings.css?v=',text)
            (root/'static/settings.js').write_text('const preference=2;',encoding='utf-8');build(root)
            for name in old:self.assertNotEqual(old[name],(root/'public'/name).read_text())
    def test_motion_scripts_and_styles_are_versioned_in_app_and_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.setup_tree(root)
            for name,text in [('motion.js','const animation=1;'),('motion.css','.liquid-ripple{opacity:1}')]:
                (root/'static'/name).write_text(text,encoding='utf-8')
            markup='<script src="/motion.js" defer></script><link href="/motion.css">'
            (root/'static/accessibility.html').write_text(markup,encoding='utf-8')
            with (root/'static/index.html').open('a',encoding='utf-8') as page:page.write(markup)
            build(root);old=(root/'public/index.html').read_text()
            self.assertIn('/motion.js?v=',old);self.assertIn('/motion.css?v=',old)
            (root/'static/motion.css').write_text('.liquid-ripple{opacity:0}',encoding='utf-8');build(root)
            self.assertNotEqual(old,(root/'public/index.html').read_text())
            self.assertIn('/motion.css?v=',(root/'public/accessibility.html').read_text())

if __name__=='__main__':unittest.main()
