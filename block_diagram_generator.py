import ollama
import json
import re

def get_model():
    try:
        model_list = ollama.list().get('models', [])
        available  = []
        for m in model_list:
            try:
                name = m.get('name') or m.get('model') or ''
                available.append(name.split(':')[0])
            except:
                continue
        for preferred in ['llama3', 'mistral', 'phi3', 'llama2']:
            if preferred in available:
                return preferred
    except Exception as e:
        print(f"[DIAGRAM] Model list error: {e}")
    return 'llama3'

def generate_diagram_data(project_name, search_results):
    context = '\n\n'.join([
        f"[{h['filename']}]: {h['content']}"
        for h in search_results[:8]
    ])

    prompt = f"""Analyse this project: "{project_name}"

Content from project files:
{context[:3000]}

Return ONLY valid JSON describing a block diagram. No markdown, no explanation.
Identify the main system components, subsystems, and how they connect.

Return exactly this structure:
{{
  "title": "System Block Diagram",
  "blocks": [
    {{"id": "1", "label": "Component Name", "type": "input", "description": "brief description"}},
    {{"id": "2", "label": "Component Name", "type": "process", "description": "brief description"}},
    {{"id": "3", "label": "Component Name", "type": "output", "description": "brief description"}}
  ],
  "connections": [
    {{"from": "1", "to": "2", "label": "signal/data name"}},
    {{"from": "2", "to": "3", "label": "signal/data name"}}
  ]
}}

Types available: input, process, output, storage, control, display, power, comms
Generate 6-12 blocks and their connections based on the actual project content.
Each block label should be SHORT (2-4 words max).
Return ONLY the JSON."""

    model = get_model()
    print(f"[DIAGRAM] Using model: {model}")

    try:
        response = ollama.chat(
            model=model,
            messages=[{'role': 'user', 'content': prompt}],
            options={'num_predict': 1000, 'temperature': 0.1}
        )
        reply = response['message']['content']
        print(f"[DIAGRAM] Got reply: {reply[:150]}")

        json_match = re.search(r'\{[\s\S]*\}', reply)
        if not json_match:
            raise Exception("No JSON found in reply")

        data = json.loads(json_match.group())
        return data

    except Exception as e:
        print(f"[DIAGRAM] Error: {e}")
        # Return fallback diagram
        return {
            "title": f"{project_name} — System Block Diagram",
            "blocks": [
                {"id": "1", "label": "Input",       "type": "input",   "description": "System input"},
                {"id": "2", "label": "Processor",   "type": "process", "description": "Main processing unit"},
                {"id": "3", "label": "Controller",  "type": "control", "description": "Control logic"},
                {"id": "4", "label": "Memory",      "type": "storage", "description": "Data storage"},
                {"id": "5", "label": "Output",      "type": "output",  "description": "System output"},
                {"id": "6", "label": "Display",     "type": "display", "description": "User interface"},
            ],
            "connections": [
                {"from": "1", "to": "2", "label": "data"},
                {"from": "2", "to": "3", "label": "control"},
                {"from": "2", "to": "4", "label": "read/write"},
                {"from": "3", "to": "2", "label": "feedback"},
                {"from": "2", "to": "5", "label": "output"},
                {"from": "5", "to": "6", "label": "display"},
            ]
        }

