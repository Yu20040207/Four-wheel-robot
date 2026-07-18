"""Flask-Login 集成、登录路由与管理后台 Blueprint"""
import configparser
import os
from functools import wraps
from typing import Optional

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from auth_db import AuthDatabase

auth_bp = Blueprint('auth', __name__)
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

login_manager = LoginManager()
auth_db: Optional[AuthDatabase] = None


class User(UserMixin):
    def __init__(self, row: dict):
        self.id = row['id']
        self.username = row['username']
        self.password_hash = row['password_hash']
        self.role = row['role']
        self.is_active_account = bool(row.get('is_active', 1))

    @property
    def is_active(self):
        return self.is_active_account

    @property
    def is_admin(self):
        return self.role == 'admin'


def load_auth_config(base_dir: str) -> dict:
    config = configparser.ConfigParser()
    config_path = os.path.join(base_dir, 'config.ini')
    defaults = {
        'secret_key': 'dev-change-me-please',
        'admin_username': 'admin',
        'admin_password': 'admin123',
    }
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8-sig') as f:
            config.read_file(f)
        if 'auth' in config:
            cfg = config['auth']
            defaults['secret_key'] = cfg.get('secret_key', defaults['secret_key'])
            defaults['admin_username'] = cfg.get('admin_username', defaults['admin_username'])
            defaults['admin_password'] = cfg.get('admin_password', defaults['admin_password'])
    return defaults


def init_auth(app, base_dir: str) -> AuthDatabase:
    global auth_db
    auth_db = AuthDatabase(base_dir)
    cfg = load_auth_config(base_dir)

    app.config['SECRET_KEY'] = cfg['secret_key']

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '请先登录'

    @login_manager.user_loader
    def load_user(user_id: str):
        row = auth_db.get_user_by_id(int(user_id))
        if row and row.get('is_active', 1):
            return User(row)
        return None

    if auth_db.count_users() == 0:
        admin_user = cfg['admin_username']
        admin_pass = cfg['admin_password']
        auth_db.create_user(
            admin_user,
            generate_password_hash(admin_pass),
            role='admin',
        )
        print(f'🔐 已创建默认管理员: {admin_user} / {admin_pass}')
        print('   请尽快在 config.ini [auth] 中修改密码并重启')

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    return auth_db


def is_public_path(path: str) -> bool:
    if path.startswith('/static/'):
        return True
    return path in ('/login', '/admin/login', '/favicon.ico')


def check_request_auth():
    """before_request 鉴权；返回 Response 或 None"""
    path = request.path
    if is_public_path(path):
        return None

    if path.startswith('/admin'):
        if path == '/admin/login':
            return None
        if not current_user.is_authenticated:
            return redirect(url_for('admin.login', next=path))
        if not current_user.is_admin:
            abort(403)
        return None

    if not current_user.is_authenticated:
        if path.startswith('/api/'):
            return jsonify({'status': 'error', 'message': '未登录，请先登录'}), 401
        return redirect(url_for('auth.login', next=path))

    return None


def user_can_access_robot(robot_id: str) -> bool:
    if not robot_id:
        return False
    if not current_user.is_authenticated:
        return False
    if current_user.is_admin:
        return auth_db.get_robot(robot_id) is not None
    return auth_db.user_owns_robot(current_user.id, robot_id)


def get_selected_robot_id() -> Optional[str]:
    return session.get('selected_robot_id')


ROBOT_ONLINE_EXEMPT_PATHS = frozenset({
    '/api/reload_faces',
})


def require_robot_for_control():
    """控制类 API 需已选机器人；账户下有机器人但未选时一律拦截"""
    robot_id = get_selected_robot_id()
    if robot_id:
        if not user_can_access_robot(robot_id):
            return jsonify({'status': 'error', 'message': '无权控制该机器人'}), 403
        if request.path not in ROBOT_ONLINE_EXEMPT_PATHS:
            from robot_context import is_robot_online
            if not is_robot_online(robot_id):
                return jsonify({
                    'status': 'error',
                    'message': '机器人未连接，请确认设备已开机并联网',
                }), 503
        return None

    if current_user.is_admin:
        robots = auth_db.list_robots()
    else:
        robots = auth_db.list_robots_for_user(current_user.id)

    if robots:
        return jsonify({
            'status': 'error',
            'message': '请先在顶部选择要控制的机器人',
        }), 400
    return None


