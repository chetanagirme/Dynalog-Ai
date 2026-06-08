from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, Response, stream_with_context, send_file
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import ollama
import os
import datetime
import zipfile
import json
from rag_engine import index_file, search_project, delete_project_index, delete_file_from_index

app = Flask(__name__)
app.secret_key = 'dynalog-secret-key-change-this-2024'

UPLOAD_FOLDER      = 'uploads'
BLOCKED_EXTENSIONS = {
    'exe','dll','so','bin','iso',
    'mp4','mp3','avi','mov',
    'jpg','jpeg','png','gif','bmp','ico','svg'
}
app.config['UPLOAD_FOLDER']      = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username, full_name, role):
        self.id        = id
        self.username  = username
        self.full_name = full_name
        self.role      = role

def get_db():
    conn = sqlite3.connect('data/users.db')
    conn.row_factory = sqlite3.Row
    return conn

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    conn.close()
    if user:
        return User(user['id'], user['username'], user['full_name'], user['role'])
    return None

def allowed_file(filename):
    if not filename:
        return False
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext not in BLOCKED_EXTENSIONS

def log_activity(project_id, user_id, action, detail=''):
    try:
        conn = get_db()
        conn.execute(
            'INSERT INTO project_activity (project_id, user_id, action, detail) VALUES (?,?,?,?)',
            (project_id, user_id, action, detail)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Log error: {e}")

def get_best_model():
    try:
        models = ollama.list()
        model_list = models.get('models', [])
        names = []
        for m in model_list:
            try:
                name = m.get('name') or m.get('model') or str(m)
                names.append(name.split(':')[0])
            except:
                continue
        for preferred in ['phi3', 'mistral', 'llama3', 'llama2']:
            if preferred in names:
                return preferred
    except Exception as e:
        print(f"Model list error: {e}")
    return 'llama3'

# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        conn     = get_db()
        user     = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            u = User(user['id'], user['username'], user['full_name'], user['role'])
            login_user(u)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()
    projects = conn.execute('''
        SELECT p.*,
               u.full_name as creator_name,
               COUNT(DISTINCT pf.id) as file_count,
               COUNT(DISTINCT ch.id) as chat_count
        FROM projects p
        LEFT JOIN users u ON p.created_by = u.id
        LEFT JOIN project_files pf ON pf.project_id = p.id
        LEFT JOIN chat_history ch ON ch.project_id = p.id
        WHERE p.status = 'active'
        GROUP BY p.id
        ORDER BY p.updated_at DESC
    ''').fetchall()
    conn.close()
    return render_template('dashboard.html', projects=projects)

# ── Project CRUD ──────────────────────────────────────────────────────────────

@app.route('/project/new', methods=['POST'])
@login_required
def new_project():
    name = request.form.get('name', '').strip()
    desc = request.form.get('description', '').strip()
    if not name:
        flash('Project name is required')
        return redirect(url_for('dashboard'))
    conn   = get_db()
    cursor = conn.execute(
        'INSERT INTO projects (name, description, created_by) VALUES (?,?,?)',
        (name, desc, current_user.id)
    )
    project_id = cursor.lastrowid
    conn.commit()
    conn.close()
    log_activity(project_id, current_user.id, 'created', f'Project "{name}" created')
    return redirect(url_for('project', project_id=project_id))


@app.route('/project/<int:project_id>/delete', methods=['POST'])
@login_required
def delete_project(project_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    conn = get_db()
    conn.execute("UPDATE projects SET status='deleted' WHERE id=?", (project_id,))
    conn.commit()
    conn.close()
    delete_project_index(project_id)
    return redirect(url_for('dashboard'))

# ── File Upload ───────────────────────────────────────────────────────────────

@app.route('/project/<int:project_id>/upload', methods=['POST'])
@login_required
def upload_files(project_id):
    results        = []
    project_folder = os.path.join(UPLOAD_FOLDER, str(project_id))
    os.makedirs(project_folder, exist_ok=True)

    all_files = []
    for field in ['files', 'folder']:
        received = request.files.getlist(field)
        all_files.extend(received)

    print(f"[Upload] {len(all_files)} file(s) received for project {project_id}")

    if not all_files:
        return jsonify({'results': [], 'error': 'No files received'}), 400

    for file in all_files:
        if not file or not file.filename or file.filename.strip() == '':
            continue
        original_name = file.filename.replace('\\', '/')
        basename      = os.path.basename(original_name)
        if not basename:
            continue
        filename = secure_filename(basename)
        if not filename:
            continue
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'txt'

        if ext == 'zip':
            zip_path = os.path.join(project_folder, filename)
            file.save(zip_path)
            extracted = _extract_zip(zip_path, project_folder, project_id)
            try:
                os.remove(zip_path)
            except:
                pass
            results.extend(extracted)
        elif allowed_file(filename):
            filepath = os.path.join(project_folder, filename)
            file.save(filepath)
            size     = os.path.getsize(filepath)
            ok, info = index_file(project_id, filepath, filename)
            _save_file_record(project_id, filename, original_name, ext, size, ok)
            results.append({
                'filename': filename,
                'original': original_name,
                'success':  ok,
                'chunks':   info if ok else 0,
                'error':    '' if ok else str(info)
            })
            if ok:
                log_activity(project_id, current_user.id, 'uploaded',
                             f'File "{filename}" indexed ({info} chunks)')

    _update_project_timestamp(project_id)
    return jsonify({'results': results})

def _extract_zip(zip_path, dest_folder, project_id):
    results = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            for member in z.namelist():
                if member.endswith('/'):
                    continue
                basename = os.path.basename(member)
                if not basename:
                    continue
                filename = secure_filename(basename)
                if not filename or not allowed_file(filename):
                    continue
                filepath = os.path.join(dest_folder, filename)
                with z.open(member) as src, open(filepath, 'wb') as dst:
                    dst.write(src.read())
                size     = os.path.getsize(filepath)
                ext      = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'txt'
                ok, info = index_file(project_id, filepath, filename)
                _save_file_record(project_id, filename, member, ext, size, ok)
                results.append({
                    'filename': filename,
                    'original': member,
                    'success':  ok,
                    'chunks':   info if ok else 0,
                    'error':    '' if ok else str(info)
                })
                if ok:
                    log_activity(project_id, current_user.id, 'uploaded',
                                 f'"{filename}" from ZIP ({info} chunks)')
    except Exception as e:
        results.append({'filename': 'ZIP file', 'success': False, 'chunks': 0, 'error': str(e)})
    return results

def _save_file_record(project_id, filename, original_name, file_type, size, indexed):
    conn = get_db()
    try:
        existing = conn.execute(
            'SELECT id FROM project_files WHERE project_id=? AND filename=?',
            (project_id, filename)
        ).fetchone()
        if existing:
            conn.execute(
                'UPDATE project_files SET indexed=?, file_size=?, uploaded_at=? WHERE id=?',
                (1 if indexed else 0, size, datetime.datetime.now(), existing['id'])
            )
        else:
            conn.execute(
                '''INSERT INTO project_files
                   (project_id, filename, original_name, file_type, file_size, indexed, uploaded_by)
                   VALUES (?,?,?,?,?,?,?)''',
                (project_id, filename, original_name, file_type,
                 size, 1 if indexed else 0, current_user.id)
            )
        conn.commit()
    except Exception as e:
        print(f"Save record error: {e}")
    finally:
        conn.close()

def _update_project_timestamp(project_id):
    conn = get_db()
    conn.execute('UPDATE projects SET updated_at=? WHERE id=?',
                 (datetime.datetime.now(), project_id))
    conn.commit()
    conn.close()

@app.route('/project/<int:project_id>/delete-file/<int:file_id>', methods=['DELETE'])
@login_required
def delete_file(project_id, file_id):
    conn = get_db()
    f    = conn.execute(
        'SELECT * FROM project_files WHERE id=? AND project_id=?',
        (file_id, project_id)
    ).fetchone()
    if f:
        filepath = os.path.join(UPLOAD_FOLDER, str(project_id), f['filename'])
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except:
                pass
        delete_file_from_index(project_id, f['filename'])
        conn.execute('DELETE FROM project_files WHERE id=?', (file_id,))
        conn.commit()
        log_activity(project_id, current_user.id, 'deleted',
                     f'File "{f["filename"]}" removed')
    conn.close()
    return jsonify({'success': True})

# ── Chat ──────────────────────────────────────────────────────────────────────

@app.route('/project/<int:project_id>')
@app.route('/project/<int:project_id>/chat')
@app.route('/project/<int:project_id>/chat/<int:conversation_id>')
@login_required
def project_chat(project_id, conversation_id=None):
    conn = get_db()
    proj = conn.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
    if not proj:
        return redirect(url_for('dashboard'))
    conversations = conn.execute('''
        SELECT c.*, COUNT(ch.id) as msg_count
        FROM conversations c
        LEFT JOIN chat_history ch ON ch.conversation_id = c.id
        WHERE c.project_id = ?
        GROUP BY c.id
        ORDER BY c.updated_at DESC
    ''', (project_id,)).fetchall()
    history        = []
    active_conv_id = None
    if conversation_id:
        conv = conn.execute(
            'SELECT id FROM conversations WHERE id=? AND project_id=?',
            (conversation_id, project_id)
        ).fetchone()
        if conv:
            active_conv_id = conversation_id
            history        = conn.execute('''
                SELECT message, response, sources, timestamp
                FROM chat_history
                WHERE conversation_id=?
                ORDER BY timestamp ASC
            ''', (conversation_id,)).fetchall()
    files     = conn.execute(
        '''SELECT pf.*, u.full_name as uploader_name
           FROM project_files pf
           LEFT JOIN users u ON pf.uploaded_by = u.id
           WHERE pf.project_id=?
           ORDER BY pf.uploaded_at DESC''',
        (project_id,)
    ).fetchall()
    today     = datetime.date.today().isoformat()
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    convs_fixed = [{
        'id':         c['id'],
        'title':      c['title'],
        'updated_at': c['updated_at'][:10],
        'msg_count':  c['msg_count']
    } for c in conversations]
    conn.close()
    return render_template('notebook.html',
        project=proj,
        conversations=convs_fixed,
        history=history,
        active_conv_id=active_conv_id,
        files=files,
        today=today,
        yesterday=yesterday
    )
   
@app.route('/api/project/<int:project_id>/chat', methods=['POST'])
@login_required
def api_project_chat(project_id):
    data            = request.json
    user_message    = data.get('message', '').strip()
    conversation_id = data.get('conversation_id')

    if not user_message:
        return jsonify({'error': 'Empty message'}), 400

    hits = search_project(project_id, user_message, n_results=5)

    conn      = get_db()
    proj      = conn.execute('SELECT name FROM projects WHERE id=?', (project_id,)).fetchone()
    proj_name = proj['name'] if proj else 'Unknown Project'

    if not hits:
        no_result_reply = "I could not find any relevant information in the project files. Please make sure files have been uploaded and indexed."
        is_new = False
        if not conversation_id:
            title  = user_message[:50]
            cursor = conn.execute(
                'INSERT INTO conversations (user_id, project_id, title, updated_at) VALUES (?,?,?,?)',
                (current_user.id, project_id, title, datetime.datetime.now())
            )
            conversation_id = cursor.lastrowid
            is_new = True
        conn.execute(
            'INSERT INTO chat_history (user_id, conversation_id, project_id, message, response, sources) VALUES (?,?,?,?,?,?)',
            (current_user.id, conversation_id, project_id, user_message, no_result_reply, '[]')
        )
        conn.commit()
        conn.close()
        return jsonify({'reply': no_result_reply, 'sources': [], 'conversation_id': conversation_id, 'is_new': is_new})

    context = ""
    sources = []
    seen    = set()
    for h in hits:
        fname    = h['filename']
        context += f"\n\n[Source: {fname}]\n{h['content']}"
        if fname not in seen:
            sources.append({'filename': fname, 'score': h['score']})
            seen.add(fname)

    system_prompt = f"""You are a secure AI assistant for Dynalog Defence Organisation.
Project: "{proj_name}".
Answer ONLY from the document excerpts below.
If not found say: "This information is not available in the project files."
Always cite which file your answer comes from.
Be concise and professional.

Document excerpts:
{context}"""

    prev_messages = []
    if conversation_id:
        prev = conn.execute(
            'SELECT message, response FROM chat_history WHERE conversation_id=? ORDER BY timestamp DESC LIMIT 6',
            (conversation_id,)
        ).fetchall()
        for p in reversed(prev):
            prev_messages.append({'role': 'user',      'content': p['message']})
            prev_messages.append({'role': 'assistant', 'content': p['response']})
    prev_messages.append({'role': 'user', 'content': user_message})

    is_new = False
    if not conversation_id:
        title  = user_message[:50] + ('...' if len(user_message) > 50 else '')
        cursor = conn.execute(
            'INSERT INTO conversations (user_id, project_id, title, updated_at) VALUES (?,?,?,?)',
            (current_user.id, project_id, title, datetime.datetime.now())
        )
        conversation_id = cursor.lastrowid
        conn.commit()
        is_new = True
    else:
        conn.execute('UPDATE conversations SET updated_at=? WHERE id=?',
                     (datetime.datetime.now(), conversation_id))
        conn.commit()

    model = get_best_model()
    conn.close()

    def generate():
        full_reply = ""
        try:
            stream = ollama.chat(
                model=model,
                messages=[{'role': 'system', 'content': system_prompt}] + prev_messages,
                stream=True
            )
            meta = json.dumps({
                'type':            'meta',
                'sources':         sources,
                'conversation_id': conversation_id,
                'is_new':          is_new
            })
            yield f"data: {meta}\n\n"

            for chunk in stream:
                token = chunk['message']['content']
                full_reply += token
                yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            error_msg = f"AI error: {str(e)}. Make sure Ollama is running."
            full_reply = error_msg
            yield f"data: {json.dumps({'type': 'token', 'text': error_msg})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        finally:
            try:
                db = get_db()
                db.execute(
                    'INSERT INTO chat_history (user_id, conversation_id, project_id, message, response, sources) VALUES (?,?,?,?,?,?)',
                    (current_user.id, conversation_id, project_id,
                     user_message, full_reply, json.dumps(sources))
                )
                db.commit()
                db.close()
                log_activity(project_id, current_user.id, 'chat', f'Asked: {user_message[:60]}')
            except Exception as e:
                print(f"Save chat error: {e}")

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )

@app.route('/api/delete-conversation/<int:conv_id>', methods=['DELETE'])
@login_required
def delete_conversation(conv_id):
    conn = get_db()
    conn.execute('DELETE FROM chat_history WHERE conversation_id=?', (conv_id,))
    conn.execute('DELETE FROM conversations WHERE id=?', (conv_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ── PowerPoint generator ──────────────────────────────────────────────────────

@app.route('/project/<int:project_id>/generate-ppt', methods=['POST'])
@login_required
def generate_ppt_route(project_id):
    try:
        from ppt_generator import generate_ppt
        conn = get_db()
        proj = conn.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
        conn.close()
        if not proj:
            return jsonify({'error': 'Project not found'}), 404
        topic = request.json.get('topic', 'project overview')
        hits  = search_project(project_id,
                               topic + ' overview specifications components results',
                               n_results=15)
        if not hits:
            return jsonify({'error': 'No indexed files found. Please upload and index files first.'}), 400
        buf      = generate_ppt(
            project_name=proj['name'],
            project_desc=proj['description'] or '',
            search_results=hits
        )
        filename = proj['name'].replace(' ', '_') + '_presentation.pptx'
        log_activity(project_id, current_user.id, 'generated', f'PowerPoint: {filename}')
        return send_file(
            buf,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation'
        )
    except Exception as e:
        print(f"PPT error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/project/<int:project_id>/generate-ppt', methods=['POST'])
@login_required
def generate_ppt_api(project_id):
    return generate_ppt_route(project_id)

# ── Admin ─────────────────────────────────────────────────────────────────────
# ── Block diagram generator ───────────────────────────────────────────────────

@app.route('/project/<int:project_id>/generate-diagram', methods=['POST'])
@login_required
def generate_diagram(project_id):
    try:
        from block_diagram_generator import generate_diagram_data, generate_svg

        conn = get_db()
        proj = conn.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
        conn.close()

        if not proj:
            return jsonify({'error': 'Project not found'}), 404

        hits = search_project(
            project_id,
            'system architecture components modules signal flow connections',
            n_results=12
        )

        if not hits:
            return jsonify({'error': 'No indexed files found. Please upload and index files first.'}), 400

        data = generate_diagram_data(proj['name'], hits)
        svg  = generate_svg(data, proj['name'])

        log_activity(project_id, current_user.id, 'generated',
                     f'Block diagram generated for {proj["name"]}')

        return jsonify({'svg': svg, 'title': data.get('title', proj['name'])})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/project/<int:project_id>/generate-diagram', methods=['POST'])
@login_required
def generate_diagram_api(project_id):
    return generate_diagram(project_id)

# ── NotebookLM style features ─────────────────────────────────────────────────

@app.route('/project/<int:project_id>/generate-overview', methods=['POST'])
@login_required
def generate_overview(project_id):
    try:
        from report_generator import generate_overview
        conn = get_db()
        proj = conn.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
        conn.close()
        hits = search_project(project_id, 'project overview summary objectives', n_results=10)
        if not hits:
            return jsonify({'error': 'No indexed files found'}), 400
        data = generate_overview(proj['name'], hits)
        log_activity(project_id, current_user.id, 'generated', 'Project overview generated')
        return jsonify(data)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/project/<int:project_id>/generate-faq', methods=['POST'])
@login_required
def generate_faq(project_id):
    try:
        from report_generator import generate_faq
        conn = get_db()
        proj = conn.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
        conn.close()
        hits = search_project(project_id, 'frequently asked questions key information', n_results=10)
        if not hits:
            return jsonify({'error': 'No indexed files found'}), 400
        data = generate_faq(proj['name'], hits)
        log_activity(project_id, current_user.id, 'generated', 'FAQ generated')
        return jsonify(data)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/project/<int:project_id>/generate-flowchart', methods=['POST'])
@login_required
def generate_flowchart(project_id):
    try:
        from report_generator import generate_flowchart
        conn = get_db()
        proj = conn.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
        conn.close()
        hits = search_project(project_id, 'process steps workflow procedure sequence', n_results=10)
        if not hits:
            return jsonify({'error': 'No indexed files found'}), 400
        data = generate_flowchart(proj['name'], hits)
        log_activity(project_id, current_user.id, 'generated', 'Flowchart generated')
        return jsonify(data)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/project/<int:project_id>/generate-mindmap', methods=['POST'])
@login_required
def generate_mindmap(project_id):
    try:
        from report_generator import generate_mindmap
        conn = get_db()
        proj = conn.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
        conn.close()
        hits = search_project(project_id, 'concepts topics components relationships', n_results=10)
        if not hits:
            return jsonify({'error': 'No indexed files found'}), 400
        data = generate_mindmap(proj['name'], hits)
        log_activity(project_id, current_user.id, 'generated', 'Mind map generated')
        return jsonify(data)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/project/<int:project_id>/generate-timeline', methods=['POST'])
@login_required
def generate_timeline(project_id):
    try:
        from report_generator import generate_timeline
        conn = get_db()
        proj = conn.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
        conn.close()
        hits = search_project(project_id, 'dates timeline milestones events schedule', n_results=10)
        if not hits:
            return jsonify({'error': 'No indexed files found'}), 400
        data = generate_timeline(proj['name'], hits)
        log_activity(project_id, current_user.id, 'generated', 'Timeline generated')
        return jsonify(data)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/project/<int:project_id>/generate-briefing', methods=['POST'])
@login_required
def generate_briefing(project_id):
    try:
        from report_generator import generate_executive_briefing
        conn = get_db()
        proj = conn.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
        conn.close()
        hits = search_project(project_id, 'executive summary findings recommendations actions', n_results=10)
        if not hits:
            return jsonify({'error': 'No indexed files found'}), 400
        data = generate_executive_briefing(proj['name'], hits)
        log_activity(project_id, current_user.id, 'generated', 'Executive briefing generated')
        return jsonify(data)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/project/<int:project_id>/generate-report', methods=['POST'])
@login_required
def generate_report(project_id):
    try:
        from report_generator import generate_word_report
        conn = get_db()
        proj = conn.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
        conn.close()
        hits = search_project(project_id, 'technical report specifications architecture testing', n_results=15)
        if not hits:
            return jsonify({'error': 'No indexed files found'}), 400
        buf      = generate_word_report(proj['name'], proj['description'] or '', hits)
        filename = proj['name'].replace(' ', '_') + '_report.docx'
        log_activity(project_id, current_user.id, 'generated', f'Word report: {filename}')
        return send_file(buf, as_attachment=True, download_name=filename,
                        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/add-user', methods=['GET', 'POST'])
@login_required
def add_user():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username  = request.form.get('username', '').strip()
        password  = request.form.get('password', '')
        full_name = request.form.get('full_name', '').strip()
        role      = request.form.get('role', 'staff')
        if username and password and full_name:
            conn = get_db()
            try:
                conn.execute(
                    'INSERT INTO users (username, password, full_name, role) VALUES (?,?,?,?)',
                    (username, generate_password_hash(password), full_name, role)
                )
                conn.commit()
                flash(f'User {username} added successfully!')
            except sqlite3.IntegrityError:
                flash(f'Username {username} already exists!')
            conn.close()
    conn  = get_db()
    users = conn.execute('SELECT id, username, full_name, role FROM users').fetchall()
    conn.close()
    return render_template('admin.html', users=users)

@app.route('/admin/delete-user/<int:user_id>')
@login_required
def delete_user(user_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    conn = get_db()
    conn.execute('DELETE FROM users WHERE id=?', (user_id,))
    conn.commit()
    conn.close()
    flash('User deleted.')
    return redirect(url_for('add_user'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True, threaded=True)