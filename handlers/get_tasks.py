from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime
import requests
from db_querry import DBQuerry
from config import GET_FAULTS, GET_INSTALL_WITH_CABLE, GET_INSTALL_WITHOUT_CABLE



db_querry = DBQuerry()

async def get_task_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Запросить заявки", callback_data='request_applications')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите тип заявок, которые хотите получить:", reply_markup=reply_markup)

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

if __name__ == '__main__':
    TOKEN = '7637338151:AAEVDMyQle_rwCEzYgudzUmuu_opxvnhjzw'
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler('get_tasks', get_task_main))
    application.add_handler(CallbackQueryHandler(get_task_handler))

    application.run_polling()