def is_robot_control_api(path: str, method: str) -> bool:
    """是否属于需要选中机器人的控制类 API"""
    exempt = {
        '/api/human_tracking/status',
        '/api/human_tracking/history',
        '/api/robots/my',
        '/api/robots/select',
        '/api/stats',
        '/api/flask_status',
        '/api/collection_status',
    }
    if path in exempt:
        return False
    if path.startswith('/admin/'):
        return False

    control_prefixes = (
        '/api/human_tracking/',
        '/api/garbage_pickup/',
        '/api/face_tracking/',
        '/api/face_recognition/',
    )
    control_exact = {
        '/api/refresh_stream',
        '/api/reload_faces',
        '/api/send_recognition_result',
        '/api/save_rubbish_photo',
        '/api/camera/open',
        '/api/camera/close',
        '/api/add_face',
        '/api/cancel_collection',
        '/api/trigger_face_collection',
    }
    if path in control_exact:
        return True
    return any(path.startswith(p) for p in control_prefixes)


def admin_required_json(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({'status': 'error', 'message': '需要管理员权限'}), 403
        return f(*args, **kwargs)
    return wrapped


# ---------- 客户登录 ----------

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin and request.args.get('next', '').startswith('/admin'):
            return redirect(request.args.get('next') or url_for('admin.dashboard'))
        return redirect(url_for('index'))

    error = None
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        row = auth_db.get_user_by_username(username)
        if row and row.get('is_active', 1) and check_password_hash(row['password_hash'], password):
            if row['role'] == 'admin':
                error = '管理员请使用管理后台入口登录'
            else:
                session.clear()
                login_user(User(row), remember=bool(request.form.get('remember')))
                next_url = request.args.get('next') or url_for('index')
                if next_url.startswith('/admin'):
                    next_url = url_for('index')
                return redirect(next_url)
        else:
            error = '用户名或密码错误'

    return render_template('login.html', error=error)


@auth_bp.route('/logout')
def logout():
    logout_user()
    session.pop('selected_robot_id', None)
    return redirect(url_for('auth.login'))


@auth_bp.route('/api/robots/my')
def api_my_robots():
    if current_user.is_admin:
        robots = auth_db.list_robots()
        for r in robots:
            r.setdefault('bound_at', None)
    else:
        robots = auth_db.list_robots_for_user(current_user.id)
    selected = get_selected_robot_id()
    return jsonify({
        'status': 'success',
        'robots': robots,
        'selected_robot_id': selected,
    })


@auth_bp.route('/api/robots/select', methods=['POST'])
def api_select_robot():
    data = request.get_json(silent=True) or {}
    robot_id = (data.get('robot_id') or '').strip()
    if not robot_id:
        session.pop('selected_robot_id', None)
        return jsonify({'status': 'success', 'message': '已取消选择', 'selected_robot_id': None})
    if not user_can_access_robot(robot_id):
        return jsonify({'status': 'error', 'message': '无权选择该机器人'}), 403
    session['selected_robot_id'] = robot_id
    robot = auth_db.get_robot(robot_id)
    return jsonify({
        'status': 'success',
        'message': f"已选择: {robot['display_name']}",
        'selected_robot_id': robot_id,
        'display_name': robot['display_name'],
    })


# ---------- 管理后台登录 ----------

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('admin.dashboard'))

    error = None
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        row = auth_db.get_user_by_username(username)
        if (
            row
            and row.get('is_active', 1)
            and row['role'] == 'admin'
            and check_password_hash(row['password_hash'], password)
        ):
            session.clear()
            login_user(User(row), remember=bool(request.form.get('remember')))
            return redirect(request.args.get('next') or url_for('admin.dashboard'))
        error = '管理员账号或密码错误'

    return render_template('admin/login.html', error=error)


