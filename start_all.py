from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from datetime import datetime
import requests
from handlers.db_querry import DBQuerry
from handlers.config import GET_FAULTS, GET_INSTALL_WITH_CABLE, GET_INSTALL_WITHOUT_CABLE, GET_ADDRESSES_API, GET_EXECUTORS, CLOSE_TASK_API, TOKEN

db_querry = DBQuerry()

"""GET TASKS"""
async def get_task_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Запросить заявки", callback_data='request_applications')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите тип заявок:", reply_markup=reply_markup)

async def get_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    
    try:
        if query.data == 'request_applications':
            keyboard = [
                [InlineKeyboardButton("Неисправности", callback_data='get_faults')],
                [InlineKeyboardButton("Подключения с кабелем", callback_data='get_install_with_cable')],
                [InlineKeyboardButton("Подключения без кабеля", callback_data='get_install_without_cable')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Выберите тип заявки:", reply_markup=reply_markup)

        else:
            response = None
            if query.data == 'get_faults':
                response = requests.get(GET_FAULTS)
            elif query.data == 'get_install_with_cable':
                response = requests.get(GET_INSTALL_WITH_CABLE)
            elif query.data == 'get_install_without_cable':
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

    last_task_date_stored = db_querry.get_last_task_date(user_id, application_type)

    latest_date_current = datetime.min
    new_items = [] 

    for task_id, value in data.items():
        contract = value[0].strip() 
        original_date = value[1].strip()
        date_object = datetime.strptime(original_date, '%a, %d %b %Y %H:%M:%S %Z')
        formatted_date = date_object.strftime('%Y-%m-%d %H:%M:%S')
        items.append((task_id.strip(), contract, formatted_date, value[2].strip()))
        latest_date_current = max(latest_date_current, date_object)

        if last_task_date_stored is None or date_object > last_task_date_stored:
            new_items.append((task_id.strip(), formatted_date, value[1].strip()))

    sorted_items = sorted(items, key=lambda x: x[2])

    for task_id, contract, formatted_date, comment in sorted_items:
        is_new = any(item[0] == task_id for item in new_items)
        task_status = db_querry.get_task_status_and_assignees(task_id=task_id)
    
        if is_new:
            formatted_string = f"{contract} | {formatted_date} | {comment} | _Новое_"
        else:
            formatted_string = f"{contract} | {formatted_date} | {comment}"
        
        if task_status:
            formatted_string += f" | {task_status}"

        formatted_strings.append(formatted_string)

    db_querry.update_task_date(user_id, application_type, latest_date_current)

    return latest_date_current, '\n\n'.join(formatted_strings)

"""TAKE TASK"""
async def take_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Неисправности", callback_data='take_faults')],
        [InlineKeyboardButton("Подключения с кабелем", callback_data='take_install_with_cable')],
        [InlineKeyboardButton("Подключения без кабеля", callback_data='take_install_without_cable')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите тип заявки, которую хотите взять:", reply_markup=reply_markup)

async def take_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data in ['take_faults', 'take_install_with_cable', 'take_install_without_cable']:
        response = None
        if query.data == 'take_faults':
            response = requests.get(GET_FAULTS)
        elif query.data == 'take_install_with_cable':
            response = requests.get(GET_INSTALL_WITH_CABLE)
        elif query.data == 'take_install_without_cable':
            response = requests.get(GET_INSTALL_WITHOUT_CABLE)
        
        if response:
            try:
                data = response.json()
                context.user_data["tasks"] = data
                keyboard = [
                    [InlineKeyboardButton(f"{value[0]}", callback_data=f"take_task_{key}")]
                    for key, value in data.items()
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("Выберите заявку:", reply_markup=reply_markup)
            except ValueError:
                await query.edit_message_text("Ошибка при обработке данных с сервера.")

    elif query.data.startswith("take_task_"):
        task_id = query.data.split("_")[1]
        context.user_data["task_id"] = task_id
        task_address = context.user_data.get("tasks", {}).get(task_id, [None])[0]
        
        if task_address:
            existing_executors = db_querry.check_existing_task_in_progress(task_id)
            if existing_executors:
                await query.edit_message_text(
                    f"Заявка {task_address} уже в работе исполнителями: {', '.join(existing_executors)}."
                )
            else:
                users = db_querry.get_users()
                context.user_data["executors"] = users
                keyboard = [
                    [InlineKeyboardButton(f"{name}", callback_data=f"take_executor_{user_id}")]
                    for user_id, name in users.items()
                ]
                keyboard.append([InlineKeyboardButton("Завершить", callback_data='finish_take_selection')])
                await query.edit_message_text(f"Выберите исполнителя для заявки: {task_address}", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("Не удалось найти адрес для данной заявки.")

    elif query.data.startswith("take_executor_"):
        executor_id = query.data.split("_")[1]
        selected_executors = context.user_data.get("selected_executors", [])
        
        if executor_id not in selected_executors:
            selected_executors.append(executor_id)
            context.user_data["selected_executors"] = selected_executors

        executors = context.user_data.get("executors", {})
        executor_name = executors.get(executor_id, "Неизвестный исполнитель")
        
        keyboard = [
            [InlineKeyboardButton(f"{name}", callback_data=f"take_executor_{user_id}")]
            for user_id, name in executors.items() if user_id not in selected_executors
        ]
        keyboard.append([InlineKeyboardButton("Завершить", callback_data='finish_take_selection')])

        await query.edit_message_text(
            f"Исполнитель {executor_name} добавлен. Выберите еще исполнителя или завершите выбор.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == 'finish_take_selection':
        task_id = context.user_data.get("task_id")
        selected_executors = context.user_data.get("selected_executors", [])
        executors = context.user_data.get("executors", {})

        if selected_executors:
            executor_names = [executors.get(exec_id, "Неизвестный исполнитель") for exec_id in selected_executors]
            db_querry.update_task_status(task_id, selected_executors, "В работе")
            task_address = context.user_data.get("tasks", {}).get(task_id, [None])[0]
            await query.edit_message_text(f"Заявка {task_address} взята в работу: {', '.join(executor_names)}.")
        else:
            await query.edit_message_text("Исполнители не выбраны.")

"""CLOSE TASKS MONITORING"""
async def close_task_monitoring(update: Update, context: ContextTypes.DEFAULT_TYPE):
    groups = db_querry.get_work_groups()
    keyboard = [[InlineKeyboardButton(group[1], callback_data=f"group_{group[0]}")] for group in groups]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите группу задач:", reply_markup=reply_markup)

async def close_monitoring_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("group_"):
        group_id = int(query.data.split("_")[1])
        context.user_data["group_id"] = group_id
        work_types = db_querry.get_work_type(group_id)
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
        context.user_data["comment"] = ""

        employee_ids = db_querry.get_employee_ids()
        installer_names = db_querry.get_installer_names(employee_ids)

        keyboard = [[InlineKeyboardButton(name, callback_data=f"installer_{employee_id}")] 
                    for employee_id, name in installer_names.items()]
        
        keyboard.append([InlineKeyboardButton("Завершить", callback_data="finish_task")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите исполнителей:", reply_markup=reply_markup)

    elif query.data == "finish_task":
        group_id = context.user_data["group_id"]
        work_type_id = context.user_data["work_type_id"]
        address_id = context.user_data["address"]
        comment = context.user_data["comment"]
        selected_installers = context.user_data.get("selected_installers", [])
        selected_installers_id = db_querry.get_installers_id(selected_installers)

        task_id = db_querry.add_task(group_id, work_type_id, address_id, comment)
        db_querry.add_task_installers(task_id, selected_installers_id)
        await query.edit_message_text("Задача успешно закрыта.")

    elif query.data.startswith("installer_"):
        installer_id = int(query.data.split("_")[1])
        selected_installers = context.user_data.get("selected_installers", [])

        if installer_id not in selected_installers:
            selected_installers.append(installer_id)
            context.user_data["selected_installers"] = selected_installers

        employee_ids = db_querry.get_employee_ids()
        installer_names = db_querry.get_installer_names(employee_ids)
        
        keyboard = [[InlineKeyboardButton(name, callback_data=f"installer_{employee_id}")] 
                    for employee_id, name in installer_names.items() if employee_id not in selected_installers]

        keyboard.append([InlineKeyboardButton("Завершить", callback_data="finish_task")])

        selected_installer_names = [installer_names[installer_id] for installer_id in selected_installers]
        
        installer_names_str = ", ".join(selected_installer_names)

        await query.edit_message_text(
            f"Выбрано исполнителей: {installer_names_str}. Выберите еще исполнителя или завершите.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def close_task_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    comment = update.message.text
    context.user_data["comment"] = comment

    employee_ids = db_querry.get_employee_ids()
    installer_names = db_querry.get_installer_names(employee_ids)

    keyboard = [[InlineKeyboardButton(name, callback_data=f"installer_{employee_id}")] 
                for employee_id, name in installer_names.items()]

    keyboard.append([InlineKeyboardButton("Завершить", callback_data="finish_task")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("Выберите исполнителей:", reply_markup=reply_markup)


"""CLOSE TASKS IN BILLLING"""
async def close_task_billing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Неисправности", callback_data='closebilling_faults')],
        [InlineKeyboardButton("Подключения с кабелем", callback_data='closebilling_install_with_cable')],
        [InlineKeyboardButton("Подключения без кабеля", callback_data='closebilling_install_without_cable')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите тип заявки для закрытия:", reply_markup=reply_markup)

async def close_billing_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if query.data in ['closebilling_faults', 'closebilling_install_with_cable', 'closebilling_install_without_cable']:
        response = None
        if query.data == 'closebilling_faults':
            response = requests.get(GET_FAULTS)
        elif query.data == 'closebilling_install_with_cable':
            response = requests.get(GET_INSTALL_WITH_CABLE)
        elif query.data == 'closebilling_install_without_cable':
            response = requests.get(GET_INSTALL_WITHOUT_CABLE)
        
        if response:
            try:
                data = response.json()
                context.user_data["tasks"] = data
                keyboard = [
                    [InlineKeyboardButton(f"{value[0]}", callback_data=f"closebilling_task_{key}")]
                    for key, value in data.items()
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("Выберите заявку:", reply_markup=reply_markup)
            except ValueError:
                await query.edit_message_text("Ошибка при обработке данных с сервера.")

    elif query.data.startswith("closebilling_task_"):
        task_id = query.data.split("_")[1]
        context.user_data["task_id"] = task_id
        task_address = context.user_data.get("tasks", {}).get(task_id, [None])[0]

        if task_address:
            executors = {}
            response = requests.get(GET_EXECUTORS)
            try:
                executors = response.json() if response else {}
                if isinstance(executors, dict):
                    context.user_data["executors"] = executors
                    keyboard = [
                        [InlineKeyboardButton(f"{executor_name}", callback_data=f"closebilling_executor_{executor_id}")]
                        for executor_id, executor_name in executors.items()
                    ]
                    keyboard.append([InlineKeyboardButton("Завершить", callback_data='closebilling_finish_selection')])
                    await query.edit_message_text(f"Выберите исполнителя для заявки: {task_address}", reply_markup=InlineKeyboardMarkup(keyboard))
                else:
                    await query.edit_message_text("Ошибка при получении списка исполнителей.")
            except ValueError:
                await query.edit_message_text("Ошибка при обработке данных с сервера.")
        else:
            await query.edit_message_text("Не удалось найти адрес для данной заявки.")

    elif query.data.startswith("closebilling_executor_"):
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
            keyboard.append([InlineKeyboardButton("Завершить", callback_data='closebilling_finish_selection')])

            await query.edit_message_text(
                f"Исполнитель {executor_name} добавлен. Выберите еще исполнителя или завершите выбор.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text(
                f"Исполнитель {executor_name} уже выбран. Выберите еще или закончите выбор.",
                reply_markup=InlineKeyboardMarkup(
                    [InlineKeyboardButton(f"{executor_name}", callback_data=f"closebilling_executor_{executor_id}") 
                     for executor_id, executor_name in executors.items() if executor_id not in context.user_data["selected_executors"]] + 
                    [[InlineKeyboardButton("Закончить выбор", callback_data='finish_selection')]]
                ))

    elif query.data == 'closebilling_finish_selection':
        task_id = context.user_data.get("task_id")
        task_address = context.user_data.get("tasks", {}).get(task_id, [None])[0]
        selected_executors = context.user_data.get("selected_executors", [])
        executors = context.user_data.get("executors", {})

        if not selected_executors:
            await query.edit_message_text("Исполнитель не выбран. Заявка не будет закрыта.")
            return

        executor_names = [executors[executor_id] for executor_id in selected_executors if executor_id in executors]

        try:
            db_querry.update_task_status(task_id)
        except Exception as e:
            await query.edit_message_text(f"Ошибка при обновлении статуса заявки в базе данных: {str(e)}.")
            return
        
        response = requests.post(CLOSE_TASK_API, json={
            'task_id': task_id,
            'executor_ids': selected_executors
        })

        if response.status_code == 200:
            await query.edit_message_text(f"Заявка {task_address} закрыта: {', '.join(executor_names)}.")
        else:
            await query.edit_message_text("Ошибка при закрытии заявки. Попробуйте снова.")

if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler('get_tasks', get_task_main))
    application.add_handler(CallbackQueryHandler(get_task_handler))

    application.add_handler(CommandHandler('take_tasks', take_task))
    application.add_handler(CallbackQueryHandler(take_task_handler))

    application.add_handler(CommandHandler('close_task_monitoring', close_task_monitoring))
    application.add_handler(CallbackQueryHandler(close_monitoring_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, close_task_message_handler))

    application.add_handler(CommandHandler('close_task_billing', close_task_billing))
    application.add_handler(CallbackQueryHandler(close_billing_handler))

    application.run_polling()

