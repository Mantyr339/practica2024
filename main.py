import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import motor.motor_asyncio
import logging

logging.basicConfig(level=logging.INFO)

TOKEN = "7129349108:AAEUfp_nJf49l0syQ70AgU6Vm7XJ5tBBUh0"
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

cluster = motor.motor_asyncio.AsyncIOMotorClient("mongodb+srv://golenkoroma11:15568493154@cluster.mpquv97.mongodb.net/?retryWrites=true&w=majority&appName=Cluster")
db = cluster.for_bot
users_collection = db.users
schedule_collection = db.schedule
feedback_collection = db.feedback


class ScheduleStates(StatesGroup):
    setting_schedule = State()
    editing_schedule_input = State()


class FeedbackStates(StatesGroup):
    waiting_for_feedback = State()


async def add_user(user_id):
    if not await users_collection.find_one({"id": user_id}):
        await users_collection.insert_one({
            "id": user_id,
            "date": str(datetime.now().date())
        })

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

@dp.message(Command(commands=["start"]))
async def start(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Звіт за сьогодні", callback_data="today_report")]
    ])
    await message.answer(
        "Привіт! Ось команди, які ти можеш використовувати:\n"
        "/set_schedule - Встановити свій розклад на тиждень\n"
        "/view_schedule - Переглянути свій розклад\n"
        "/edit_delete - Редагувати або видалити розклад\n"
        "/help - Отримати допомогу щодо використання цього бота\n",
        reply_markup=keyboard
    )
    await add_user(message.chat.id)

@dp.message(Command(commands=["set_schedule"]))
async def set_schedule_command(message: types.Message, state: FSMContext):
    await message.answer(
        "Введи свій розклад у форматі:\n"
        "День, номер пари, предмет, початок, кінець\n"
        "Приклад:\n"
        "Понеділок, 1, Математика, 08:30, 09:50\n"
        "Понеділок, 2, Фізика, 10:10, 11:30\n"
        "Після введення кожної пари відправляй наступну. Коли закінчиш, напиши 'Готово'."
    )
    await state.set_state(ScheduleStates.setting_schedule)
    await state.update_data(schedule=[])


@dp.message(Command(commands=["help"]))
async def help_command(message: types.Message):
    await message.answer(
        "Цей бот допомагає тобі керувати своїм розкладом занять.\n"
        "Ось команди, які ти можеш використовувати:\n"
        "/set_schedule - Встановити свій розклад на тиждень. Введи пари у форматі: День, номер пари, предмет, початок, кінець. Напиши 'Готово', щоб завершити.\n"
        "/view_schedule - Переглянути поточний розклад. Бот відобразить твій розклад на кожен день.\n"
        "/today_report - Переглянути звіт з пар за сьогоднішній день.\n"
        "/edit_delete - Редагувати або видалити розклад. Використовуй цю команду, щоб редагувати або видалити певні пари.\n"
        "/help - Отримати допомогу щодо використання цього бота. Ця команда відображає пояснення до усіх існуючих функцій.\n"
        "\n"
        "Сповіщення:\n"
        "Бот надсилає сповіщення за 5 хвилин до початку кожної пари, щоб нагадати тобі про заняття."
    )


@dp.message(Command(commands=["view_schedule"]))
async def view_schedule_command(message: types.Message):
    user_id = message.chat.id
    schedules = await schedule_collection.find({"id": user_id}).to_list(None)
    if schedules:
        schedule_text = ""
        for schedule in schedules:
            day = schedule.get("day", "Невідомий день")
            schedule_text += f"\n{day}:\n"
            for cls in schedule.get("schedule", []):
                schedule_text += f"  {cls['number']}. {cls['subject']} ({cls['start']} - {cls['end']})\n"
        await message.answer(f"Твій розклад:\n{schedule_text}")
    else:
        await message.answer("Ти ще не встановив свій розклад.")


