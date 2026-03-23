import logging
from flask import (
    Flask, render_template, request, jsonify,
    session, redirect, url_for, make_response
)
import pymysql
from pymysql.cursors import DictCursor
import re
from datetime import datetime

# 配置应用
app = Flask(__name__)
app.secret_key = 'your_secure_secret_key_here'  # 生产环境需更换为安全密钥
app.config['DEBUG'] = True  # 生产环境设为False
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '834915653Wjx',
    'db': 'dbcd',
    'charset': 'utf8mb4',
    'cursorclass': DictCursor
}


# 数据库连接工具函数
def get_db_connection():
    """获取数据库连接"""
    try:
        conn = pymysql.connect(**DB_CONFIG)
        logger.info("成功连接到MySQL数据库")
        return conn
    except pymysql.MySQLError as e:
        logger.error(f"数据库连接失败: {str(e)}")
        raise


def check_student_login(username, password):
    """检查学生登录信息是否正确"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 确保表名和字段名正确无误
            sql = "SELECT * FROM stu_login_k WHERE stu_id=%s AND stu_pass=%s"
            cursor.execute(sql, (username, password))
            result = cursor.fetchone()
            return result is not None
    finally:
        conn.close()


# 定义 validate_token 函数
def validate_token(token):
    # 这里只是简单示例，实际应用中需要根据具体的身份验证机制实现
    # 假设有效的 token 为 "valid_token"
    logger.debug(f"验证Token: {token}")
    return token == "valid_token"

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
    return response

# 首页路由
@app.route('/')
@app.route('/index.html')
def index():
    """首页"""
    return render_template('index.html')

# 管理员登录路由
@app.route('/admin_login')
def admin_login():
    """管理员登录页面"""
    return render_template('admin_login.html')

# 管理员登录验证
@app.route('/check_admin', methods=['POST'])
def check_admin():
    """验证管理员登录"""
    username = request.form.get('username')
    password = request.form.get('password')

    if not all([username, password]):
        return jsonify({'success': False, 'message': '请填写完整的用户名和密码'}), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                sql = "SELECT admin_id FROM admin_login_k WHERE admin_id = %s AND admin_pass = %s"
                cursor.execute(sql, (username, password))
                result = cursor.fetchone()

                if result:
                    session['admin_id'] = username  # 设置管理员会话
                    return jsonify({'success': True})
                else:
                    logger.info(f"Admin login failed for user: {username}")
                    return jsonify({'success': False, 'message': '用户名或密码错误'}), 401

    except pymysql.MySQLError as e:
        logger.error(f"管理员登录数据库错误: {str(e)}")
        return jsonify({'success': False, 'message': '数据库连接失败'}), 500

# 学生登录路由
@app.route('/student_login')
def student_login():
    """学生登录页面"""
    return render_template('student_login.html')


@app.route('/check_student', methods=['POST'])
def check_student():
    """验证学生信息"""
    # 检查请求头中的认证信息
    auth_header = request.headers.get('Authorization')
    logger.debug(f"Authorization头: {auth_header}")
    if not auth_header or not auth_header.startswith('Bearer '):
        logger.warning("缺少有效的Authorization头")
        return jsonify({"error": "未授权访问", "code": 401}), 401

    token = auth_header.split(" ")[1]
    logger.debug(f"提取的Token: {token}")
    if not validate_token(token):
        logger.warning(f"无效Token: {token}")
        return jsonify({"error": "无效Token", "code": 401}), 401

    # 获取并验证请求体中的数据
    data = {}
    if request.is_json:
        data = request.get_json()
        logger.debug(f"从JSON获取请求数据: {data}")
    else:
        data = request.form.to_dict()
        logger.debug(f"从表单获取请求数据: {data}")

    stu_id = data.get('stu_id')
    stu_pass = data.get('stu_pass') or data.get('stu_old_pass')

    if not stu_id or not stu_pass:
        logger.warning(f"缺少必要参数: stu_id={stu_id}, stu_pass={stu_pass}")
        return jsonify({"error": "缺少必要参数", "code": 400}), 400

    # 验证学生账号和密码逻辑
    logger.info(f"验证学生: {stu_id}")
    if verify_student(stu_id, stu_pass):
        logger.info(f"学生验证成功: {stu_id}")

        session['stu_id'] = stu_id

        return jsonify({"success": True, "message": "验证成功"}), 200
    else:
        logger.warning(f"学生验证失败: {stu_id}")
        return jsonify({"error": "账号或密码错误", "code": 403}), 403

# 学生信息查看路由
@app.route('/student_view')
def student_view():
    """学生信息页面"""
    stu_id = request.args.get('studentId')

    # 验证会话和参数
    if not session.get('stu_id') or stu_id != session['stu_id']:
        return redirect(url_for('student_login'))

    if not stu_id:
        return redirect(url_for('error_page', message='缺少必要的学生ID参数'))

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 查询学生基本信息
                sql_info = """
                           SELECT stu_id, \
                                  name, \
                                  gender, \
                                  age, \
                                  birth_date, \
                                  major, \
                                  class_id
                           FROM student_info
                           WHERE stu_id = %s \
                           """
                cursor.execute(sql_info, (stu_id,))
                student_info = cursor.fetchone()

                if not student_info:
                    return redirect(url_for('error_page', message='未找到该学生信息'))

                # 查询选课信息（包含成绩和课程名称）
                sql_courses = """
                              SELECT sc.course_id, \
                                     c.course_name, \
                                     c.credit, \
                                     sc.grade, \
                                     sc.exam_date
                              FROM student_course sc
                                       JOIN course_info c ON sc.course_id = c.course_id
                              WHERE sc.stu_id = %s \
                              """
                cursor.execute(sql_courses, (stu_id,))
                courses = cursor.fetchall()

                # 处理日期格式
                if student_info.get('birth_date'):
                    student_info['birth_date'] = student_info['birth_date'].strftime('%Y-%m-%d')
                for course in courses:
                    if course.get('exam_date'):
                        course['exam_date'] = course['exam_date'].strftime('%Y-%m-%d')

                return render_template(
                    'student_view.html',
                    student=student_info,
                    courses=courses
                )

    except pymysql.MySQLError as e:
        logger.error(f"学生信息查询错误: {str(e)}")
        return redirect(url_for('error_page', message='数据库查询失败'))


# 错误处理页面
@app.route('/logout')
def logout():
    """登出操作"""
    return redirect(url_for('admin_login')), 302


# 修改函数名称，避免与API端点冲突
@app.route('/add_student', methods=['GET', 'POST'])
def add_student_page():
    """添加学生信息页面"""
    if request.method == 'POST':
        # 处理表单提交逻辑
        pass
    return render_template('add_student.html')


# 修复后的 verify_student 函数
def verify_student(stu_id, stu_pass):
    """验证学生账号和原密码"""
    conn = None
    cursor = None
    try:
        logger.debug(f"尝试验证学生: {stu_id}")
        # 使用已有的数据库连接工具函数
        conn = get_db_connection()
        cursor = conn.cursor()

        # 确保SQL查询中的字段名与数据库一致
        sql_query = "SELECT * FROM stu_login_k WHERE stu_id=%s AND stu_pass=%s"
        logger.debug(f"执行SQL查询: {sql_query}, 参数: ({stu_id}, {stu_pass})")

        cursor.execute(sql_query, (stu_id, stu_pass))
        result = cursor.fetchone()

        if result:
            logger.info(f"学生验证成功: {stu_id}")
            return True
        else:
            logger.warning(f"学生验证失败: {stu_id} - 未找到匹配记录")
            return False

    except pymysql.MySQLError as e:
        logger.error(f"学生验证数据库错误: {str(e)}")
        return False
    finally:
        # 确保资源正确关闭
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route('/edit_student', methods=['GET', 'POST'])
def edit_student():
    """编辑学生信息页面"""
    if request.method == 'POST':
        # 处理表单提交逻辑
        pass
    return render_template('edit_student.html')


@app.route('/view_reports', methods=['GET', 'POST'])
def view_reports():
    """查询学生信息页面"""
    if request.method == 'POST':
        # 处理表单提交逻辑
        pass
    return render_template('view_reports.html')


@app.route('/create_account', methods=['GET', 'POST'])
def create_account():
    """新建管理员账号页面"""
    if request.method == 'POST':
        # 处理表单提交逻辑
        pass
    return render_template('create_account.html')


@app.route('/error_page')
def error_page():
    """统一错误页面"""
    message = request.args.get('message', '服务器发生未知错误，请稍后再试')
    return make_response(f'<h1>错误提示</h1><p>{message}</p>', 400)

# 获取课程列表API
@app.route('/api/courses', methods=['GET'])
def get_courses_api():
    """获取课程列表（API接口）"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:  # 使用DictCursor以返回字典格式结果
                sql = """
                      SELECT course_id AS id,
                             course_name,
                             credit
                      FROM course_info
                      """
                cursor.execute(sql)
                courses = cursor.fetchall()
                return jsonify(courses), 200  # 明确返回状态码

    except pymysql.MySQLError as e:
        logger.error(f"数据库查询失败: {str(e)}")  # 提供更明确的错误日志
        return jsonify({"error": "无法获取课程信息，请稍后重试。"}), 500  # 返回用户友好的错误信息


