from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from db_querry import DBQuerry
import requests
from config import GET_ADDRESSES_API


db_querry = DBQuerry()

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

if __name__ == '__main__':
    TOKEN = '7637338151:AAEVDMyQle_rwCEzYgudzUmuu_opxvnhjzw'
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler('close_task_monitoring', close_task_monitoring))
    application.add_handler(CallbackQueryHandler(close_monitoring_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, close_task_message_handler))

    application.run_polling()
