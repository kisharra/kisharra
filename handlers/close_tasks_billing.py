from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from config import TOKEN, GET_FAULTS, GET_INSTALL_WITH_CABLE, GET_INSTALL_WITHOUT_CABLE, GET_EXECUTORS, CLOSE_TASK_API
import requests
from db_querry import DBQuerry

db_querry = DBQuerry()

async def close_task_billing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Неисправности", callback_data='faults')],
        [InlineKeyboardButton("Подключения с кабелем", callback_data='install_with_cable')],
        [InlineKeyboardButton("Подключения без кабеля", callback_data='install_without_cable')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите тип заявки для закрытия:", reply_markup=reply_markup)


async def close_billing_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    TOKEN = '7637338151:AAEVDMyQle_rwCEzYgudzUmuu_opxvnhjzw'
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler('close_task_billing', close_task_billing))
    application.add_handler(CallbackQueryHandler(close_billing_handler))

    application.run_polling()