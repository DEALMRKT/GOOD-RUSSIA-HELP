import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "520362766"))
DB_PATH = os.getenv("DB_PATH", "applications.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add it to Render environment variables.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("good-russia-help")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

APPLICATIONS = {
    "admin": ("🛡 Администратор", [
        ("Ваше имя / как к вам обращаться?", "name"),
        ("Сколько вам лет?", "age"),
        ("Был ли у вас опыт администрирования? Расскажите.", "experience"),
        ("Почему хотите стать администратором?", "motivation"),
        ("Сколько времени готовы уделять проекту?", "schedule"),
    ]),
    "helper": ("🤝 Хелпер", [
        ("Ваше имя / как к вам обращаться?", "name"),
        ("Сколько вам лет?", "age"),
        ("Есть ли опыт помощи игрокам или работы с жалобами?", "experience"),
        ("Почему хотите стать хелпером?", "motivation"),
        ("Сколько времени обычно бываете онлайн?", "schedule"),
    ]),
    "media": ("🎥 Медиа-партнёр", [
        ("Ваше имя / как к вам обращаться?", "name"),
        ("Сколько вам лет?", "age"),
        ("Ссылка на ваш канал / площадку:", "channel"),
        ("Расскажите о вашей аудитории и активности.", "audience"),
        ("Какой формат сотрудничества предлагаете?", "motivation"),
    ]),
}

class ApplicationForm(StatesGroup):
    answering = State()

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                kind TEXT NOT NULL,
                answers TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
        """)

def main_keyboard(is_admin=False):
    rows = [
        [KeyboardButton(text="🛡 Подать заявку на админа")],
        [KeyboardButton(text="🤝 Подать заявку на хелпера")],
        [KeyboardButton(text="🎥 Подать заявку на медиа-партнёра")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="⚙️ Панель администратора")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Заявки", callback_data="admin:list")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin:refresh")],
    ])

def application_actions(app_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"app:approve:{app_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"app:reject:{app_id}"),
        ]
    ])

def get_pending():
    with db() as conn:
        return conn.execute(
            "SELECT id, user_id, username, kind, answers, created_at FROM applications WHERE status='pending' ORDER BY id DESC"
        ).fetchall()

def get_application(app_id):
    with db() as conn:
        return conn.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()

def set_status(app_id, status):
    with db() as conn:
        cur = conn.execute(
            "UPDATE applications SET status=? WHERE id=? AND status='pending'",
            (status, app_id)
        )
        return cur.rowcount > 0

def safe(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    is_admin = message.from_user.id == ADMIN_ID
    text = (
        "🐻 <b>GOOD RUSSIA HELP</b>\n\n"
        "Добро пожаловать! Здесь вы можете подать заявку в команду проекта.\n\n"
        "Выберите направление в меню ниже:"
    )
    await message.answer(text, reply_markup=main_keyboard(is_admin), parse_mode="HTML")

@dp.message(Command("cancel"))
@dp.message(F.text == "↩️ Отмена")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Заявка отменена. Вы можете начать заново в меню.", reply_markup=main_keyboard(message.from_user.id == ADMIN_ID))

async def begin_application(message: Message, state: FSMContext, kind: str):
    title, questions = APPLICATIONS[kind]
    await state.set_state(ApplicationForm.answering)
    await state.update_data(kind=kind, title=title, questions=questions, index=0, answers={})
    await message.answer(
        f"📝 <b>Заявка: {title}</b>\n\nОтветьте на вопросы по очереди. "
        "После отправки заявка поступит администрации.\n\n"
        f"<b>Вопрос 1/{len(questions)}.</b>\n{questions[0][0]}",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="↩️ Отмена")]],
            resize_keyboard=True
        )
    )

@dp.message(F.text == "🛡 Подать заявку на админа")
async def apply_admin(message: Message, state: FSMContext):
    await begin_application(message, state, "admin")

@dp.message(F.text == "🤝 Подать заявку на хелпера")
async def apply_helper(message: Message, state: FSMContext):
    await begin_application(message, state, "helper")

@dp.message(F.text == "🎥 Подать заявку на медиа-партнёра")
async def apply_media(message: Message, state: FSMContext):
    await begin_application(message, state, "media")

@dp.message(F.text == "⚙️ Панель администратора")
async def admin_panel_button(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("⚙️ <b>Панель администратора GOOD RUSSIA HELP</b>", reply_markup=admin_keyboard(), parse_mode="HTML")

@dp.message(Command("admin"))
async def admin_panel_command(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет доступа к панели.")
        return
    await message.answer("⚙️ <b>Панель администратора GOOD RUSSIA HELP</b>", reply_markup=admin_keyboard(), parse_mode="HTML")

@dp.message(ApplicationForm.answering)
async def collect_answer(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, отправьте ответ текстом.")
        return
    data = await state.get_data()
    questions = data["questions"]
    index = data["index"]
    answers = data["answers"]
    answers[questions[index][1]] = message.text.strip()
    index += 1

    if index < len(questions):
        await state.update_data(index=index, answers=answers)
        await message.answer(
            f"<b>Вопрос {index + 1}/{len(questions)}.</b>\n{questions[index][0]}",
            parse_mode="HTML"
        )
        return

    kind = data["kind"]
    title = data["title"]
    username = message.from_user.username
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO applications (user_id, username, kind, answers, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                message.from_user.id,
                username,
                kind,
                "\n".join(f"{label}: {answers[key]}" for label, key in questions),
                datetime.now(timezone.utc).isoformat()
            )
        )
        app_id = cur.lastrowid

    await state.clear()
    await message.answer(
        "✅ <b>Заявка отправлена!</b>\n\n"
        "Администрация рассмотрит её и пришлёт вам ответ в этот чат.",
        parse_mode="HTML",
        reply_markup=main_keyboard(message.from_user.id == ADMIN_ID)
    )

    username_text = f"@{safe(username)}" if username else "не указан"
    body = "\n".join(f"• <b>{safe(label)}:</b> {safe(answers[key])}" for label, key in questions)
    admin_text = (
        f"📨 <b>Новая заявка №{app_id}</b>\n"
        f"Направление: <b>{safe(title)}</b>\n"
        f"От: {safe(message.from_user.full_name)}\n"
        f"Username: {username_text}\n"
        f"Telegram ID: <code>{message.from_user.id}</code>\n\n"
        f"{body}"
    )
    try:
        await bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML", reply_markup=application_actions(app_id))
    except Exception:
        logger.exception("Could not deliver application %s to admin", app_id)
        await message.answer("⚠️ Заявка сохранена, но уведомление администрации не доставлено. Попробуйте позже.")

@dp.callback_query(F.data.in_({"admin:list", "admin:refresh"}))
async def list_applications(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    rows = get_pending()
    if not rows:
        await callback.message.answer("📭 Сейчас нет заявок на рассмотрении.")
    else:
        await callback.message.answer(f"📥 <b>Заявки на рассмотрении: {len(rows)}</b>", parse_mode="HTML")
        for row in rows[:20]:
            username = f"@{safe(row['username'])}" if row["username"] else "не указан"
            await callback.message.answer(
                f"📨 <b>Заявка №{row['id']}</b>\nТип: {safe(APPLICATIONS[row['kind']][0])}\n"
                f"Пользователь: {username}\nID: <code>{row['user_id']}</code>\n\n{safe(row['answers'])}",
                parse_mode="HTML",
                reply_markup=application_actions(row["id"])
            )
    await callback.answer()

@dp.callback_query(F.data.startswith("app:"))
async def decide_application(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, action, raw_id = callback.data.split(":")
    app_id = int(raw_id)
    row = get_application(app_id)
    if not row or row["status"] != "pending":
        await callback.answer("Эта заявка уже обработана или не найдена.", show_alert=True)
        return

    status = "approved" if action == "approve" else "rejected"
    if action not in ("approve", "reject") or not set_status(app_id, status):
        await callback.answer("Не удалось обработать заявку.", show_alert=True)
        return

    if status == "approved":
        user_text = "🎉 <b>Ваша заявка одобрена!</b>\n\nАдминистрация GOOD RUSSIA HELP приняла положительное решение."
        admin_label = "✅ Одобрена"
    else:
        user_text = "К сожалению, ваша заявка в GOOD RUSSIA HELP отклонена. Спасибо за интерес к проекту!"
        admin_label = "❌ Отклонена"

    try:
        await bot.send_message(row["user_id"], user_text, parse_mode="HTML")
        delivery = "Уведомление пользователю отправлено."
    except Exception:
        delivery = "Не удалось написать пользователю (возможно, он не запускал бота)."

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"{admin_label} заявка №{app_id}. {delivery}")
    await callback.answer("Готово")

async def main():
    init_db()
    logger.info("Starting GOOD RUSSIA HELP bot; admin=%s", ADMIN_ID)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