@app.route('/api/students/update/<stu_id>', methods=['POST'])
def update_student(stu_id):
    data = request.json
    if not data:
        return jsonify({'success': False, 'message': '缺少更新数据'}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 更新学生基本信息
            sql = """
                  UPDATE student_info
                  SET name       = %s,
                      gender     = %s,
                      birth_date = %s,
                      major      = %s,
                      class_id   = %s
                  WHERE stu_id = %s
                  """
            cursor.execute(sql, (
                data['name'], data['gender'], data['birth_date'],
                data['major'], data['class_id'], stu_id
            ))

            # 如果有课程信息，更新课程成绩
            if 'courses' in data and len(data['courses']) > 0:
                for course in data['courses']:
                    # 检查课程是否存在
                    cursor.execute('SELECT course_id FROM course_info WHERE course_name = %s', (course['course_name'],))
                    course_record = cursor.fetchone()

                    if not course_record:
                        # 如果课程不存在，创建新课程
                        cursor.execute('INSERT INTO course_info (course_name, credit) VALUES (%s, %s)',
                                       (course['course_name'], course.get('credit', 0)))
                        course_id = cursor.lastrowid
                    else:
                        course_id = course_record['course_id']

                    # 检查学生是否已有该课程记录
                    cursor.execute('SELECT id FROM student_course WHERE stu_id = %s AND course_id = %s',
                                   (stu_id, course_id))
                    course_relation = cursor.fetchone()

                    if course_relation:
                        # 如果已有记录，更新成绩和考试日期
                        cursor.execute('''
                                       UPDATE student_course
                                       SET grade     = %s,
                                           exam_date = %s
                                       WHERE stu_id = %s
                                         AND course_id = %s
                                       ''', (course['grade'], course['exam_date'], stu_id, course_id))
                    else:
                        # 如果没有记录，插入新记录
                        cursor.execute('''
                                       INSERT INTO student_course (stu_id, course_id, grade, exam_date)
                                       VALUES (%s, %s, %s, %s)
                                       ''', (stu_id, course_id, course['grade'], course['exam_date']))

            conn.commit()
            return jsonify({'success': True, 'message': '学生信息更新成功'})

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'更新失败: {str(e)}'}), 500

    finally:
        conn.close()