@dp.message(ScheduleStates.setting_schedule)
async def handle_schedule_input(message: types.Message, state: FSMContext):
    user_id = message.chat.id
    text = message.text.strip()
    if text.lower() == "готово":
        data = await state.get_data()
        schedule = data['schedule']
        for entry in schedule:
            await schedule_collection.update_one(
                {"id": user_id, "day": entry["day"]},
                {"$push": {"schedule": entry}},
                upsert=True
            )
        await state.clear()
        await message.answer("Розклад збережено.")
        return
    try:
        day, number, subject, start, end = map(str.strip, text.split(","))
        number = int(number)
        datetime.strptime(start, "%H:%M")  # Validate start time format
        datetime.strptime(end, "%H:%M")  # Validate end time format

        schedule_entry = {
            "day": day,
            "number": number,
            "subject": subject,
            "start": start,
            "end": end
        }

        data = await state.get_data()
        data['schedule'].append(schedule_entry)
        await state.update_data(schedule=data['schedule'])
        await message.answer(f"Пара збережена: {day}, {number}, {subject}, {start}, {end}")
    except ValueError:
        await message.answer("Невірний формат. Спробуй ще раз або напиши 'Готово' для завершення.")


@dp.message(Command(commands=["edit_delete"]))
async def edit_delete_command(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Редагувати", callback_data="edit")],
        [InlineKeyboardButton(text="Видалити", callback_data="delete")]
    ])
    await message.answer("Вибери дію:", reply_markup=keyboard)


@dp.callback_query(lambda c: c.data == "edit")
async def edit_callback(callback_query: types.CallbackQuery):
    days_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 - Понеділок", callback_data="edit_1")],
        [InlineKeyboardButton(text="2 - Вівторок", callback_data="edit_2")],
        [InlineKeyboardButton(text="3 - Середа", callback_data="edit_3")],
        [InlineKeyboardButton(text="4 - Четвер", callback_data="edit_4")],
        [InlineKeyboardButton(text="5 - П'ятниця", callback_data="edit_5")],
        [InlineKeyboardButton(text="6 - Субота", callback_data="edit_6")],
        [InlineKeyboardButton(text="7 - Неділя", callback_data="edit_7")]
    ])
    await callback_query.message.answer("Вибери день для редагування:", reply_markup=days_keyboard)
    await callback_query.answer()


@dp.callback_query(lambda c: c.data.startswith("edit_"))
async def edit_day_callback(callback_query: types.CallbackQuery, state: FSMContext):
    day_map = {
        "edit_1": "Понеділок",
        "edit_2": "Вівторок",
        "edit_3": "Середа",
        "edit_4": "Четвер",
        "edit_5": "П'ятниця",
        "edit_6": "Субота",
        "edit_7": "Неділя"
    }
    day_code = callback_query.data
    day = day_map.get(day_code)
    if day:
        user_id = callback_query.from_user.id
        schedule = await schedule_collection.find_one({"id": user_id, "day": day})
        if schedule and "schedule" in schedule:
            schedule_text = f"{day}:\n"
            for cls in schedule["schedule"]:
                schedule_text += f"  {cls['number']}. {cls['subject']} ({cls['start']} - {cls['end']})\n"
            await callback_query.message.answer(
                f"Твій розклад на {day}:\n{schedule_text}\n\nВведи нову інформацію для редагування в форматі:\nномер пари, предмет, початок, кінець")
            await state.set_state(ScheduleStates.editing_schedule_input)
            await state.update_data(user_id=user_id, day=day)
        else:
            await callback_query.message.answer(f"Розклад на {day} не знайдено.")
    await callback_query.answer()