@admin_bp.route('/logout')
def logout():
    logout_user()
    session.pop('selected_robot_id', None)
    return redirect(url_for('admin.login'))


@admin_bp.route('/')
def dashboard():
    users = auth_db.list_users()
    robots = auth_db.list_robots()
    bindings = auth_db.list_bindings()
    return render_template(
        'admin/dashboard.html',
        user_count=len(users),
        robot_count=len(robots),
        binding_count=len(bindings),
        users=users,
        robots=robots,
        bindings=bindings,
    )


@admin_bp.route('/users')
def users_page():
    return render_template('admin/users.html', users=auth_db.list_users())


@admin_bp.route('/robots')
def robots_page():
    return render_template('admin/robots.html', robots=auth_db.list_robots())


@admin_bp.route('/bindings')
def bindings_page():
    return render_template(
        'admin/bindings.html',
        users=auth_db.list_users(),
        robots=auth_db.list_robots(),
        bindings=auth_db.list_bindings(),
    )


# ---------- 管理 API ----------

@admin_bp.route('/api/users', methods=['GET', 'POST'])
@admin_required_json
def api_users():
    if request.method == 'GET':
        return jsonify({'status': 'success', 'users': auth_db.list_users()})

    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return jsonify({'status': 'error', 'message': '用户名和密码不能为空'}), 400
    if auth_db.get_user_by_username(username):
        return jsonify({'status': 'error', 'message': '用户名已存在'}), 400
    user = auth_db.create_user(username, generate_password_hash(password), role='user')
    return jsonify({'status': 'success', 'message': '用户已创建', 'user': {
        'id': user['id'], 'username': user['username'], 'role': user['role'],
    }})


@admin_bp.route('/api/users/<int:user_id>/toggle', methods=['POST'])
@admin_required_json
def api_toggle_user(user_id):
    user = auth_db.get_user_by_id(user_id)
    if not user:
        return jsonify({'status': 'error', 'message': '用户不存在'}), 404
    if user['role'] == 'admin':
        return jsonify({'status': 'error', 'message': '不能禁用管理员'}), 400
    new_active = not bool(user.get('is_active', 1))
    auth_db.set_user_active(user_id, new_active)
    return jsonify({
        'status': 'success',
        'message': '已启用' if new_active else '已禁用',
        'is_active': new_active,
    })


@admin_bp.route('/api/users/<int:user_id>/reset_password', methods=['POST'])
@admin_required_json
def api_reset_password(user_id):
    data = request.get_json(silent=True) or {}
    password = data.get('password') or ''
    if len(password) < 4:
        return jsonify({'status': 'error', 'message': '密码至少 4 位'}), 400
    if not auth_db.get_user_by_id(user_id):
        return jsonify({'status': 'error', 'message': '用户不存在'}), 404
    auth_db.update_password(user_id, generate_password_hash(password))
    return jsonify({'status': 'success', 'message': '密码已重置'})


@admin_bp.route('/api/users/<int:user_id>', methods=['PUT'])
@admin_required_json
def api_update_user(user_id):
    user = auth_db.get_user_by_id(user_id)
    if not user:
        return jsonify({'status': 'error', 'message': '用户不存在'}), 404

    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    role = (data.get('role') or user['role']).strip()
    is_active = bool(data.get('is_active', True))
    password = data.get('password') or ''

    if not username:
        return jsonify({'status': 'error', 'message': '用户名不能为空'}), 400
    if role not in ('user', 'admin'):
        return jsonify({'status': 'error', 'message': '角色无效'}), 400

    existing = auth_db.get_user_by_username(username)
    if existing and existing['id'] != user_id:
        return jsonify({'status': 'error', 'message': '用户名已存在'}), 400

    if user['role'] == 'admin' and (role != 'admin' or not is_active):
        admins = [u for u in auth_db.list_users() if u['role'] == 'admin' and u['is_active']]
        if len(admins) <= 1:
            return jsonify({'status': 'error', 'message': '不能禁用或降级最后一个管理员'}), 400

    password_hash = None
    if password:
        if len(password) < 4:
            return jsonify({'status': 'error', 'message': '密码至少 4 位'}), 400
        password_hash = generate_password_hash(password)

    if not auth_db.update_user(user_id, username, role, is_active, password_hash):
        return jsonify({'status': 'error', 'message': '更新失败'}), 500
    return jsonify({'status': 'success', 'message': '用户已更新'})