@app.route('/api/students/delete/<stu_id>', methods=['DELETE'])
def delete_student(stu_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 先删除学生课程关联
            sql = "DELETE FROM student_course WHERE stu_id = %s"
            cursor.execute(sql, (stu_id,))

            # 删除登录信息
            sql = "DELETE FROM stu_login_k WHERE stu_id = %s"
            cursor.execute(sql, (stu_id,))

            # 删除学生基本信息
            sql = "DELETE FROM student_info WHERE stu_id = %s"
            cursor.execute(sql, (stu_id,))

            conn.commit()
            return jsonify({'success': True, 'message': '学生信息已删除'})

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

    finally:
        conn.close()


# 获取单个学生信息API
@app.route('/api/student/<string:stu_id>', methods=['GET'])
def get_student_api(stu_id):
    """获取单个学生信息（API接口）"""
    if not stu_id or len(stu_id) != 9:  # 假设学号为9位数字
        return jsonify({'error': '无效的学号格式'}), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 查询学生基本信息
                sql_info = """
                           SELECT stu_id   AS id,
                                  name,
                                  gender,
                                  age,
                                  birth_date,
                                  class_id AS class,
                                  major
                           FROM student_info
                           WHERE stu_id = %s \
                           """
                cursor.execute(sql_info, (stu_id,))
                student = cursor.fetchone()

                if not student:
                    return jsonify({'error': '学生不存在'}), 404

                # 查询选课信息
                sql_courses = """
                              SELECT c.course_name,
                                     c.credit,
                                     sc.grade,
                                     sc.exam_date
                              FROM student_course sc
                                       JOIN course_info c ON sc.course_id = c.course_id
                              WHERE sc.stu_id = %s \
                              """
                cursor.execute(sql_courses, (stu_id,))
                student['courses'] = cursor.fetchall()

                # 格式化日期
                if student.get('birth_date'):
                    student['birth_date'] = student['birth_date'].strftime('%Y-%m-%d')
                for course in student['courses']:
                    if course.get('exam_date'):
                        course['exam_date'] = course['exam_date'].strftime('%Y-%m-%d')
                return jsonify(student)

    except pymysql.MySQLError as e:
        logger.error(f"学生详情API错误: {str(e)}")
        return jsonify({'error': '数据库错误'}), 500


# 管理员管理页面（示例路由）
@app.route('/admin_manage')
def admin_manage():
    """管理员管理页面（需权限验证）"""
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    return render_template('admin_manage.html')

@app.route('/student_change')
def student_change():
    """学生密码修改页面"""
    student_id = request.args.get('studentId')
    if not student_id:
        return redirect(url_for('error_page', message="缺少学生ID"))

    # 渲染学生密码修改页面
    return render_template('student_change.html', student_id=student_id)

    """验证学生身份并更新密码"""
    try:
        # 获取请求数据
        data = request.get_json()
        stu_id = data.get('stu_id')
        stu_pass = data.get('stu_pass')
        new_pass = data.get('new_pass')

        # 检查参数是否完整
        if not all([stu_id, stu_pass, new_pass]):
            return jsonify({"success": False, "error": "缺少必要参数"}), 400

        # 数据库连接与查询
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 查询学生是否存在
                sql_check = """
                    SELECT stu_pass FROM student_info
                    WHERE stu_id = %s
                """
                cursor.execute(sql_check, (stu_id,))
                result = cursor.fetchone()

                if not result or result['stu_pass'] != stu_pass:
                    return jsonify({"success": False, "error": "原密码错误"}), 401

                # 更新密码
                sql_update = """
                    UPDATE student_info
                    SET stu_pass = %s
                    WHERE stu_id = %s
                """
                cursor.execute(sql_update, (new_pass, stu_id))
                conn.commit()

        return jsonify({"success": True})

    except pymysql.MySQLError as e:
        logger.error(f"密码修改接口错误: {str(e)}")
        return jsonify({"success": False, "error": "数据库操作失败"}), 500

@app.route('/update_student_password', methods=['POST'])
def update_student_password():
    """更新学生密码"""
    try:
        # 获取请求数据
        data = request.get_json()
        stu_id = data.get('stu_id')
        stu_pass = data.get('stu_pass')
        new_pass = data.get('new_pass')

        # 检查参数是否完整
        if not all([stu_id, stu_pass, new_pass]):
            return jsonify({"success": False, "error": "缺少必要参数"}), 400

        # 验证会话和参数
        if stu_id != session.get('stu_id'):
            return jsonify({"success": False, "error": "非法请求或会话不匹配"}), 403

        # 数据库连接与查询
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 查询学生是否存在
                sql_check = """
                    SELECT stu_pass FROM stu_login_k
                    WHERE stu_id = %s
                """
                cursor.execute(sql_check, (stu_id,))
                result = cursor.fetchone()

                if not result or result['stu_pass'] != stu_pass:
                    return jsonify({"success": False, "error": "原密码错误"}), 401

                # 更新密码
                sql_update = """
                    UPDATE stu_login_k
                    SET stu_pass = %s
                    WHERE stu_id = %s
                """
                cursor.execute(sql_update, (new_pass, stu_id))
                conn.commit()

        return jsonify({"success": True})

    except pymysql.MySQLError as e:
        logger.error(f"密码更新接口错误: {str(e)}")
        return jsonify({"success": False, "error": "数据库操作失败"}), 500

@app.route('/admin_change')
def admin_change():
    """管理员密码修改页面"""
    admin_id = session.get('admin_id')
    if not admin_id:
        return redirect(url_for('error_page', message="未登录或会话已过期"))

    # 渲染管理员密码修改页面
    return render_template('admin_change.html', admin_id=admin_id)


@app.route('/update_admin_password', methods=['POST'])
def update_admin_password():
    """更新管理员密码"""
    try:
        # 获取请求数据
        data = request.get_json()
        admin_id = data.get('admin_id')
        admin_pass = data.get('admin_pass')
        admin_new_pass = data.get('admin_new_pass')

        # 检查参数是否完整
        if not all([admin_id, admin_pass, admin_new_pass]):
            return jsonify({"success": False, "error": "缺少必要参数"}), 400

        # 验证会话和参数
        if admin_id != session.get('admin_id'):
            return jsonify({"success": False, "error": "非法请求或会话不匹配"}), 403

        # 数据库连接与查询
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 查询管理员是否存在
                sql_check = """
                            SELECT admin_pass 
                            FROM admin_login_k
                            WHERE admin_id = %s 
                            """
                cursor.execute(sql_check, (admin_id,))
                result = cursor.fetchone()

                if not result or result['admin_pass'] != admin_pass:
                    return jsonify({"success": False, "error": "原密码错误"}), 401

                # 更新密码
                sql_update = """
                            UPDATE admin_login_k
                            SET admin_pass = %s
                            WHERE admin_id = %s
                            """
                cursor.execute(sql_update, (admin_new_pass, admin_id))
                conn.commit()

        return jsonify({"success": True})

    except pymysql.MySQLError as e:
        logger.error(f"密码更新接口错误: {str(e)}")
        return jsonify({"success": False, "error": "数据库操作失败"}), 500

# 检查用户名是否可用
@app.route('/api/admin/check-username', methods=['GET'])
def check_username_availability():
    username = request.args.get('username')
    if not username:
        return jsonify({'available': False, 'message': '缺少用户名参数'}), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                sql = "SELECT admin_id FROM admin_login_k WHERE admin_id = %s"
                cursor.execute(sql, (username,))
                result = cursor.fetchone()
                return jsonify({'available': result is None})

    except pymysql.MySQLError as e:
        logger.error(f"检查用户名可用性时数据库错误: {str(e)}")
        return jsonify({'available': False, 'message': '数据库错误'}), 500


# 创建新管理员账号
@app.route('/api/admin/accounts', methods=['POST'])
def create_admin_account():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'success': False, 'message': '缺少必要参数'}), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 检查用户名是否已存在
                sql_check = "SELECT admin_id FROM admin_login_k WHERE admin_id = %s"
                cursor.execute(sql_check, (username,))
                result = cursor.fetchone()
                if result:
                    return jsonify({'success': False, 'message': '用户名已存在'}), 409

                # 插入新管理员账号
                sql_insert = "INSERT INTO admin_login_k (admin_id, admin_pass) VALUES (%s, %s)"
                cursor.execute(sql_insert, (username, password))
                conn.commit()

        return jsonify({'success': True, 'message': '管理员账号创建成功'})

    except pymysql.MySQLError as e:
        logger.error(f"创建管理员账号时数据库错误: {str(e)}")
        return jsonify({'success': False, 'message': '数据库错误'}), 500


