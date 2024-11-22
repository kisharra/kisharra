from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import requests
from db_querry import DBQuerry
from config import GET_FAULTS, GET_INSTALL_WITH_CABLE, GET_INSTALL_WITHOUT_CABLE


db_querry = DBQuerry()


async def take_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Неисправности", callback_data='faults')],
        [InlineKeyboardButton("Подключения с кабелем", callback_data='install_with_cable')],
        [InlineKeyboardButton("Подключения без кабеля", callback_data='install_without_cable')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите тип заявки, которую хотите взять:", reply_markup=reply_markup)

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
            existing_executors = db_querry.check_existing_task_in_progress(task_id)
            if existing_executors:
                await query.edit_message_text(
                    f"Заявка {task_address} уже в работе исполнителями: {', '.join(existing_executors)}."
                )
            else:
                users = db_querry.get_users()
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
            db_querry.update_task_status(task_id, selected_executors, "В работе")
            task_address = context.user_data.get("tasks", {}).get(task_id, [None])[0]
            await query.edit_message_text(f"Заявка {task_address} взята в работу: {', '.join(executor_names)}.")
        else:
            await query.edit_message_text("Исполнители не выбраны.")

if __name__ == '__main__':
    TOKEN = '7637338151:AAEVDMyQle_rwCEzYgudzUmuu_opxvnhjzw'
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler('take_tasks', take_task))
    application.add_handler(CallbackQueryHandler(take_task_handler))

    application.run_polling()