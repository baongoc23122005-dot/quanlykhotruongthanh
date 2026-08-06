from flask import Flask, render_template, request, redirect, jsonify, Response
import sqlite3
import csv
from io import StringIO

app = Flask(__name__)
app.secret_key = 'he_thong_kho_demo'

# ==========================================
# 1. KHỞI TẠO CƠ SỞ DỮ LIỆU
# ==========================================
def init_db():
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()
    
    # 1. Tạo các bảng với cấu trúc mới nhất (Hỗ trợ kiểm tra tồn tại để không bị mất dữ liệu bảng)
    c.execute('''CREATE TABLE IF NOT EXISTS Users (
                    id INTEGER PRIMARY KEY, 
                    username TEXT UNIQUE, 
                    password TEXT, 
                    role TEXT, 
                    is_active INTEGER DEFAULT 1
                )''')
                
    # [CẬP NHẬT]: Thêm quantity (số lượng cần quét), scanned_qty (đã quét), task_type (Xuất/Nhập)
    c.execute('''CREATE TABLE IF NOT EXISTS Tasks (
                    id INTEGER PRIMARY KEY, 
                    worker_id INTEGER, 
                    item_code TEXT, 
                    quantity INTEGER DEFAULT 1,
                    scanned_qty INTEGER DEFAULT 0,
                    task_type TEXT DEFAULT 'Xuất',
                    status TEXT
                )''')
                
    c.execute('''CREATE TABLE IF NOT EXISTS Inventory (
                    id INTEGER PRIMARY KEY, 
                    item_code TEXT UNIQUE, 
                    item_name TEXT, 
                    quantity INTEGER, 
                    location TEXT
                )''')
    
    # Kiểm tra xem bảng Users đã có dữ liệu chưa, nếu chưa thì thêm dữ liệu mẫu
    c.execute("SELECT COUNT(*) FROM Users")
    count = c.fetchone()[0]
    
    if count == 0:
        try:
            c.execute("INSERT INTO Users (username, password, role, is_active) VALUES ('congnhan1', '123456', 'Worker', 1)")
            c.execute("INSERT INTO Users (username, password, role, is_active) VALUES ('quanly1', '123456', 'Manager', 1)")
            
            # Lệnh mẫu mặc định (Xuất 5 cái ghế gỗ)
            c.execute("INSERT INTO Tasks (worker_id, item_code, quantity, scanned_qty, task_type, status) VALUES (1, 'SP-GHEGO-1', 5, 0, 'Xuất', 'Pending')")
            
            # Dữ liệu mẫu Inventory
            c.execute("INSERT INTO Inventory (item_code, item_name, quantity, location) VALUES ('SP-GHEGO-1', 'Ghế Gỗ Cao Cấp', 50, 'Khu A - Kệ 01')")
            c.execute("INSERT INTO Inventory (item_code, item_name, quantity, location) VALUES ('SP-GHEGO-2', 'Ghế Xoay', 30, 'Khu B - Kệ 03')")
            c.execute("INSERT INTO Inventory (item_code, item_name, quantity, location) VALUES ('SP-BAN-1', 'Bàn Làm Việc', 10, 'Khu C - Kệ 02')")
        except sqlite3.IntegrityError:
            pass 
        
    conn.commit()
    conn.close()

# Gọi init_db ngay khi app khởi động để đảm bảo luôn có cơ sở dữ liệu trên Render
init_db()