def generate_svg(data, project_name):
    blocks      = data.get('blocks', [])
    connections = data.get('connections', [])
    title       = data.get('title', project_name + ' Block Diagram')

    # Color map by type
    colors = {
        'input':   {'fill': '#1e3a5f', 'stroke': '#378ADD', 'text': '#7ec8f8'},
        'process': {'fill': '#0a2e1a', 'stroke': '#1D9E75', 'text': '#6ee7b7'},
        'output':  {'fill': '#3b1a1a', 'stroke': '#E24B4A', 'text': '#fca5a5'},
        'storage': {'fill': '#2e2a0a', 'stroke': '#BA7517', 'text': '#fcd34d'},
        'control': {'fill': '#2a1a3b', 'stroke': '#7F77DD', 'text': '#c4b5fd'},
        'display': {'fill': '#1a2e3b', 'stroke': '#378ADD', 'text': '#7ec8f8'},
        'power':   {'fill': '#3b2a0a', 'stroke': '#EF9F27', 'text': '#fcd34d'},
        'comms':   {'fill': '#0a2e2e', 'stroke': '#1D9E75', 'text': '#6ee7b7'},
    }
    default_color = {'fill': '#1a1a2e', 'stroke': '#5F5E5A', 'text': '#d1d5db'}

    # Layout: arrange blocks in rows of 3
    BOX_W    = 160
    BOX_H    = 60
    PAD_X    = 60
    PAD_Y    = 70
    COLS     = 3
    START_X  = 60
    START_Y  = 100

    positions = {}
    for i, block in enumerate(blocks):
        col = i % COLS
        row = i // COLS
        x   = START_X + col * (BOX_W + PAD_X)
        y   = START_Y + row * (BOX_H + PAD_Y)
        positions[block['id']] = {'x': x, 'y': y, 'cx': x + BOX_W//2, 'cy': y + BOX_H//2}

    rows     = (len(blocks) + COLS - 1) // COLS
    svg_w    = START_X * 2 + COLS * BOX_W + (COLS - 1) * PAD_X
    svg_h    = START_Y + rows * (BOX_H + PAD_Y) + 60

    svg_parts = []
    svg_parts.append(f'''<svg viewBox="0 0 {svg_w} {svg_h}" xmlns="http://www.w3.org/2000/svg" style="width:100%;background:#0a0f1e;border-radius:12px;font-family:sans-serif">''')

    # Title
    svg_parts.append(f'<text x="{svg_w//2}" y="40" text-anchor="middle" font-size="16" font-weight="500" fill="#7ec8f8">{title}</text>')
    svg_parts.append(f'<text x="{svg_w//2}" y="58" text-anchor="middle" font-size="11" fill="#5F5E5A">{project_name}</text>')

    # Draw connections first (behind blocks)
    svg_parts.append('<g id="connections">')
    for conn in connections:
        fid  = conn.get('from')
        tid  = conn.get('to')
        lbl  = conn.get('label', '')
        if fid not in positions or tid not in positions:
            continue
        fp = positions[fid]
        tp = positions[tid]
        x1, y1 = fp['cx'], fp['cy'] + BOX_H // 2
        x2, y2 = tp['cx'], tp['cy'] - BOX_H // 2

        # If same row, connect side to side
        if abs(fp['y'] - tp['y']) < 10:
            if fp['x'] < tp['x']:
                x1 = fp['x'] + BOX_W
                y1 = fp['cy']
                x2 = tp['x']
                y2 = tp['cy']
            else:
                x1 = fp['x']
                y1 = fp['cy']
                x2 = tp['x'] + BOX_W
                y2 = tp['cy']

        mx = (x1 + x2) // 2
        my = (y1 + y2) // 2

        svg_parts.append(f'<defs><marker id="arr_{fid}_{tid}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M2 1L8 5L2 9" fill="none" stroke="#378ADD" stroke-width="1.5"/></marker></defs>')
        svg_parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#378ADD" stroke-width="1.5" stroke-dasharray="4,3" opacity="0.6" marker-end="url(#arr_{fid}_{tid})"/>')

        if lbl:
            svg_parts.append(f'<rect x="{mx-25}" y="{my-9}" width="50" height="16" rx="4" fill="#0a0f1e" opacity="0.9"/>')
            svg_parts.append(f'<text x="{mx}" y="{my+4}" text-anchor="middle" font-size="9" fill="#5F5E5A">{lbl[:12]}</text>')

    svg_parts.append('</g>')

    # Draw blocks
    svg_parts.append('<g id="blocks">')
    for block in blocks:
        bid   = block['id']
        label = block.get('label', 'Block')
        btype = block.get('type', 'process')
        desc  = block.get('description', '')

        if bid not in positions:
            continue

        pos = positions[bid]
        x, y = pos['x'], pos['y']
        c   = colors.get(btype, default_color)

        svg_parts.append(f'<rect x="{x}" y="{y}" width="{BOX_W}" height="{BOX_H}" rx="8" fill="{c["fill"]}" stroke="{c["stroke"]}" stroke-width="1.5"/>')

        # Type badge
        svg_parts.append(f'<rect x="{x+6}" y="{y+6}" width="{len(btype)*6+8}" height="14" rx="4" fill="{c["stroke"]}" opacity="0.3"/>')
        svg_parts.append(f'<text x="{x+10}" y="{y+17}" font-size="9" fill="{c["stroke"]}">{btype.upper()}</text>')

        # Label
        words = label.split()
        if len(words) > 2:
            line1 = ' '.join(words[:2])
            line2 = ' '.join(words[2:])
            svg_parts.append(f'<text x="{x + BOX_W//2}" y="{y+36}" text-anchor="middle" font-size="13" font-weight="500" fill="{c["text"]}">{line1}</text>')
            svg_parts.append(f'<text x="{x + BOX_W//2}" y="{y+50}" text-anchor="middle" font-size="11" fill="{c["text"]}" opacity="0.8">{line2}</text>')
        else:
            svg_parts.append(f'<text x="{x + BOX_W//2}" y="{y+40}" text-anchor="middle" font-size="13" font-weight="500" fill="{c["text"]}">{label}</text>')

    svg_parts.append('</g>')

    # Legend
    legend_x = 20
    legend_y = svg_h - 40
    svg_parts.append(f'<text x="{legend_x}" y="{legend_y}" font-size="10" fill="#5F5E5A">Generated by Dynalog AI — {project_name}</text>')

    svg_parts.append('</svg>')
    return '\n'.join(svg_parts)