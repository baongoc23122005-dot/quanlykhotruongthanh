from flask import Flask, render_template, request, redirect, jsonify, Response
import sqlite3
import csv
from io import StringIO
import datetime

app = Flask(__name__)
app.secret_key = 'he_thong_kho_demo'

def init_db():
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS Users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT, is_active INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS Tasks (
                    id INTEGER PRIMARY KEY, worker_id INTEGER, item_code TEXT, 
                    quantity INTEGER DEFAULT 1, scanned_qty INTEGER DEFAULT 0,
                    task_type TEXT DEFAULT 'Xuất', status TEXT,
                    target_slot TEXT, created_at TEXT, completed_at TEXT
                )''')
                
    # BỎ CỘT max_capacity
    c.execute('''CREATE TABLE IF NOT EXISTS Inventory (
                    id INTEGER PRIMARY KEY, item_code TEXT UNIQUE, item_name TEXT, 
                    quantity INTEGER DEFAULT 0
                )''')
                
    c.execute('''CREATE TABLE IF NOT EXISTS WarehouseMap (
                    id INTEGER PRIMARY KEY, slot_code TEXT UNIQUE, item_code TEXT,
                    zone TEXT, row_num INTEGER, shelf TEXT, pos INTEGER
                )''')
    
    c.execute("SELECT COUNT(*) FROM WarehouseMap")
    if c.fetchone()[0] == 0:
        for z in ['A', 'B', 'C', 'D']:
            for r in [1, 2]:
                for s in ['Trên', 'Dưới']:
                    for p in range(1, 11):
                        slot_code = f"{z}-{r}-{s}-{p}"
                        c.execute("INSERT INTO WarehouseMap (slot_code, zone, row_num, shelf, pos) VALUES (?, ?, ?, ?, ?)", (slot_code, z, r, s, p))
        
        try:
            c.execute("INSERT INTO Users (username, password, role, is_active) VALUES ('congnhan1', '123456', 'Worker', 1)")
            c.execute("INSERT INTO Users (username, password, role, is_active) VALUES ('quanly1', '123456', 'Manager', 1)")
            
            c.execute("INSERT INTO Inventory (item_code, item_name, quantity) VALUES ('SP-BAN-1', 'Bàn Làm Việc', 15)")
            c.execute("INSERT INTO Inventory (item_code, item_name, quantity) VALUES ('SP-GHEGO-2', 'Ghế Xoay', 5)")
            c.execute("INSERT INTO Inventory (item_code, item_name, quantity) VALUES ('SP-GHEGO-1', 'Ghế Gỗ Cao Cấp', 1)")
            
            for i in range(1, 11): c.execute(f"UPDATE WarehouseMap SET item_code='SP-BAN-1' WHERE slot_code='C-1-Trên-{i}'")
            for i in range(1, 6): c.execute(f"UPDATE WarehouseMap SET item_code='SP-BAN-1' WHERE slot_code='C-1-Dưới-{i}'")
            for i in range(1, 6): c.execute(f"UPDATE WarehouseMap SET item_code='SP-GHEGO-2' WHERE slot_code='B-2-Dưới-{i}'")
            c.execute("UPDATE WarehouseMap SET item_code='SP-GHEGO-1' WHERE slot_code='A-1-Trên-1'")
            
        except sqlite3.IntegrityError: pass 
    conn.commit()
    conn.close()

init_db()

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
            if result[1] == 0: error = "Tài khoản bị khóa!"
            else: return redirect('/scanner') if result[0] == 'Worker' else redirect('/dashboard')
        else: error = "Sai tài khoản hoặc mật khẩu!"
    return render_template('login.html', error=error)

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        worker_id = request.form['worker_id']
        item_code = request.form['item_code']
        quantity = int(request.form['quantity'])
        task_type = request.form['task_type'] 
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        c.execute("""
            INSERT INTO Tasks (worker_id, item_code, quantity, scanned_qty, task_type, target_slot, status, created_at) 
            VALUES (?, ?, ?, 0, ?, 'Tự động phân bổ', 'Pending', ?)
        """, (worker_id, item_code, quantity, task_type, now_str))
        conn.commit()
        return redirect('/dashboard')

    c.execute("SELECT status, COUNT(*) FROM Tasks GROUP BY status")
    stats = dict(c.fetchall())
    completed, pending = stats.get('Completed', 0), stats.get('Pending', 0)
    
    c.execute("SELECT id, worker_id, item_code, quantity, scanned_qty, task_type, status, created_at, completed_at, target_slot FROM Tasks ORDER BY id DESC")
    raw_tasks = c.fetchall()
    tasks = []
    for t in raw_tasks:
        duration_str = "-"
        if t[6] == 'Completed' and t[7] and t[8]:
            try:
                fmt = '%Y-%m-%d %H:%M:%S'
                diff = int((datetime.datetime.strptime(t[8], fmt) - datetime.datetime.strptime(t[7], fmt)).total_seconds())
                duration_str = f"{diff // 60} p {diff % 60} s" if diff >= 60 else f"{diff} giây"
            except: duration_str = "N/A"
        tasks.append({'id': t[0], 'worker_id': t[1], 'item_code': t[2], 'quantity': t[3], 'scanned_qty': t[4], 'task_type': t[5], 'status': t[6], 'duration': duration_str, 'slot': t[9]})

    c.execute("SELECT id, username, role, is_active FROM Users")
    users = c.fetchall()

    c.execute("SELECT id, item_code, item_name, quantity FROM Inventory ORDER BY id DESC")
    inventories = c.fetchall()

    # THỐNG KÊ SỐ LƯỢNG HÀNG TRONG TỪNG KHU VỰC
    c.execute("SELECT zone, COUNT(item_code) FROM WarehouseMap WHERE item_code IS NOT NULL GROUP BY zone")
    zone_stats = dict(c.fetchall())
    for z in ['A', 'B', 'C', 'D']:
        if z not in zone_stats: zone_stats[z] = 0

    c.execute("SELECT slot_code, item_code, zone, row_num, shelf, pos FROM WarehouseMap")
    map_raw = c.fetchall()
    map_data = {}
    for row in map_raw:
        z, r, s = row[2], row[3], row[4]
        if z not in map_data: map_data[z] = {}
        if r not in map_data[z]: map_data[z][r] = {}
        if s not in map_data[z][r]: map_data[z][r][s] = []
        map_data[z][r][s].append({'code': row[0], 'item': row[1], 'pos': row[5]})

    conn.close()
    return render_template('dashboard.html', completed=completed, pending=pending, tasks=tasks, users=users, inventories=inventories, map_data=map_data, zone_stats=zone_stats)

@app.route('/scanner')
def scanner():
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()
    c.execute('''
        SELECT t.item_code, i.item_name, t.quantity, t.scanned_qty, t.task_type 
        FROM Tasks t LEFT JOIN Inventory i ON t.item_code = i.item_code WHERE t.status='Pending' LIMIT 1
    ''')
    task = c.fetchone()
    
    expected_loc = "Chờ lệnh mới"
    if task:
        item_code, task_type = task[0], task[4]
        if task_type == 'Nhập':
            c.execute("SELECT slot_code FROM WarehouseMap WHERE item_code IS NULL ORDER BY zone, row_num, shelf, pos LIMIT 1")
        else:
            c.execute("SELECT slot_code FROM WarehouseMap WHERE item_code = ? LIMIT 1", (item_code,))
        res = c.fetchone()
        expected_loc = res[0] if res else ("KHO ĐẦY" if task_type == 'Nhập' else "LỖI KHO / THIẾU HÀNG")
    
    c.execute("SELECT item_code FROM Tasks WHERE status='Completed' ORDER BY id DESC LIMIT 3")
    history_tasks = [row[0] for row in c.fetchall()]
    conn.close()
    
    task_info = {
        'code': task[0] if task else "HẾT LỆNH", 'name': task[1] if task and task[1] else "",
        'quantity': task[2] if task else 0, 'scanned_qty': task[3] if task else 0,
        'task_type': task[4] if task else "Xuất", 'location': expected_loc
    }
    return render_template('scanner.html', task=task_info, history_tasks=history_tasks)

@app.route('/api/confirm', methods=['POST'])
def api_confirm():
    data = request.get_json()
    scanned_code = data.get('item_code')
    scanned_slot = data.get('slot_code')
    
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()
    c.execute("SELECT id, quantity, scanned_qty, task_type FROM Tasks WHERE item_code=? AND status='Pending' LIMIT 1", (scanned_code,))
    task = c.fetchone()
    
    if task:
        task_id, target_qty, current_scanned, task_type = task[0], task[1], task[2], task[3]
        new_scanned = current_scanned + 1
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if task_type == 'Xuất':
            c.execute("UPDATE Inventory SET quantity = quantity - 1 WHERE item_code=? AND quantity >= 1", (scanned_code,))
            c.execute("UPDATE WarehouseMap SET item_code = NULL WHERE slot_code=?", (scanned_slot,))
        else:
            c.execute("UPDATE Inventory SET quantity = quantity + 1 WHERE item_code=?", (scanned_code,))
            c.execute("UPDATE WarehouseMap SET item_code = ? WHERE slot_code=?", (scanned_code, scanned_slot))
            
        if new_scanned >= target_qty:
            c.execute("UPDATE Tasks SET scanned_qty=?, status='Completed', completed_at=? WHERE id=?", (new_scanned, now_str, task_id))
        else:
            c.execute("UPDATE Tasks SET scanned_qty=? WHERE id=?", (new_scanned, task_id))
            
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": f"Thành công 1 SP ({new_scanned}/{target_qty})!"})
    else:
        conn.close()
        return jsonify({"status": "error", "message": "Lỗi lệnh chờ!"})

@app.route('/reset')
def reset_db():
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS WarehouseMap")
    c.execute("DROP TABLE IF EXISTS Tasks")
    c.execute("DROP TABLE IF EXISTS Inventory")
    conn.commit()
    conn.close()
    init_db()
    return redirect('/dashboard')

@app.route('/inventory/manage', methods=['POST'])
def manage_inventory():
    item_code = request.form['item_code']
    item_name = request.form['item_name']
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO Inventory (item_code, item_name, quantity) VALUES (?, ?, 0)", (item_code, item_name))
    except sqlite3.IntegrityError:
        c.execute("UPDATE Inventory SET item_name=? WHERE item_code=?", (item_name, item_code))
    conn.commit()
    conn.close()
    return redirect('/dashboard')

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
    except sqlite3.IntegrityError: pass 
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

@app.route('/export')
def export_csv():
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()
    c.execute("SELECT id, worker_id, item_code, quantity, task_type, status, created_at, completed_at FROM Tasks ORDER BY id DESC")
    tasks = c.fetchall()
    conn.close()

    si = StringIO()
    si.write('\ufeff') 
    cw = csv.writer(si)
    cw.writerow(['ID Lệnh', 'Mã Nhân Viên', 'Mã Hàng', 'Số Lượng', 'Loại Lệnh', 'Trạng Thái', 'Thời Gian Tạo', 'Hoàn Thành'])
    
    for task in tasks:
        cw.writerow([f"#{task[0]}", f"Worker {task[1]}", task[2], task[3], task[4], task[5], task[6], task[7]])
    
    return Response(si.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=Lich_Su_Cong_Viec.csv"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
