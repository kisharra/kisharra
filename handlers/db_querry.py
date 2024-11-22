import sqlite3
import mysql.connector
from datetime import datetime
from handlers.config import DB_NAME, DB_INSTALLERS, DB_SATMES


class DBQuerry:
    def __init__(self):
        self.db_installers = mysql.connector.connect(**DB_INSTALLERS)
        self.db_satmes = mysql.connector.connect(**DB_SATMES)
        self.cursor_installers = self.db_installers.cursor()
        self.cursor_satmes = self.db_satmes.cursor()
        self.tg_bot_db = sqlite3.connect(DB_NAME)

    """GET TASKS"""
    
    def get_last_task_date(self, user_id, task_type):
        conn = self.tg_bot_db
        cursor = conn.cursor()
        cursor.execute('SELECT last_task_date FROM register_last_task_dt WHERE user_id = ? AND task_type = ?', (user_id, task_type))
        result = cursor.fetchone()
        conn.close()
        return datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S') if result else None

    
    def update_task_date(self, user_id, task_type, last_task_date):
        conn = self.tg_bot_db
        cursor = conn.cursor()
        cursor.execute(''' 
            INSERT INTO register_last_task_dt (user_id, last_task_date, task_type) 
            VALUES (?, ?, ?) 
            ON CONFLICT(user_id, task_type) DO UPDATE SET last_task_date = ? 
        ''', (user_id, last_task_date.strftime('%Y-%m-%d %H:%M:%S'), task_type, last_task_date.strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()

    
    def get_task_status_and_assignees(self, task_id):
        """Получает статус и имена исполнителей для указанной заявки из базы данных."""
        conn = self.tg_bot_db
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT u.name FROM user_task_status uts
                JOIN users_name u ON uts.user_id = u.id
                WHERE uts.task_id = ? AND uts.status = "В работе"
            ''', (task_id,))
            
            assignees = [row[0] for row in cursor.fetchall()]
            
            return "В работе: " + ", ".join(assignees) if assignees else None
        
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return None
        
        finally:
            conn.close()

    """TAKE TASKS"""
    
    def get_users(self):
        conn = self.tg_bot_db
        cursor = conn.cursor()
        cursor.execute('SELECT id, name FROM users_name')
        users = {str(user_id): name for user_id, name in cursor.fetchall()}  # Преобразуем ключи в строки
        conn.close()
        return users
    
    
    def update_task_status(self, task_id, user_ids, status):
        """Обновляем статус заявки в базе данных для выбранных исполнителей."""
        conn = self.tg_bot_db
        cursor = conn.cursor()
        for user_id in user_ids:
            cursor.execute(''' 
                INSERT INTO user_task_status (task_id, user_id, status, take_date) 
                VALUES (?, ?, ?, ?)
            ''', (task_id, user_id, status, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()

    
    def check_existing_task_in_progress(self, task_id):
        """Проверяем, существует ли заявка с данным task_id и статусом 'В работе'. Возвращает список исполнителей, если заявка найдена."""
        conn = self.tg_bot_db
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.name 
            FROM user_task_status AS uts
            JOIN users_name AS u ON uts.user_id = u.id
            WHERE uts.task_id = ? AND uts.status = "В работе"
        ''', (task_id,))
        executors = [row[0] for row in cursor.fetchall()]
        conn.close()
        return executors
    
    """CLOSE TASKS BILLING"""
    
    def update_task_status(self, task_id):
        """Обновляем статус заявки в базе данных для выбранных исполнителей."""
        conn = self.tg_bot_db
        cursor = conn.cursor()
        cursor.execute('UPDATE user_task_status SET close_date = ? WHERE task_id = ?', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), task_id))
        conn.commit()
        conn.close()

    """CLOSE TASK MONITORING"""
    
    def get_work_groups(self):
        conn = self.cursor_installers
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM work_group")
        groups = cursor.fetchall()
        conn.close()
        return groups
    
    
    def get_work_type(self, workgroup_id):
        conn = self.cursor_installers
        cursor = conn.cursor()
        cursor.execute("""SELECT wt.id, wt.name AS work_type_name
                        FROM work_type wt
                        JOIN work_group_type wgt ON wt.id = wgt.w_type_id
                        JOIN work_group wg ON wgt.w_group_id = wg.id
                        WHERE wg.id = %s""", (workgroup_id,))
        types = cursor.fetchall()
        conn.close()
        return types

    def get_employee_ids(self):
        conn = self.cursor_installers
        cursor = conn.cursor()
        cursor.execute("SELECT id, employee_id FROM installer WHERE status = 0")
        installers = cursor.fetchall()
        conn.close()
        employee_ids = [installer[1] for installer in installers]
        return employee_ids
    
    def get_installers_id(self, employee_ids):
        conn = self.cursor_installers
        cursor = conn.cursor()
        cursor.execute("SELECT id, employee_id FROM installer WHERE status = 0" + " AND employee_id IN (%s)" % ','.join(['%s'] * len(employee_ids)), tuple(employee_ids))
        installers = cursor.fetchall()
        conn.close()
        return [installer[0] for installer in installers]  # Получаем только id

        # Получение имен исполнителей по employee_ids
    def get_installer_names(self, employee_ids):    
        conn = self.cursor_satmes
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM sm_contracts WHERE id IN (%s)" % ','.join(['%s'] * len(employee_ids)), tuple(employee_ids))
        result = cursor.fetchall()
        conn.close()
        return {employee_id: name for employee_id, name in result}

       # Добавление заявки в базу данных
    def add_task(self, workgroup_id, work_type, address, comment, creator_uid=65):
        conn = self.cursor_satmes
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            "INSERT INTO task (work_group, work_type, task_address, task_comment, task_date, task_status, creator_uid, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (workgroup_id, work_type, address, comment, now, 0, creator_uid, now, now)
        )
        task_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return task_id

     # Связывание исполнителей с заявкой
    def add_task_installers(self, task_id, installer_ids):
        conn = self.cursor_installers
        cursor = conn.cursor()
        cursor.executemany(
            "INSERT INTO task_installer (task_id, installer_id) VALUES (%s, %s)",
            [(task_id, installer_id) for installer_id in installer_ids]
        )
        conn.commit()
        conn.close()

    
    def get_work_type_id(self, work_type_name):
        conn = self.cursor_satmes
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM work_type WHERE name = %s", (work_type_name,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
if __name__ == '__main__':
    pass