@admin_bp.route('/api/robots', methods=['GET', 'POST'])
@admin_required_json
def api_robots():
    if request.method == 'GET':
        return jsonify({'status': 'success', 'robots': auth_db.list_robots()})

    data = request.get_json(silent=True) or {}
    robot_id = (data.get('robot_id') or '').strip()
    display_name = (data.get('display_name') or '').strip()
    notes = (data.get('notes') or '').strip()
    if not robot_id or not display_name:
        return jsonify({'status': 'error', 'message': 'robot_id 和名称不能为空'}), 400
    if auth_db.get_robot(robot_id):
        return jsonify({'status': 'error', 'message': 'robot_id 已存在'}), 400
    robot = auth_db.create_robot(robot_id, display_name, notes)
    return jsonify({'status': 'success', 'message': '机器人已添加', 'robot': robot})


@admin_bp.route('/api/robots/<robot_id>', methods=['PUT'])
@admin_required_json
def api_update_robot(robot_id):
    if not auth_db.get_robot(robot_id):
        return jsonify({'status': 'error', 'message': '机器人不存在'}), 404

    data = request.get_json(silent=True) or {}
    display_name = (data.get('display_name') or '').strip()
    notes = (data.get('notes') or '').strip()
    if not display_name:
        return jsonify({'status': 'error', 'message': '显示名称不能为空'}), 400
    if not auth_db.update_robot(robot_id, display_name, notes):
        return jsonify({'status': 'error', 'message': '更新失败'}), 500
    return jsonify({'status': 'success', 'message': '机器人已更新'})


@admin_bp.route('/api/robots/<robot_id>', methods=['DELETE'])
@admin_required_json
def api_delete_robot(robot_id):
    if not auth_db.delete_robot(robot_id):
        return jsonify({'status': 'error', 'message': '机器人不存在'}), 404
    return jsonify({'status': 'success', 'message': '已删除'})


@admin_bp.route('/api/bindings', methods=['GET', 'POST'])
@admin_required_json
def api_bindings():
    if request.method == 'GET':
        return jsonify({'status': 'success', 'bindings': auth_db.list_bindings()})

    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    robot_id = (data.get('robot_id') or '').strip()
    if not user_id or not robot_id:
        return jsonify({'status': 'error', 'message': '请选择用户和机器人'}), 400
    if not auth_db.get_user_by_id(int(user_id)):
        return jsonify({'status': 'error', 'message': '用户不存在'}), 404
    if not auth_db.bind_robot(int(user_id), robot_id):
        return jsonify({'status': 'error', 'message': '机器人不存在'}), 404
    return jsonify({'status': 'success', 'message': '绑定成功'})


@admin_bp.route('/api/bindings/<int:user_id>/<robot_id>', methods=['PUT'])
@admin_required_json
def api_update_binding(user_id, robot_id):
    data = request.get_json(silent=True) or {}
    new_user_id = data.get('user_id')
    new_robot_id = (data.get('robot_id') or '').strip()
    if not new_user_id or not new_robot_id:
        return jsonify({'status': 'error', 'message': '请选择用户和机器人'}), 400
    if not auth_db.update_binding(user_id, robot_id, int(new_user_id), new_robot_id):
        return jsonify({'status': 'error', 'message': '绑定不存在或目标无效'}), 404
    return jsonify({'status': 'success', 'message': '绑定已更新'})


@admin_bp.route('/api/bindings/<int:user_id>/<robot_id>', methods=['DELETE'])
@admin_required_json
def api_unbind(user_id, robot_id):
    if not auth_db.unbind_robot(user_id, robot_id):
        return jsonify({'status': 'error', 'message': '绑定不存在'}), 404
    return jsonify({'status': 'success', 'message': '已解绑'})
