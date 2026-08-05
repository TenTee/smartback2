import yaml
import json
import os
import re

# Paths
YAML_PATH = 'api_documentation.yaml'
HTML_PATH = 'api_documentation.html'

def load_schema():
    with open(YAML_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def resolve_ref(ref, components):
    if not ref or not ref.startswith('#/components/'):
        return {}
    parts = ref.split('/')
    # Assuming #/components/schemas/Name
    section = parts[2] # schemas
    name = parts[3]    # Name
    return components.get(section, {}).get(name, {})

def get_schema_summary(schema, components, seen=None):
    if seen is None:
        seen = set()
    
    if '$ref' in schema:
        ref_name = schema['$ref'].split('/')[-1]
        if ref_name in seen:
            return f"Recursive {ref_name}"
        seen.add(ref_name)
        resolved = resolve_ref(schema['$ref'], components)
        return get_schema_summary(resolved, components, seen)

    stype = schema.get('type', 'object')
    
    if stype == 'array':
        items = schema.get('items', {})
        item_summary = get_schema_summary(items, components, seen)
        return [item_summary]
    
    if stype == 'object':
        props = schema.get('properties', {})
        summary = {}
        required = schema.get('required', [])
        for name, prop in props.items():
            prop_summary = get_schema_summary(prop, components, seen.copy())
            if name in required:
                name = f"{name}*"
            summary[name] = prop_summary
        return summary
    
    # Primitive types
    fmt = schema.get('format', '')
    res = stype
    if fmt:
        res += f" ({fmt})"
    if 'enum' in schema:
        res += f" [enum: {', '.join(map(str, schema['enum']))}]"
    return res

def format_json_summary(summary):
    if summary is None:
        return "null"
    return json.dumps(summary, indent=2, ensure_ascii=False)

def generate_html(schema):
    paths = schema.get('paths', {})
    tags_info = schema.get('tags', [])
    components = schema.get('components', {})

    # Group endpoints by tags
    grouped = {}
    tag_descriptions = {t['name']: t.get('description', '') for t in tags_info}

    for path, methods in paths.items():
        for method, details in methods.items():
            if method.lower() not in ['get', 'post', 'put', 'patch', 'delete']:
                continue
            
            tags = details.get('tags', ['Other'])
            for tag in tags:
                if tag not in grouped:
                    grouped[tag] = []
                
                # Extract Request Body details
                req_info = None
                if details.get('requestBody'):
                    content = details['requestBody'].get('content', {})
                    for mime, body in content.items():
                        if 'schema' in body:
                            summary = get_schema_summary(body['schema'], components)
                            req_info = {
                                'mime': mime,
                                'schema': format_json_summary(summary)
                            }
                            break # Just take the first one for now (usually JSON)

                # Extract Response details
                res_info = None
                responses = details.get('responses', {})
                ok_code = next((c for c in ['200', '201', '204'] if c in responses), None)
                if ok_code:
                    res_details = responses[ok_code]
                    content = res_details.get('content', {})
                    for mime, body in content.items():
                        if 'schema' in body:
                            summary = get_schema_summary(body['schema'], components)
                            res_info = {
                                'code': ok_code,
                                'mime': mime,
                                'schema': format_json_summary(summary)
                            }
                            break
                    if not res_info:
                        res_info = {'code': ok_code, 'mime': 'text/plain', 'schema': 'No response body'}

                endpoint = {
                    'path': path,
                    'method': method.upper(),
                    'summary': details.get('summary', details.get('operationId', 'No Summary')),
                    'description': details.get('description', ''),
                    'req_info': req_info,
                    'res_info': res_info,
                }
                grouped[tag].append(endpoint)

    sorted_tags = sorted(grouped.keys())

    # Build Sidebar
    sidebar_links = ""
    for tag in sorted_tags:
        safe_tag = re.sub(r'[^a-z0-9]', '-', tag.lower())
        sidebar_links += f'            <a href="#{safe_tag}">{tag}</a>\n'

    # Build Content
    content_html = ""
    for tag in sorted_tags:
        safe_tag = re.sub(r'[^a-z0-9]', '-', tag.lower())
        endpoints = grouped[tag]
        desc = tag_descriptions.get(tag, "")
        
        content_html += f'''
        <section id="{safe_tag}" class="section">
          <div class="section-header"><h3>{tag}</h3><span class="section-count">{len(endpoints)} endpoints</span></div>
          {f'<p class="desc">{desc}</p>' if desc else ''}
          <div class="endpoint-list">
        '''
        
        for ep in endpoints:
            req_section = ""
            if ep['req_info']:
                req_section = f'''<h4>Requête ({ep['req_info']['mime']})</h4><pre>{ep['req_info']['schema']}</pre>'''
            
            res_section = ""
            if ep['res_info']:
                res_section = f'''<h4>Réponse {ep['res_info']['code']} ({ep['res_info']['mime']})</h4><pre>{ep['res_info']['schema']}</pre>'''

            content_html += f'''
            <article class="endpoint">
              <div class="endpoint-top"><span class="method {ep['method']}">{ep['method']}</span><div><div class="endpoint-path">{ep['path']}</div><div class="endpoint-title">{ep['summary']}</div></div></div>
              <div class="endpoint-body">
                <p class="desc">{ep['description']}</p>
                {req_section}
                {res_section}
              </div>
            </article>
            '''
        
        content_html += "          </div>\n        </section>\n"

    # Template
    info = schema.get('info', {})
    version = info.get('version', '1.0.0')

    template = f'''<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SmartCampus API - Documentation API</title>
  <style>
    :root {{
      --bg: #f4f7fb;
      --panel: #ffffff;
      --panel-soft: #eef4ff;
      --text: #122033;
      --muted: #5f6f85;
      --line: #d9e2ef;
      --accent: #0f62fe;
      --accent-2: #13315c;
      --success: #198754;
      --danger: #dc2626;
      --put: #7c3aed;
      --patch: #ea580c;
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace;
      --sans: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{ margin: 0; background: linear-gradient(180deg, #eef5ff 0%, var(--bg) 28%, #f8fbff 100%); color: var(--text); font-family: var(--sans); }}
    .layout {{ display: grid; grid-template-columns: 320px minmax(0, 1fr); min-height: 100vh; }}
    .sidebar {{ position: sticky; top: 0; align-self: start; height: 100vh; overflow: auto; background: rgba(19,49,92,.97); color: #fff; padding: 24px 18px; }}
    .brand h1 {{ margin: 0 0 8px; font-size: 1.4rem; }}
    .brand p {{ margin: 0 0 18px; color: rgba(255,255,255,.8); line-height: 1.5; }}
    .search {{ width: 100%; margin: 0 0 18px; padding: 12px 14px; border-radius: 12px; border: 1px solid rgba(255,255,255,.16); background: rgba(255,255,255,.08); color: #fff; outline: none; }}
    .search::placeholder {{ color: rgba(255,255,255,.55); }}
    .nav-group {{ margin-bottom: 18px; }}
    .nav-title {{ display: flex; justify-content: space-between; align-items: center; font-size: .85rem; text-transform: uppercase; letter-spacing: .08em; color: rgba(255,255,255,.62); margin-bottom: 10px; }}
    .nav-links {{ display: grid; gap: 8px; }}
    .nav-links a {{ color: #fff; text-decoration: none; padding: 10px 12px; border-radius: 10px; background: rgba(255,255,255,.04); font-size: .95rem; line-height: 1.35; }}
    .nav-links a:hover {{ background: rgba(255,255,255,.1); }}
    .main {{ padding: 32px; }}
    .hero {{ background: radial-gradient(circle at top right, rgba(15,98,254,.18), transparent 34%), linear-gradient(135deg, #fff 0%, #f4f8ff 100%); border: 1px solid var(--line); border-radius: 24px; padding: 28px; box-shadow: 0 20px 45px rgba(16,42,67,.08); margin-bottom: 22px; }}
    .hero-top {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; flex-wrap: wrap; }}
    .hero h2 {{ margin: 0 0 10px; font-size: 2rem; }}
    .hero p {{ margin: 0; color: var(--muted); max-width: 900px; white-space: pre-line; line-height: 1.6; }}
    .version {{ display: inline-flex; align-items: center; padding: 10px 14px; border-radius: 999px; background: var(--accent-2); color: #fff; font-weight: 700; }}
    .section {{ margin-top: 28px; }}
    .section-header {{ display: flex; justify-content: space-between; align-items: baseline; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }}
    .section h3 {{ margin: 0; font-size: 1.5rem; }}
    .section-count {{ color: var(--muted); font-size: .95rem; }}
    .endpoint-list {{ display: grid; gap: 16px; }}
    .endpoint {{ background: var(--panel); border: 1px solid var(--line); border-radius: 20px; overflow: hidden; box-shadow: 0 12px 36px rgba(15,23,42,.06); }}
    .endpoint-top {{ display: flex; gap: 14px; align-items: center; padding: 18px 20px; border-bottom: 1px solid var(--line); flex-wrap: wrap; }}
    .method {{ font-weight: 800; color: #fff; border-radius: 999px; padding: 7px 12px; min-width: 74px; text-align: center; font-size: .82rem; letter-spacing: .06em; }}
    .method.GET {{ background: var(--success); }}
    .method.POST {{ background: var(--accent); }}
    .method.PUT {{ background: var(--put); }}
    .method.PATCH {{ background: var(--patch); }}
    .method.DELETE {{ background: var(--danger); }}
    .endpoint-path {{ font-family: var(--mono); font-size: 1rem; word-break: break-all; color: var(--accent-2); font-weight: 700; }}
    .endpoint-title {{ font-weight: 700; font-size: 1.05rem; }}
    .endpoint-body {{ padding: 18px 20px 22px; display: grid; gap: 18px; }}
    .desc {{ color: var(--muted); line-height: 1.6; white-space: pre-line; }}
    pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; background: #0f172a; color: #dbeafe; padding: 14px; border-radius: 14px; font-size: .83rem; line-height: 1.55; overflow: auto; font-family: var(--mono); }}
    .footer {{ margin-top: 30px; color: var(--muted); text-align: center; font-size: .92rem; }}
    @media (max-width: 980px) {{ .layout {{ grid-template-columns: 1fr; }} .sidebar {{ position: static; height: auto; }} .main {{ padding: 20px; }} .hero {{ padding: 22px; }} }}
  </style>
</head>
<body>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">
        <h1>SmartCampus API</h1>
        <p>Documentation mise à jour depuis l'analyse des routes backend pour faciliter l'implémentation frontend.</p>
      </div>
      <input id="search" class="search" type="search" placeholder="Rechercher une route, un module, une méthode..." />
      <div id="sidebar-nav">
        <div class="nav-group">
          <div class="nav-title">Sections</div>
          <div class="nav-links">
{sidebar_links}
          </div>
        </div>
      </div>
    </aside>
    <main class="main">
      <section class="hero">
        <div class="hero-top">
          <div>
            <h2>SmartCampus API</h2>
            <p>Documentation complète du backend <code>smartback-new</code>.

Cette page présente toutes les routes exposées et leurs actions pour accélérer l'intégration frontend.</p>
          </div>
          <div class="version">Version {version}</div>
        </div>
      </section>
      <div id="content">
{content_html}
      </div>
      <div class="footer">Documentation mise à jour depuis l'analyse des routes backend de <code>smartback-new</code>.</div>
    </main>
  </div>
  <script>
    document.getElementById('search').addEventListener('input', (e) => {{
      const q = e.target.value.toLowerCase();
      document.querySelectorAll('.endpoint').forEach(el => {{
        const text = el.textContent.toLowerCase();
        el.style.display = text.includes(q) ? 'block' : 'none';
      }});
      document.querySelectorAll('.section').forEach(sec => {{
        const visible = sec.querySelectorAll('.endpoint[style="display: block"]').length;
        sec.style.display = visible > 0 || !q ? 'block' : 'none';
      }});
    }});
  </script>
</body>
</html>
'''
    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(template)

if __name__ == "__main__":
    if not os.path.exists(YAML_PATH):
        print(f"Error: {{YAML_PATH}} not found.")
    else:
        schema = load_schema()
        generate_html(schema)
        print(f"Successfully updated {{HTML_PATH}}")
