from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import requests
import sqlite3
import mysql.connector
from datetime import datetime

GET_FAULTS = 'http://192.168.80.138:5000/api/faults'
GET_INSTALL_WITH_CABLE = 'http://192.168.80.138:5000/api/install_with_cable'
GET_INSTALL_WITHOUT_CABLE = 'http://192.168.80.138:5000/api/install_without_cable'
GET_EXECUTORS = 'http://192.168.80.138:5000/api/executors'
CLOSE_TASK_API = 'http://192.168.80.138:5000/api/close_task'
GET_ADDRESSES_API = 'http://192.168.80.138:5000/api/addresses'

DB_INSTALLERS = {
    'host': 'localhost',
    'user': 'root',
    'password': 'kisharra',
    'database': 'installerstasks'
}
DB_SATMES = {
    'host': 'localhost',
    'user': 'root',
    'password': 'kisharra',
    'database': 'satmes'
}

DB_NAME = 'tg_bot.db'


"""GET TASKS FROM DB"""

def get_last_task_date(user_id, task_type):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT last_task_date FROM register_last_task_dt WHERE user_id = ? AND task_type = ?', (user_id, task_type))
    result = cursor.fetchone()
    conn.close()
    return datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S') if result else None

def update_task_date(user_id, task_type, last_task_date):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(''' 
        INSERT INTO register_last_task_dt (user_id, last_task_date, task_type) 
        VALUES (?, ?, ?) 
        ON CONFLICT(user_id, task_type) DO UPDATE SET last_task_date = ? 
    ''', (user_id, last_task_date.strftime('%Y-%m-%d %H:%M:%S'), task_type, last_task_date.strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

def get_task_status_and_assignees(task_id):
    """Получает статус и имена исполнителей для указанной заявки из базы данных."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT u.name FROM user_task_status uts
            JOIN users_name u ON uts.user_id = u.id
            WHERE uts.task_id = ? AND uts.status = "В работе"
        ''', (task_id,))
        
        # Получаем всех исполнителей в работе
        assignees = [row[0] for row in cursor.fetchall()]
        
        # Отладочный вывод
        
        return "В работе: " + ", ".join(assignees) if assignees else None
    
    except sqlite3.Error as e:
        print(f"Database error: {e}")  # Логирование ошибок базы данных
        return None
    
    finally:
        conn.close()

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Запросить заявки", callback_data='request_applications')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите тип заявки:", reply_markup=reply_markup)

async def get_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    
    try:
        if query.data == 'request_applications':
            keyboard = [
                [InlineKeyboardButton("Неисправности", callback_data='faults')],
                [InlineKeyboardButton("Подключения с кабелем", callback_data='install_with_cable')],
                [InlineKeyboardButton("Подключения без кабеля", callback_data='install_without_cable')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Выберите тип заявки:", reply_markup=reply_markup)

        else:
            response = None
            if query.data == 'faults':
                response = requests.get(GET_FAULTS)
            elif query.data == 'install_with_cable':
                response = requests.get(GET_INSTALL_WITH_CABLE)
            elif query.data == 'install_without_cable':
                response = requests.get(GET_INSTALL_WITHOUT_CABLE)
            
            if response.status_code != 200:
                await query.edit_message_text("Не удалось загрузить список заявок")
                return
            
            data = response.json()
            if not data:
                await query.edit_message_text("Список заявок пуст")
                return

            formatted_data = get_task_data(data, user_id, query.data)
            await query.edit_message_text(formatted_data[1], parse_mode='Markdown')

    except Exception as e:
        print(f"Error handling the query: {e}")
        await query.edit_message_text("Ошибка работы бота")

def get_task_data(data, user_id, application_type):
    formatted_strings = []
    items = []

    last_task_date_stored = get_last_task_date(user_id, application_type)

    latest_date_current = datetime.min
    new_items = [] 

    for task_id, value in data.items():
        contract = value[0].strip()  # Договор
        original_date = value[1].strip()
        date_object = datetime.strptime(original_date, '%a, %d %b %Y %H:%M:%S %Z')
        formatted_date = date_object.strftime('%Y-%m-%d %H:%M:%S')
        items.append((task_id.strip(), contract, formatted_date, value[2].strip()))  # Добавляем task_id
        latest_date_current = max(latest_date_current, date_object)

        if last_task_date_stored is None or date_object > last_task_date_stored:
            new_items.append((task_id.strip(), formatted_date, value[1].strip()))

    sorted_items = sorted(items, key=lambda x: x[2])  # Сортируем по дате

    for task_id, contract, formatted_date, comment in sorted_items:
        is_new = any(item[0] == task_id for item in new_items)
        task_status = get_task_status_and_assignees(task_id=task_id)  # Проверяем статус по task_id
        
        # Формируем строку для вывода
        if is_new:
            formatted_string = f"{contract} | {formatted_date} | {comment} | _Новое_"
        else:
            formatted_string = f"{contract} | {formatted_date} | {comment}"
        
        if task_status:
            formatted_string += f" | {task_status}"

        formatted_strings.append(formatted_string)

    update_task_date(user_id, application_type, latest_date_current)

    return latest_date_current, '\n\n'.join(formatted_strings)

"""TAKE TASKS"""

def get_users():
    """Получаем список пользователей из базы данных и возвращаем как словарь."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM users_name')
    users = {str(user_id): name for user_id, name in cursor.fetchall()}  # Преобразуем ключи в строки
    conn.close()
    return users

def update_task_status(task_id, user_ids, status):
    """Обновляем статус заявки в базе данных для выбранных исполнителей."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    for user_id in user_ids:
        cursor.execute(''' 
            INSERT INTO user_task_status (task_id, user_id, status, take_date) 
            VALUES (?, ?, ?, ?)
        ''', (task_id, user_id, status, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

def check_existing_task_in_progress(task_id):
    """Проверяем, существует ли заявка с данным task_id и статусом 'В работе'. Возвращает список исполнителей, если заявка найдена."""
    conn = sqlite3.connect(DB_NAME)
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

async def take_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Неисправности", callback_data='faults')],
        [InlineKeyboardButton("Подключения с кабелем", callback_data='install_with_cable')],
        [InlineKeyboardButton("Подключения без кабеля", callback_data='install_without_cable')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите тип заявки:", reply_markup=reply_markup)

async def take_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data in ['faults', 'install_with_cable', 'install_without_cable']:
        response = None
        if query.data == 'faults':
            response = requests.get(GET_FAULTS)
        elif query.data == 'install_with_cable':
            response = requests.get(GET_INSTALL_WITH_CABLE)
        elif query.data == 'install_without_cable':
            response = requests.get(GET_INSTALL_WITHOUT_CABLE)
        
        if response:
            try:
                data = response.json()
                context.user_data["tasks"] = data
                keyboard = [
                    [InlineKeyboardButton(f"{value[0]}", callback_data=f"task_{key}")]
                    for key, value in data.items()
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("Выберите заявку:", reply_markup=reply_markup)
            except ValueError:
                await query.edit_message_text("Ошибка при обработке данных с сервера.")

    elif query.data.startswith("task_"):
        task_id = query.data.split("_")[1]
        context.user_data["task_id"] = task_id
        task_address = context.user_data.get("tasks", {}).get(task_id, [None])[0]
        
        if task_address:
            existing_executors = check_existing_task_in_progress(task_id)
            if existing_executors:
                await query.edit_message_text(
                    f"Заявка {task_address} уже в работе исполнителями: {', '.join(existing_executors)}."
                )
            else:
                users = get_users()
                context.user_data["executors"] = users
                keyboard = [
                    [InlineKeyboardButton(f"{name}", callback_data=f"executor_{user_id}")]
                    for user_id, name in users.items()
                ]
                keyboard.append([InlineKeyboardButton("Завершить", callback_data='finish_selection')])
                await query.edit_message_text(f"Выберите исполнителя для заявки: {task_address}", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("Не удалось найти адрес для данной заявки.")

    elif query.data.startswith("executor_"):
        executor_id = query.data.split("_")[1]
        selected_executors = context.user_data.get("selected_executors", [])
        
        if executor_id not in selected_executors:
            selected_executors.append(executor_id)
            context.user_data["selected_executors"] = selected_executors

        executors = context.user_data.get("executors", {})
        executor_name = executors.get(executor_id, "Неизвестный исполнитель")
        
        keyboard = [
            [InlineKeyboardButton(f"{name}", callback_data=f"executor_{user_id}")]
            for user_id, name in executors.items() if user_id not in selected_executors
        ]
        keyboard.append([InlineKeyboardButton("Завершить", callback_data='finish_selection')])

        await query.edit_message_text(
            f"Исполнитель {executor_name} добавлен. Выберите еще исполнителя или завершите выбор.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == 'finish_selection':
        task_id = context.user_data.get("task_id")
        selected_executors = context.user_data.get("selected_executors", [])
        executors = context.user_data.get("executors", {})

        if selected_executors:
            executor_names = [executors.get(exec_id, "Неизвестный исполнитель") for exec_id in selected_executors]
            update_task_status(task_id, selected_executors, "В работе")
            task_address = context.user_data.get("tasks", {}).get(task_id, [None])[0]
            await query.edit_message_text(f"Заявка {task_address} взята в работу: {', '.join(executor_names)}.")
        else:
            await query.edit_message_text("Исполнители не выбраны.")

"""CLOSE_TASKS_BILLING"""

def update_task_status(task_id):
    """Обновляем статус заявки в базе данных для выбранных исполнителей."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE user_task_status SET close_date = ? WHERE task_id = ?', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), task_id))
    conn.commit()
    conn.close()

async def close_task_billing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Неисправности", callback_data='faults')],
        [InlineKeyboardButton("Подключения с кабелем", callback_data='install_with_cable')],
        [InlineKeyboardButton("Подключения без кабеля", callback_data='install_without_cable')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите тип заявки для закрытия:", reply_markup=reply_markup)


async def billing_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if query.data in ['faults', 'install_with_cable', 'install_without_cable']:
        response = None
        if query.data == 'faults':
            response = requests.get(GET_FAULTS)
        elif query.data == 'install_with_cable':
            response = requests.get(GET_INSTALL_WITH_CABLE)
        elif query.data == 'install_without_cable':
            response = requests.get(GET_INSTALL_WITHOUT_CABLE)
        
        if response:
            try:
                data = response.json()
                context.user_data["tasks"] = data
                keyboard = [
                    [InlineKeyboardButton(f"{value[0]}", callback_data=f"task_{key}")]
                    for key, value in data.items()
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("Выберите заявку:", reply_markup=reply_markup)
            except ValueError:
                await query.edit_message_text("Ошибка при обработке данных с сервера.")

    elif query.data.startswith("task_"):
        task_id = query.data.split("_")[1]
        context.user_data["task_id"] = task_id
        task_address = context.user_data.get("tasks", {}).get(task_id, [None])[0]

        if task_address:
            # Определяем executors как пустой словарь перед блоком try
            executors = {}
            response = requests.get(GET_EXECUTORS)
            try:
                executors = response.json() if response else {}
                if isinstance(executors, dict):
                    context.user_data["executors"] = executors
                    keyboard = [
                        [InlineKeyboardButton(f"{executor_name}", callback_data=f"executor_{executor_id}")]
                        for executor_id, executor_name in executors.items()
                    ]
                    keyboard.append([InlineKeyboardButton("Завершить", callback_data='finish_selection')])
                    await query.edit_message_text(f"Выберите исполнителя для заявки: {task_address}", reply_markup=InlineKeyboardMarkup(keyboard))
                else:
                    await query.edit_message_text("Ошибка при получении списка исполнителей.")
            except ValueError:
                await query.edit_message_text("Ошибка при обработке данных с сервера.")
        else:
            await query.edit_message_text("Не удалось найти адрес для данной заявки.")

    elif query.data.startswith("executor_"):
        executor_id = query.data.split("_")[1]
        task_id = context.user_data.get("task_id")
        executors = context.user_data.get("executors", {})
        executor_name = executors.get(executor_id)
        if executor_id not in context.user_data.get("selected_executors", []):
            selected_executors = context.user_data.get("selected_executors", [])
            selected_executors.append(executor_id)
            context.user_data["selected_executors"] = selected_executors
            
            keyboard = [
                [InlineKeyboardButton(f"{executor_name}", callback_data=f"executor_{executor_id}") 
                 for executor_id, executor_name in executors.items() if executor_id not in selected_executors]
            ]
            keyboard.append([InlineKeyboardButton("Завершить", callback_data='finish_selection')])

            await query.edit_message_text(
                f"Исполнитель {executor_name} добавлен. Выберите еще исполнителя или завершите выбор.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text(
                f"Исполнитель {executor_name} уже выбран. Выберите еще или закончите выбор.",
                reply_markup=InlineKeyboardMarkup(
                    [InlineKeyboardButton(f"{executor_name}", callback_data=f"executor_{executor_id}") 
                     for executor_id, executor_name in executors.items() if executor_id not in context.user_data["selected_executors"]] + 
                    [[InlineKeyboardButton("Закончить выбор", callback_data='finish_selection')]]
                ))

    elif query.data == 'finish_selection':
        task_id = context.user_data.get("task_id")
        task_address = context.user_data.get("tasks", {}).get(task_id, [None])[0]
        selected_executors = context.user_data.get("selected_executors", [])
        executors = context.user_data.get("executors", {})  # Загружаем исполнителей из user_data

        if not selected_executors:
            await query.edit_message_text("Исполнитель не выбран. Заявка не будет закрыта.")
            return

        # Генерация имен исполнителей для вывода
        executor_names = [executors[executor_id] for executor_id in selected_executors if executor_id in executors]
        
        response = requests.post(CLOSE_TASK_API, json={
            'task_id': task_id,
            'executor_ids': selected_executors
        })

        update_task_status(task_id)

        if response.status_code == 200:
            await query.edit_message_text(f"Заявка {task_address} закрыта: {', '.join(executor_names)}.")
        else:
            await query.edit_message_text("Ошибка при закрытии заявки. Попробуйте снова.")

"""CLOSE_TASK_MONITORING"""

def connect_installers_db():
    return mysql.connector.connect(**DB_INSTALLERS)

def connect_satmes_db():
    return mysql.connector.connect(**DB_SATMES)

# Получение групп задач из базы данных
def get_work_groups():
    conn = connect_installers_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM work_group")
    groups = cursor.fetchall()
    conn.close()
    return groups

def get_work_type(workgroup_id):
    conn = connect_installers_db()
    cursor = conn.cursor()
    cursor.execute("""SELECT wt.id, wt.name AS work_type_name
                    FROM work_type wt
                    JOIN work_group_type wgt ON wt.id = wgt.w_type_id
                    JOIN work_group wg ON wgt.w_group_id = wg.id
                    WHERE wg.id = %s""", (workgroup_id,))
    types = cursor.fetchall()
    conn.close()
    return types

def get_employee_ids():
    conn = connect_installers_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, employee_id FROM installer WHERE status = 0")
    installers = cursor.fetchall()
    conn.close()
    employee_ids = [installer[1] for installer in installers]
    return employee_ids

def get_installers_id(employee_ids):
    conn = connect_installers_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, employee_id FROM installer WHERE status = 0" + " AND employee_id IN (%s)" % ','.join(['%s'] * len(employee_ids)), tuple(employee_ids))
    installers = cursor.fetchall()
    conn.close()
    return [installer[0] for installer in installers]  # Получаем только id

# Получение имен исполнителей по employee_ids
def get_installer_names(employee_ids):    
    conn = connect_satmes_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM sm_contracts WHERE id IN (%s)" % ','.join(['%s'] * len(employee_ids)), tuple(employee_ids))
    result = cursor.fetchall()
    conn.close()
    return {employee_id: name for employee_id, name in result}

# Добавление заявки в базу данных
def add_task(workgroup_id, work_type, address, comment, creator_uid=65):
    conn = connect_installers_db()
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
def add_task_installers(task_id, installer_ids):
    conn = connect_installers_db()
    cursor = conn.cursor()
    cursor.executemany(
        "INSERT INTO task_installer (task_id, installer_id) VALUES (%s, %s)",
        [(task_id, installer_id) for installer_id in installer_ids]
    )
    conn.commit()
    conn.close()

def get_work_type_id(work_type_name):
    conn = connect_installers_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM work_type WHERE name = %s", (work_type_name,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

# Команда для начала работы
async def close_task_monitoring(update: Update, context: ContextTypes.DEFAULT_TYPE):
    groups = get_work_groups()
    keyboard = [[InlineKeyboardButton(group[1], callback_data=f"group_{group[0]}")] for group in groups]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите группу задач:", reply_markup=reply_markup)

# Обработка кнопок
async def monitoring_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("group_"):
        group_id = int(query.data.split("_")[1])
        context.user_data["group_id"] = group_id
        work_types = get_work_type(group_id)
        keyboard = [[InlineKeyboardButton(work_type[1], callback_data=f"type_{work_type[0]}")] for work_type in work_types]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите тип задач:", reply_markup=reply_markup)

    elif query.data.startswith("type_"):
        work_type_id = int(query.data.split("_")[1])
        context.user_data["work_type_id"] = work_type_id
        response = requests.get(GET_ADDRESSES_API)
        addresses = response.json() if response.status_code == 200 else {}
        keyboard = [[InlineKeyboardButton(value, callback_data=f"address_{key}")] for key, value in addresses.items()]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите адрес задачи:", reply_markup=reply_markup)

    elif query.data.startswith("address_"):
        address = query.data.split("_")[1]
        context.user_data["address"] = address
        keyboard = [
            [InlineKeyboardButton("Добавить комментарий", callback_data="add_comment")],
            [InlineKeyboardButton("Далее", callback_data="skip_comment")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Введите комментарий к задаче или пропустите:", reply_markup=reply_markup)

    elif query.data == "add_comment":
        await query.edit_message_text("Введите комментарий к задаче:")

    elif query.data == "skip_comment":
        context.user_data["comment"] = ""  # Пустой комментарий

        # Переход к выбору исполнителей без автоматического выбора всех
        employee_ids = get_employee_ids()  # Получаем employee_id
        installer_names = get_installer_names(employee_ids)  # Получаем имена исполнителей

        # Формируем кнопки с именами
        keyboard = [[InlineKeyboardButton(name, callback_data=f"installer_{employee_id}")] 
                    for employee_id, name in installer_names.items()]

        # Добавляем кнопку "Завершить"
        keyboard.append([InlineKeyboardButton("Завершить", callback_data="finish_task")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите исполнителей:", reply_markup=reply_markup)

    elif query.data == "finish_task":
        group_id = context.user_data["group_id"]
        work_type_id = context.user_data["work_type_id"]
        address_id = context.user_data["address"]
        comment = context.user_data["comment"]
        selected_installers = context.user_data.get("selected_installers", [])
        selected_installers_id = get_installers_id(selected_installers)

        task_id = add_task(group_id, work_type_id, address_id, comment)
        add_task_installers(task_id, selected_installers_id)  # Добавляем выбранных исполнителей по их id
        await query.edit_message_text("Задача успешно закрыта.")

    elif query.data.startswith("installer_"):
        installer_id = int(query.data.split("_")[1])
        selected_installers = context.user_data.get("selected_installers", [])

        # Если исполнитель еще не выбран, добавляем его в список
        if installer_id not in selected_installers:
            selected_installers.append(installer_id)
            context.user_data["selected_installers"] = selected_installers

        # Получаем employee_id для отображения имен
        employee_ids = get_employee_ids()
        installer_names = get_installer_names(employee_ids)  # Получаем имена исполнителей
        
        # Формируем кнопки для выбора оставшихся исполнителей
        keyboard = [[InlineKeyboardButton(name, callback_data=f"installer_{employee_id}")] 
                    for employee_id, name in installer_names.items() if employee_id not in selected_installers]

        # Добавляем кнопку "Завершить"
        keyboard.append([InlineKeyboardButton("Завершить", callback_data="finish_task")])

        # Преобразуем выбранные ID в имена
        selected_installer_names = [installer_names[installer_id] for installer_id in selected_installers]
        
        # Формируем строку с именами выбранных исполнителей
        installer_names_str = ", ".join(selected_installer_names)

        await query.edit_message_text(
            f"Выбрано исполнителей: {installer_names_str}. Выберите еще исполнителя или завершите.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# Обработка текстовых сообщений для комментариев
async def monitoring_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    comment = update.message.text
    context.user_data["comment"] = comment

    # Получаем исполнителей с именами для выбора
    employee_ids = get_employee_ids()  # Получаем employee_id
    installer_names = get_installer_names(employee_ids)  # Получаем имена исполнителей

    # Формируем кнопки с именами
    keyboard = [[InlineKeyboardButton(name, callback_data=f"installer_{employee_id}")] 
                for employee_id, name in installer_names.items()]

    keyboard.append([InlineKeyboardButton("Завершить", callback_data="finish_task")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("Выберите исполнителей:", reply_markup=reply_markup)


if __name__ == '__main__':
    TOKEN = '7637338151:AAEVDMyQle_rwCEzYgudzUmuu_opxvnhjzw'
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler('get_tasks', welcome))
    application.add_handler(CallbackQueryHandler(get_task_handler))
    application.add_handler(CommandHandler('take_tasks', take_task))
    application.add_handler(CallbackQueryHandler(take_task_handler))
    application.add_handler(CommandHandler('close_task_billing', close_task_billing))
    application.add_handler(CallbackQueryHandler(billing_button_handler))
    application.add_handler(CommandHandler('close_task_monitoring', close_task_monitoring))
    application.add_handler(CallbackQueryHandler(monitoring_button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, monitoring_message_handler))
    
    application.run_polling()