@app.route('/api/students/all', methods=['GET'])
def get_all_students():
    """获取所有学生信息"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # 查询学生基本信息及课程信息
                sql_info = """
                           SELECT si.*, \
                                  sc.course_id, \
                                  sc.grade, \
                                  sc.exam_date, \
                                  ci.course_name, \
                                  ci.credit,\
                                  cl.class_name
                           FROM student_info si
                                    LEFT JOIN student_course sc ON si.stu_id = sc.stu_id
                                    LEFT JOIN course_info ci ON sc.course_id = ci.course_id
                                    LEFT JOIN class_info cl ON si.class_id = cl.class_id \
                           """
                cursor.execute(sql_info)
                results = cursor.fetchall()

                # 构建结构化数据
                students = {}
                for row in results:
                    stu_id = row['stu_id']

                    # 初始化学生信息（如果尚未初始化）
                    if stu_id not in students:
                        students[stu_id] = {
                            'stu_id': row['stu_id'],
                            'name': row['name'],
                            'gender': row['gender'],
                            'birth_date': row['birth_date'].strftime('%Y-%m-%d') if row['birth_date'] else None,
                            'major': row['major'],
                            'class_id': row['class_id'],
                            'class_name': row['class_name'],
                            'courses': []
                        }

                    # 添加课程信息（如果存在）
                    if row['course_id'] and row['course_name']:
                        students[stu_id]['courses'].append({
                            'course_id': row['course_id'],
                            'course_name': row['course_name'],
                            'credit': row['credit'],
                            'grade': row['grade'],
                            'exam_date': row['exam_date'].strftime('%Y-%m-%d') if row['exam_date'] else None
                        })

                # 按学生ID排序并返回结果
                sorted_students = sorted(students.values(), key=lambda x: x['stu_id'])

                return jsonify({'success': True, 'students': sorted_students})

    except pymysql.MySQLError as e:
        logger.error(f"获取所有学生信息错误: {str(e)}")
        return jsonify({'success': False, 'message': '数据库错误'}), 500


@app.route('/api/students/search', methods=['GET'])
def search_students():
    # 获取所有可能的搜索参数
    stu_id = request.args.get('stu_id')
    name = request.args.get('name')
    class_id = request.args.get('class_id')
    major = request.args.get('major')
    course = request.args.get('course')
    min_grade = request.args.get('min_grade')
    max_grade = request.args.get('max_grade')

    # 检查是否有任何搜索参数
    if not any([stu_id, name, class_id, major, course, min_grade, max_grade]):
        return jsonify({'success': False, 'message': '请提供至少一个查询关键词'}), 400

    conn = get_db_connection()
    try:
        conditions = []
        values = []

        if stu_id:
            conditions.append("si.stu_id = %s")
            values.append(stu_id)
        if name:
            conditions.append("si.name LIKE %s")
            values.append(f'%{name}%')
        if class_id:
            conditions.append("si.class_id = %s")
            values.append(class_id)
        if major:
            conditions.append("si.major LIKE %s")
            values.append(f'%{major}%')
        if course:
            conditions.append("ci.course_name LIKE %s")
            values.append(f'%{course}%')
        if min_grade:
            try:
                min_grade = float(min_grade)
                conditions.append("sc.grade >= %s")
                values.append(min_grade)
            except ValueError:
                return jsonify({'success': False, 'message': 'min_grade 必须是有效的数字'}), 400
        if max_grade:
            try:
                max_grade = float(max_grade)
                conditions.append("sc.grade <= %s")
                values.append(max_grade)
            except ValueError:
                return jsonify({'success': False, 'message': 'max_grade 必须是有效的数字'}), 400

        # 构建 SQL 查询语句，添加了对credit字段的选择
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""
            SELECT si.*, sc.course_id, sc.grade, sc.exam_date, ci.course_name, ci.credit
            FROM student_info si
            LEFT JOIN student_course sc ON si.stu_id = sc.stu_id
            LEFT JOIN course_info ci ON sc.course_id = ci.course_id
            WHERE {where_clause}
        """

        # 添加调试日志
        print(f"执行SQL: {sql}")
        print(f"查询参数: {values}")

        # 使用 DictCursor 直接获取字典格式的结果
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(sql, values)
            results = cursor.fetchall()

            # 添加调试日志：打印第一条结果的详细信息
            print(f"查询结果数量: {len(results)}")
            if results:
                print("第一条结果详情:")
                for key, value in results[0].items():
                    print(f"  {key}: {type(value).__name__}({value})")

            if not results:
                return jsonify({'success': False, 'message': '未找到学生信息'}), 404

            # 构建结构化数据
            students = {}
            for row in results:
                stu_id = row['stu_id']
                if stu_id not in students:
                    # 处理日期字段，确保兼容字符串和 datetime 对象
                    birth_date = row['birth_date'].strftime('%Y-%m-%d') if hasattr(row['birth_date'], 'strftime') else \
                    row['birth_date']

                    students[stu_id] = {
                        'stu_id': row['stu_id'],
                        'name': row['name'],
                        'gender': row['gender'],
                        'birth_date': birth_date,
                        'major': row['major'],
                        'class_id': row['class_id'],
                        'courses': []
                    }
                if row['course_name']:
                    # 处理课程中的日期和学分字段
                    exam_date = row['exam_date'].strftime('%Y-%m-%d') if hasattr(row['exam_date'], 'strftime') else row[
                        'exam_date']
                    credit = row['credit']  # 现在可以正确获取学分

                    students[stu_id]['courses'].append({
                        'course_name': row['course_name'],
                        'credit': credit,
                        'grade': row['grade'],
                        'exam_date': exam_date
                    })

            # 添加调试日志：打印第一个学生的详细信息
            print(f"处理后的学生数量: {len(students)}")
            if students:
                first_student_id = next(iter(students))
                first_student = students[first_student_id]
                print("学生详情:")
                print(f"  ID: {first_student['stu_id']}")
                print(f"  姓名: {first_student['name']}")
                print(f"  课程数量: {len(first_student['courses'])}")
                if first_student['courses']:
                    print("  课程详情:")
                    for i, course in enumerate(first_student['courses']):
                        print(
                            f"    课程{i + 1}: {course['course_name']}, 学分: {course['credit']}, 成绩: {course['grade']}")

            return jsonify({'success': True, 'students': list(students.values())})

    except pymysql.Error as e:
        # 数据库相关错误
        print(f"数据库错误: {str(e)}")
        return jsonify({'success': False, 'message': '数据库查询错误'}), 500
    except Exception as e:
        # 其他错误
        print(f"未知错误: {str(e)}")
        return jsonify({'success': False, 'message': '查询过程中发生未知错误'}), 500
    finally:
        conn.close()