@dp.callback_query(lambda c: c.data == "delete")
async def delete_callback(callback_query: types.CallbackQuery):
    days_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 - Понеділок", callback_data="delete_1")],
        [InlineKeyboardButton(text="2 - Вівторок", callback_data="delete_2")],
        [InlineKeyboardButton(text="3 - Середа", callback_data="delete_3")],
        [InlineKeyboardButton(text="4 - Четвер", callback_data="delete_4")],
        [InlineKeyboardButton(text="5 - П'ятниця", callback_data="delete_5")],
        [InlineKeyboardButton(text="6 - Субота", callback_data="delete_6")],
        [InlineKeyboardButton(text="7 - Неділя", callback_data="delete_7")]
    ])
    await callback_query.message.answer("Вибери день для видалення:", reply_markup=days_keyboard)
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_"))
async def delete_day_callback(callback_query: types.CallbackQuery, state: FSMContext):
    day_map = {
        "delete_1": "Понеділок",
        "delete_2": "Вівторок",
        "delete_3": "Середа",
        "delete_4": "Четвер",
        "delete_5": "П'ятниця",
        "delete_6": "Субота",
        "delete_7": "Неділя"
    }
    day_code = callback_query.data
    day = day_map.get(day_code)
    if day:
        user_id = callback_query.from_user.id
        schedule = await schedule_collection.find_one({"id": user_id, "day": day})
        if schedule and "schedule" in schedule:
            schedule_text = f"{day}:\n"
            for cls in schedule["schedule"]:
                schedule_text += f"  {cls['number']}. {cls['subject']} ({cls['start']} - {cls['end']})\n"
            await callback_query.message.answer(
                f"Твій розклад на {day}:\n{schedule_text}\n\nВведи номер пари, яку хочеш видалити."
            )
            await state.set_state(ScheduleStates.editing_schedule_input)
            await state.update_data(user_id=user_id, day=day, action="delete")
        else:
            await callback_query.message.answer(f"Розклад на {day} не знайдено.")
    await callback_query.answer()
@dp.message(ScheduleStates.editing_schedule_input)
async def handle_edit_schedule_input(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        user_id = data["user_id"]
        day = data["day"]
        action = data.get("action", "edit")
        text = message.text.strip()

        if action == "edit":
            number, subject, start, end = map(str.strip, text.split(","))
            number = int(number)
            datetime.strptime(start, "%H:%M")  # Validate start time format
            datetime.strptime(end, "%H:%M")  # Validate end time format

            schedule_entry = {
                "number": number,
                "subject": subject,
                "start": start,
                "end": end
            }

            await schedule_collection.update_one(
                {"id": user_id, "day": day, "schedule.number": number},
                {"$set": {"schedule.$": schedule_entry}}
            )
            await state.clear()
            await message.answer(f"Пара {number} на {day} оновлена.")
        elif action == "delete":
            number = int(text)
            await schedule_collection.update_one(
                {"id": user_id, "day": day},
                {"$pull": {"schedule": {"number": number}}}
            )
            await state.clear()
            await message.answer(f"Пара {number} на {day} видалена.")
    except ValueError:
        await message.answer("Невірний формат. Спробуй ще раз.")

@dp.message(ScheduleStates.editing_schedule_input)
async def handle_edit_schedule_input(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        user_id = data["user_id"]
        day = data["day"]
        text = message.text.strip()
        number, subject, start, end = map(str.strip, text.split(","))
        number = int(number)
        datetime.strptime(start, "%H:%M")  # Validate start time format
        datetime.strptime(end, "%H:%M")  # Validate end time format

        schedule_entry = {
            "number": number,
            "subject": subject,
            "start": start,
            "end": end
        }

        await schedule_collection.update_one(
            {"id": user_id, "day": day, "schedule.number": number},
            {"$set": {"schedule.$": schedule_entry}}
        )
        await state.clear()
        await message.answer(f"Пара {number} на {day} оновлена.")
    except ValueError:
        await message.answer("Невірний формат. Спробуй ще раз.")


async def send_notifications():
    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_day = now.strftime("%A")

        day_map = {
            "Monday": "Понеділок",
            "Tuesday": "Вівторок",
            "Wednesday": "Середа",
            "Thursday": "Четвер",
            "Friday": "П'ятниця",
            "Saturday": "Субота",
            "Sunday": "Неділя"
        }
        day = day_map.get(current_day, "Невідомий день")

        schedules = await schedule_collection.find({"day": day}).to_list(None)
        for schedule in schedules:
            user_id = schedule["id"]
            for cls in schedule["schedule"]:
                class_start_time = cls["start"]
                class_end_time = cls["end"]

                # Time for reminder before the class starts
                reminder_time = (datetime.strptime(class_start_time, "%H:%M") - timedelta(minutes=2)).strftime("%H:%M")
                if current_time == reminder_time:
                    await bot.send_message(user_id, f"Нагадування: {cls['subject']} починається о {cls['start']}.")

                # Time for notification when the class ends
                if current_time == class_end_time:
                    await notify_end_of_class(user_id, cls)

        await asyncio.sleep(60)


async def notify_end_of_class(user_id, cls):
    await bot.send_message(user_id, f"{cls['number']} пара ({cls['subject']}) закінчилась.")
    await request_class_feedback(user_id, cls)


async def request_class_feedback(user_id, cls):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Добре", callback_data=f"feedback_{cls['number']}_good")],
        [InlineKeyboardButton(text="Нормально", callback_data=f"feedback_{cls['number']}_ok")],
        [InlineKeyboardButton(text="Погано", callback_data=f"feedback_{cls['number']}_bad")],
        [InlineKeyboardButton(text="Не був присутній", callback_data=f"feedback_{cls['number']}_absent")]
    ])
    await bot.send_message(user_id, "Оцініть те, як пройшла пара:", reply_markup=keyboard)