# ==========================================
# 2. ROUTING & ĐIỀU HƯỚNG
# ==========================================
@app.route('/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('warehouse.db')
        c = conn.cursor()
        c.execute("SELECT role, is_active FROM Users WHERE username=? AND password=?", (username, password))
        result = c.fetchone()
        conn.close()
        
        if result:
            role = result[0]
            is_active = result[1]
            if is_active == 0:
                error = "Tài khoản của bạn đã bị vô hiệu hóa!"
            else:
                if role == 'Worker':
                    return redirect('/scanner')
                elif role == 'Manager':
                    return redirect('/dashboard')
        else:
            error = "Sai tài khoản hoặc mật khẩu!"
            
    return render_template('login.html', error=error)

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if request.method == 'POST':
        worker_id = request.form['worker_id']
        item_code = request.form['item_code']
        quantity = int(request.form['quantity'])
        task_type = request.form['task_type'] # 'Xuất' hoặc 'Nhập'
        
        conn = sqlite3.connect('warehouse.db')
        c = conn.cursor()
        c.execute("""
            INSERT INTO Tasks (worker_id, item_code, quantity, scanned_qty, task_type, status) 
            VALUES (?, ?, ?, 0, ?, 'Pending')
        """, (worker_id, item_code, quantity, task_type))
        conn.commit()
        conn.close()
        
        return redirect('/dashboard')

    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()

    c.execute("SELECT status, COUNT(*) FROM Tasks GROUP BY status")
    stats = dict(c.fetchall())
    completed = stats.get('Completed', 0)
    pending = stats.get('Pending', 0)
    
    # Lấy danh sách nhiệm vụ đầy đủ thông tin
    c.execute("SELECT id, worker_id, item_code, quantity, scanned_qty, task_type, status FROM Tasks ORDER BY id DESC")
    tasks = c.fetchall()

    c.execute("SELECT id, username, role, is_active FROM Users")
    users = c.fetchall()

    c.execute("SELECT id, item_code, item_name, quantity, location FROM Inventory ORDER BY id DESC")
    inventories = c.fetchall()

    # Tính toán dữ liệu Heatmap
    c.execute("SELECT substr(location, 1, 5) as zone, SUM(quantity) FROM Inventory WHERE location IS NOT NULL GROUP BY zone")
    heatmap_data = dict(c.fetchall())

    conn.close()

    return render_template('dashboard.html', completed=completed, pending=pending, tasks=tasks, users=users, inventories=inventories, heatmap_data=heatmap_data)

@app.route('/scanner')
def scanner():
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()
    
    # Lấy lệnh Pending kèm theo số lượng cần quét và đã quét
    c.execute('''
        SELECT t.item_code, i.location, i.item_name, t.quantity, t.scanned_qty, t.task_type 
        FROM Tasks t 
        LEFT JOIN Inventory i ON t.item_code = i.item_code 
        WHERE t.status='Pending' LIMIT 1
    ''')
    task = c.fetchone()
    
    c.execute("SELECT item_code FROM Tasks WHERE status='Completed' ORDER BY id DESC LIMIT 3")
    history_tasks = [row[0] for row in c.fetchall()]
    
    conn.close()
    
    task_info = {
        'code': task[0] if task else "HẾT LỆNH",
        'location': task[1] if task and task[1] else "Chờ lệnh mới",
        'name': task[2] if task and task[2] else "",
        'quantity': task[3] if task else 0,
        'scanned_qty': task[4] if task else 0,
        'task_type': task[5] if task else "Xuất"
    }
    
    return render_template('scanner.html', task=task_info, history_tasks=history_tasks)

@app.route('/api/confirm', methods=['POST'])
def api_confirm():
    data = request.get_json()
    scanned_code = data.get('item_code')
    
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()
    
    # Lấy thông tin lệnh hiện tại của mã này
    c.execute("SELECT id, quantity, scanned_qty, task_type FROM Tasks WHERE item_code=? AND status='Pending' LIMIT 1", (scanned_code,))
    task = c.fetchone()
    
    if task:
        task_id, target_qty, current_scanned, task_type = task[0], task[1], task[2], task[3]
        new_scanned = current_scanned + 1
        
        if new_scanned >= target_qty:
            # Đã quét đủ số lượng -> Hoàn thành lệnh
            c.execute("UPDATE Tasks SET scanned_qty=?, status='Completed' WHERE id=?", (new_scanned, task_id))
            
            # Cập nhật kho (Xuất thì trừ số lượng, Nhập thì cộng số lượng)
            if task_type == 'Xuất':
                c.execute("UPDATE Inventory SET quantity = quantity - ? WHERE item_code=? AND quantity >= ?", (target_qty, scanned_code, target_qty))
            else:
                c.execute("UPDATE Inventory SET quantity = quantity + ? WHERE item_code=?", (target_qty, scanned_code))
        else:
            # Chưa đủ số lượng -> Chỉ cập nhật số lượng đã quét tăng lên 1
            c.execute("UPDATE Tasks SET scanned_qty=? WHERE id=?", (new_scanned, task_id))
            
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": f"Quét thành công ({new_scanned}/{target_qty})!"})
    else:
        conn.close()
        return jsonify({"status": "error", "message": "Mã không khớp với lệnh đang chờ!"})

@app.route('/reset')
def reset_db():
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS Tasks")
    conn.commit()
    conn.close()
    init_db()
    return redirect('/dashboard')

# ==========================================
# 3. CÁC TÍNH NĂNG PHỤ TRỢ
# ==========================================

@app.route('/admin/add_user', methods=['POST'])
def add_user():
    username = request.form['username']
    password = request.form['password']
    role = request.form['role']
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO Users (username, password, role, is_active) VALUES (?, ?, ?, 1)", (username, password, role))
        conn.commit()
    except sqlite3.IntegrityError:
        pass 
    conn.close()
    return redirect('/dashboard')

@app.route('/admin/toggle_user/<int:user_id>')
def toggle_user(user_id):
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()
    c.execute("UPDATE Users SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return redirect('/dashboard')

@app.route('/inventory/manage', methods=['POST'])
def manage_inventory():
    item_code = request.form['item_code']
    item_name = request.form['item_name']
    quantity = request.form['quantity']
    location = request.form.get('location', 'Chưa xếp kho') 
    
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO Inventory (item_code, item_name, quantity, location) VALUES (?, ?, ?, ?)", (item_code, item_name, quantity, location))
    except sqlite3.IntegrityError:
        c.execute("UPDATE Inventory SET item_name=?, quantity=?, location=? WHERE item_code=?", (item_name, quantity, location, item_code))
    conn.commit()
    conn.close()
    return redirect('/dashboard')

@app.route('/export')
def export_csv():
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()
    c.execute("SELECT id, worker_id, item_code, quantity, task_type, status FROM Tasks ORDER BY id DESC")
    tasks = c.fetchall()
    conn.close()

    si = StringIO()
    si.write('\ufeff') 
    cw = csv.writer(si)
    cw.writerow(['ID Lệnh', 'Mã Nhân Viên', 'Mã Hàng', 'Số Lượng', 'Loại Lệnh', 'Trạng Thái'])
    
    for task in tasks:
        cw.writerow([f"#{task[0]}", f"Worker {task[1]}", task[2], task[3], task[4], task[5]])
    
    return Response(
        si.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=Lich_Su_Cong_Viec.csv"}
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