@app.route('/api/students/add', methods=['POST'], endpoint='add_student_endpoint')
def add_student_api():
    data = request.json

    # 验证必填字段
    required_fields = ['stu_id', 'name']
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({'success': False, 'message': f'缺少必填字段: {field}'}), 400

    stu_id = data['stu_id']
    name = data['name']
    gender = data.get('gender')
    birth_date = data.get('birth_date')
    major = data.get('major')
    class_id = data.get('class_id')
    courses = data.get('courses', [])

    try:
        logger.info(f"开始添加学生: {stu_id}")

        # 验证日期格式
        if birth_date:
            try:
                datetime.strptime(birth_date, '%Y-%m-%d')
            except ValueError:
                return jsonify({'success': False, 'message': '出生日期格式应为YYYY-MM-DD'}), 400

        with get_db_connection() as conn:
            logger.info(f"已获取数据库连接: {conn}")

            with conn.cursor() as cursor:
                try:
                    # 处理班级信息
                    class_name = None
                    if class_id:
                        # 检查班级是否存在
                        cursor.execute("SELECT class_name FROM class_info WHERE class_id = %s", (class_id,))
                        result = cursor.fetchone()

                        if result:
                            class_name = result['class_name']
                            logger.info(f"找到班级ID: {class_id}, 班级名称: {class_name}")
                        else:
                            # 生成随机班级名称
                            class_name = f"{major}{random.randint(1000, 9999)}班"
                            logger.info(f"班级ID {class_id} 不存在，生成随机班级名称: {class_name}")

                            # 插入新班级信息
                            cursor.execute(
                                "INSERT INTO class_info (class_id, class_name) VALUES (%s, %s)",
                                (class_id, class_name)
                            )
                            logger.info(f"已创建新班级: {class_id} - {class_name}")
                    else:
                        logger.info("未提供班级ID")

                    # 插入学生基本信息
                    cursor.execute('''
                                   INSERT INTO student_info
                                       (stu_id, name, gender, birth_date, major, class_id)
                                   VALUES (%s, %s, %s, %s, %s, %s)
                                   ''', (stu_id, name, gender, birth_date, major, class_id))

                    logger.info(f"成功插入学生基本信息: {stu_id}")

                    # 插入登录信息
                    cursor.execute('''
                                   INSERT INTO stu_login_k (stu_id, stu_pass)
                                   VALUES (%s, %s)
                                   ''', (stu_id, '123456'))

                    logger.info(f"成功插入登录信息: {stu_id}")

                    # 处理课程信息
                    for course in courses:
                        course_name = course.get('course_name')
                        if not course_name:
                            continue

                        # 检查课程是否存在
                        cursor.execute("SELECT course_id FROM course_info WHERE course_name = %s", (course_name,))
                        result = cursor.fetchone()

                        if result:
                            course_id = result['course_id']
                            logger.info(f"找到课程: {course_name}, 课程ID: {course_id}")
                        else:
                            # 生成随机课程ID
                            course_id = f"C{random.randint(1000, 9999)}"
                            logger.info(f"课程 {course_name} 不存在，生成随机课程ID: {course_id}")

                            # 插入新课程信息
                            cursor.execute(
                                "INSERT INTO course_info (course_id, course_name) VALUES (%s, %s)",
                                (course_id, course_name)
                            )
                            logger.info(f"已创建新课程: {course_id} - {course_name}")

                        # 插入学生课程关联
                        grade = course.get('grade')
                        exam_date = course.get('exam_date')

                        # 验证成绩和考试日期
                        if grade is not None:
                            try:
                                grade = float(grade)
                                if not (0 <= grade <= 100):
                                    raise ValueError("成绩必须在0-100之间")
                            except (ValueError, TypeError):
                                return jsonify({'success': False, 'message': f"无效的成绩值: {grade}"}), 400
                        else:
                            grade = None

                        if exam_date:
                            try:
                                datetime.strptime(exam_date, '%Y-%m-%d')
                            except ValueError:
                                return jsonify({'success': False, 'message': '考试日期格式应为YYYY-MM-DD'}), 400

                        # 插入学生课程关联
                        cursor.execute('''
                                       INSERT INTO student_course (stu_id, course_id, grade, exam_date)
                                       VALUES (%s, %s, %s, %s)
                                       ''', (stu_id, course_id, grade, exam_date))

                    # 提交事务
                    conn.commit()
                    logger.info(f"学生添加成功: {stu_id}")

                    return jsonify({
                        'success': True,
                        'message': '学生信息添加成功',
                        'stu_id': stu_id
                    })

                except pymysql.Error as e:
                    # 回滚事务
                    conn.rollback()
                    logger.error(f"数据库操作失败: {str(e)}", exc_info=True)

                    # 主键冲突处理
                    if isinstance(e, pymysql.IntegrityError) and e.args[0] == 1062:
                        return jsonify({'success': False, 'message': '学号已存在'}), 400

                    # 其他数据库错误
                    return jsonify({
                        'success': False,
                        'message': f'数据库错误: {str(e)}',
                        'error_code': e.args[0] if len(e.args) > 0 else None
                    }), 500

    except Exception as e:
        logger.error(f"添加学生时发生未知错误: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': '服务器内部错误，请联系管理员',
            'error_detail': str(e)
        }), 500

if __name__ == '__main__':
    app.run(port=5000)