@dp.callback_query(lambda c: c.data.startswith("feedback_"))
async def handle_feedback(callback_query: types.CallbackQuery):
    data = callback_query.data.split("_")
    class_number_str = data[1]
    feedback = data[2]

    # Конвертувати class_number в ціле число
    try:
        class_number = int(class_number_str)
    except ValueError:
        await bot.send_message(callback_query.from_user.id, "Помилка: номер пари повинен бути числом.")
        return

    feedback_map = {
        "good": "Добре",
        "ok": "Нормально",
        "bad": "Погано",
        "absent": "Не був присутній"
    }
    feedback_text = feedback_map.get(feedback, "Невідомо")

    await feedback_collection.insert_one({
        "user_id": callback_query.from_user.id,
        "class_number": class_number,
        "feedback": feedback_text,
        "timestamp": datetime.now()
    })

    await callback_query.message.delete_reply_markup()
    await bot.send_message(callback_query.from_user.id, f"Дякуємо за ваш відгук: {feedback_text}")


@dp.message(Command(commands=["today_report"]))
async def today_report_command(message: types.Message):
    await generate_today_report(message.chat.id)

@dp.callback_query(lambda c: c.data == "today_report")
async def today_report_callback(callback_query: types.CallbackQuery):
    await generate_today_report(callback_query.from_user.id)
    await callback_query.answer()

async def generate_today_report(user_id):
    current_day = datetime.now().strftime("%A")

    # Mapping days in English to Ukrainian
    day_map = {
        "Monday": "Понеділок",
        "Tuesday": "Вівторок",
        "Wednesday": "Середа",
        "Thursday": "Четвер",
        "Friday": "П'ятниця",
        "Saturday": "Субота",
        "Sunday": "Неділя"
    }
    day = day_map.get(current_day, "Невідомий день")

    # Retrieve schedule for the current day
    schedule = await schedule_collection.find_one({"id": user_id, "day": day})
    if schedule and "schedule" in schedule:
        report_text = f"Звіт за {day}:\n"
        for cls in schedule["schedule"]:
            class_number = cls['number']
            subject = cls['subject']
            start = cls['start']
            end = cls['end']

            # Retrieve feedback for the class
            feedback_doc = await feedback_collection.find_one({"user_id": user_id, "class_number": class_number})
            feedback_text = feedback_doc["feedback"] if feedback_doc else "Без відгуку"

            report_text += (
                f"\nПара {class_number}:\n"
                f"  Предмет: {subject}\n"
                f"  Початок: {start}\n"
                f"  Кінець: {end}\n"
                f"  Відгук: {feedback_text}\n"
            )

        await bot.send_message(user_id, report_text)
    else:
        await bot.send_message(user_id, "Сьогодні у вас немає пар.")

if __name__ == "__main__":
    async def main():
        notification_task = asyncio.create_task(send_notifications())
        await dp.start_polling(bot)
        await notification_task

    asyncio.run(main())
