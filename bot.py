import asyncio
import os
import json
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import SHEETS, BOT_TOKEN
from parser import get_dates, get_courses, get_groups, get_schedule, format_schedule

logging.basicConfig(level=logging.INFO)

ADMIN_ID = 8275952252
STATS_FILE = os.path.join(os.path.dirname(__file__), "stats.json")

BELLS_TEXT = (
    "🔔 <b>Расписание звонков</b>\n\n"
    "—" * 18 + "\n"
    "<b>1 пара</b>\n"
    "  1 урок: 8:30 – 9:15\n"
    "  2 урок: 9:20 – 10:05\n\n"
    "<b>2 пара</b>\n"
    "  3 урок: 10:15 – 11:00\n"
    "  4 урок: 11:05 – 11:50\n\n"
    "<i>Обед — 40 мин.</i>\n\n"
    "<b>3 пара</b>\n"
    "  5 урок: 12:30 – 13:15\n"
    "  6 урок: 13:20 – 14:05\n\n"
    "<b>4 пара</b>\n"
    "  7 урок: 14:15 – 15:00\n"
    "  8 урок: 15:05 – 15:50\n"
)

def _load_stats():
    if not os.path.exists(STATS_FILE):
        return {"users": {}, "total_starts": 0, "total_views": 0}
    try:
        with open(STATS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"users": {}, "total_starts": 0, "total_views": 0}

def _save_stats(data):
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.exception(e)

def _log_start(user):
    try:
        data = _load_stats()
        uid = str(user.id)
        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        if uid not in data["users"]:
            data["users"][uid] = {"id": user.id, "username": user.username or "", "first_name": user.first_name or "", "starts": 0, "views": 0, "first_seen": now, "last_seen": now}
        data["users"][uid]["username"] = user.username or data["users"][uid].get("username","")
        data["users"][uid]["first_name"] = user.first_name or data["users"][uid].get("first_name","")
        data["users"][uid]["starts"] += 1
        data["users"][uid]["last_seen"] = now
        data["total_starts"] += 1
        _save_stats(data)
    except Exception as e:
        logging.exception(e)

def _log_view(user, campus_key, course, group, date_str):
    try:
        data = _load_stats()
        uid = str(user.id)
        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        if uid not in data["users"]:
            data["users"][uid] = {"id": user.id, "username": user.username or "", "first_name": user.first_name or "", "starts": 0, "views": 0, "first_seen": now, "last_seen": now}
        data["users"][uid]["views"] += 1
        data["users"][uid]["last_seen"] = now
        data["users"][uid]["last_group"] = f"{group} ({campus_key} {course} {date_str})"
        data["total_views"] += 1
        _save_stats(data)
    except Exception as e:
        logging.exception(e)


def _load_env(path):
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8-sig") as f:
                for line in f:
                    line=line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k,v=line.split("=",1)
                    k=k.strip().lstrip("\ufeff").strip()
                    v=v.strip().strip('"').strip("'")
                    if k and v and not os.getenv(k):
                        os.environ[k]=v
    except: pass

_load_env(".env")
_load_env("C:\\Users\\user\\Desktop\\bot\\.env")
_load_env(os.path.join(os.path.dirname(__file__), ".env"))

TOKEN = BOT_TOKEN or os.getenv("BOT_TOKEN") or ""

def campus_kb(user_id=None):
    buttons = []
    for key, cfg in SHEETS.items():
        buttons.append([InlineKeyboardButton(text=f"{cfg['emoji']} {cfg['name']}", callback_data=f"campus:{key}")])
    buttons.append([InlineKeyboardButton(text="🔔 Расписание звонков", callback_data="bells")])
    buttons.append([InlineKeyboardButton(text="ℹ️ О боте", callback_data="about")])
    buttons.append([InlineKeyboardButton(text="👨‍💻 Создатель бота — @hohkam", url="https://t.me/hohkam")])
    if user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton(text="📊 Статистика", callback_data="stats")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def bells_kb(user_id=None):
    # кнопка назад ведет в главное меню
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back:campus")],
    ])

def dates_kb(campus_key):
    dates = get_dates(campus_key)
    rows = []
    for idx, d in enumerate(dates):
        # показываем дату как есть: "01 сентября", "04 сентября ПЯТНИЦА"
        rows.append([InlineKeyboardButton(text=f"📅 {d}", callback_data=f"date:{campus_key}:{idx}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back:campus")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def courses_kb(campus_key, date_idx):
    courses = get_courses(campus_key, date_idx)
    rows = []
    for c in courses:
        rows.append([InlineKeyboardButton(text=f"📚 {c}", callback_data=f"course:{campus_key}:{date_idx}:{c}")])
    rows.append([InlineKeyboardButton(text="◀️ К датам", callback_data=f"back:dates:{campus_key}")])
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back:campus")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def groups_kb(campus_key, date_idx, course):
    groups = get_groups(campus_key, course, date_idx)
    rows = []
    row = []
    for g in groups:
        row.append(InlineKeyboardButton(text=g, callback_data=f"group:{campus_key}:{date_idx}:{course}:{g}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="◀️ К курсам", callback_data=f"back:course:{campus_key}:{date_idx}")])
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back:campus")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def schedule_kb(campus_key, date_idx, course, group):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"refresh:{campus_key}:{date_idx}:{course}:{group}")],
        [InlineKeyboardButton(text="◀️ К группам", callback_data=f"back:groups:{campus_key}:{date_idx}:{course}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back:campus")],
    ])

async def start_handler(message: Message):
    _log_start(message.from_user)
    text = (
        "👋 <b>Привет! Я — бот расписания</b>\n\n"
        "Выбери корпус → дату → курс → группу — покажу пары.\n"
        "Данные прямо из Google-таблиц техникума.\n\n"
        "👇 <i>Выбери площадку:</i>\n\n"
        "👨‍💻 <i>Создатель бота — @hohkam</i>"
    )
    await message.answer(text, reply_markup=campus_kb(message.from_user.id), parse_mode=ParseMode.HTML)

async def about_handler(cb: CallbackQuery):
    await cb.answer()
    txt = (
        "ℹ️ <b>О боте</b>\n\n"
        "Берет расписание из официальных таблиц:\n"
        f"• {SHEETS['chapaeva']['full']}\n"
        f"• {SHEETS['pushkino']['full']}\n\n"
        "Навигация: Корпус → Дата → Курс → Группа\n"
        "После 2-й пары перерыв 40 мин, остальные 10 мин.\n"
        "Обновляется каждые 10 минут.\n\n"
        "👨‍💻 <b>Создатель бота — @hohkam</b>"
    )
    await cb.message.edit_text(txt, reply_markup=campus_kb(cb.from_user.id), parse_mode=ParseMode.HTML)

async def bells_handler(cb: CallbackQuery):
    await cb.answer()
    await cb.message.edit_text(BELLS_TEXT, reply_markup=bells_kb(cb.from_user.id), parse_mode=ParseMode.HTML)

async def bells_cmd(message: Message):
    await message.answer(BELLS_TEXT, reply_markup=bells_kb(message.from_user.id), parse_mode=ParseMode.HTML)

async def stats_handler(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("⛔ Только для админа", show_alert=True)
        return
    await cb.answer()
    data = _load_stats()
    total_users = len(data["users"])
    total_starts = data.get("total_starts", 0)
    total_views = data.get("total_views", 0)
    # топ-5 по просмотрам
    users_sorted = sorted(data["users"].values(), key=lambda x: x.get("views",0), reverse=True)[:10]
    lines = [
        f"📊 <b>Статистика бота</b>\n\n",
        f"👥 Всего юзеров: <b>{total_users}</b>\n",
        f"▶️ Стартов /start: <b>{total_starts}</b>\n",
        f"👁️ Просмотров расписания: <b>{total_views}</b>\n",
        f"—" * 18 + "\n",
        f"<b>Топ-10 активных:</b>\n"
    ]
    if not users_sorted:
        lines.append("<i>пока пусто</i>\n")
    else:
        for i, u in enumerate(users_sorted, 1):
            uname = f"@{u['username']}" if u.get("username") else f"id:{u['id']}"
            name = u.get("first_name","")
            views = u.get("views",0)
            starts = u.get("starts",0)
            last = u.get("last_seen","")
            last_gr = u.get("last_group","—")
            lines.append(f"{i}. {name} ({uname}) — 👁️{views} ▶️{starts} | {last}\n   └ {last_gr}\n")
    lines.append(f"\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    txt = "".join(lines)
    # телеграм лимит 4096, обрежем если много
    if len(txt) > 4000:
        txt = txt[:4000] + "\n<i>...обрезано</i>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="stats")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back:campus")],
    ])
    await cb.message.edit_text(txt, reply_markup=kb, parse_mode=ParseMode.HTML)

async def stats_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Только для админа")
        return
    # делаем фейковый cb чтобы переиспользовать логику
    data = _load_stats()
    total_users = len(data["users"])
    total_starts = data.get("total_starts", 0)
    total_views = data.get("total_views", 0)
    users_sorted = sorted(data["users"].values(), key=lambda x: x.get("views",0), reverse=True)[:10]
    lines = [
        f"📊 <b>Статистика бота</b>\n\n",
        f"👥 Всего юзеров: <b>{total_users}</b>\n",
        f"▶️ Стартов /start: <b>{total_starts}</b>\n",
        f"👁️ Просмотров расписания: <b>{total_views}</b>\n",
        f"—" * 18 + "\n",
        f"<b>Топ-10 активных:</b>\n"
    ]
    if not users_sorted:
        lines.append("<i>пока пусто</i>\n")
    else:
        for i, u in enumerate(users_sorted, 1):
            uname = f"@{u['username']}" if u.get("username") else f"id:{u['id']}"
            name = u.get("first_name","")
            views = u.get("views",0)
            starts = u.get("starts",0)
            last = u.get("last_seen","")
            last_gr = u.get("last_group","—")
            lines.append(f"{i}. {name} ({uname}) — 👁️{views} ▶️{starts} | {last}\n   └ {last_gr}\n")
    lines.append(f"\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    txt = "".join(lines)
    if len(txt) > 4000:
        txt = txt[:4000] + "\n<i>...обрезано</i>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back:campus")],
    ])
    await message.answer(txt, reply_markup=kb, parse_mode=ParseMode.HTML)

async def campus_cb(cb: CallbackQuery):
    _, campus_key = cb.data.split(":",1)
    cfg = SHEETS[campus_key]
    try:
        dates = get_dates(campus_key)
        if not dates:
            raise ValueError("no dates")
    except Exception as e:
        logging.exception(e)
        await cb.answer("⚠️ Не удалось загрузить таблицу, попробуй позже", show_alert=True)
        return
    await cb.answer()
    txt = f"{cfg['emoji']} <b>{cfg['full']}</b>\n<i>выбери дату:</i>"
    await cb.message.edit_text(txt, reply_markup=dates_kb(campus_key), parse_mode=ParseMode.HTML)

async def date_cb(cb: CallbackQuery):
    _, campus_key, date_idx = cb.data.split(":",2)
    cfg = SHEETS[campus_key]
    dates = get_dates(campus_key)
    try:
        date_str = dates[int(date_idx)]
    except:
        date_str = "дата"
    await cb.answer()
    txt = f"{cfg['emoji']} <b>{cfg['name']} • {date_str}</b>\n<i>выбери курс:</i>"
    await cb.message.edit_text(txt, reply_markup=courses_kb(campus_key, date_idx), parse_mode=ParseMode.HTML)

async def course_cb(cb: CallbackQuery):
    _, campus_key, date_idx, course = cb.data.split(":",3)
    await cb.answer()
    cfg = SHEETS[campus_key]
    dates = get_dates(campus_key)
    date_str = dates[int(date_idx)] if dates else ""
    txt = f"{cfg['emoji']} <b>{cfg['name']} • {date_str} • {course}</b>\n<i>выбери группу:</i>"
    try:
        groups = get_groups(campus_key, course, date_idx)
        if not groups:
            await cb.message.edit_text("😕 Для этого курса групп не нашлось", reply_markup=courses_kb(campus_key, date_idx))
            return
    except Exception as e:
        logging.exception(e)
        await cb.answer("Ошибка загрузки", show_alert=True)
        return
    await cb.message.edit_text(txt, reply_markup=groups_kb(campus_key, date_idx, course), parse_mode=ParseMode.HTML)

async def group_cb(cb: CallbackQuery):
    _, campus_key, date_idx, course, group = cb.data.split(":",4)
    await cb.answer("Загружаю расписание...")
    try:
        lessons, date_str = get_schedule(campus_key, course, group, date_idx)
        cfg = SHEETS[campus_key]
        text = format_schedule(group, lessons, date_str, cfg['name'])
        _log_view(cb.from_user, campus_key, course, group, date_str)
    except Exception as e:
        logging.exception(e)
        await cb.message.edit_text("⚠️ Ошибка при получении расписания. Попробуй обновить.", reply_markup=groups_kb(campus_key, date_idx, course))
        return
    await cb.message.edit_text(text, reply_markup=schedule_kb(campus_key, date_idx, course, group), parse_mode=ParseMode.HTML)

async def refresh_cb(cb: CallbackQuery):
    _, campus_key, date_idx, course, group = cb.data.split(":",4)
    from parser import _cache
    _cache.pop(campus_key, None)
    # заново вызвать group
    await cb.answer("Обновляю...")
    try:
        lessons, date_str = get_schedule(campus_key, course, group, date_idx)
        cfg = SHEETS[campus_key]
        text = format_schedule(group, lessons, date_str, cfg['name'])
        await cb.message.edit_text(text, reply_markup=schedule_kb(campus_key, date_idx, course, group), parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.exception(e)
        await cb.answer("Ошибка обновления", show_alert=True)
    await cb.answer("Обновлено ✅")

async def back_cb(cb: CallbackQuery):
    data = cb.data
    await cb.answer()
    if data == "back:campus":
        await cb.message.edit_text("👇 <b>Выбери площадку:</b>\n\n👨‍💻 <i>Создатель бота — @hohkam</i>", reply_markup=campus_kb(cb.from_user.id), parse_mode=ParseMode.HTML)
    elif data.startswith("back:dates:"):
        _, _, campus_key = data.split(":")
        cfg = SHEETS[campus_key]
        await cb.message.edit_text(f"{cfg['emoji']} <b>{cfg['full']}</b>\n<i>выбери дату:</i>", reply_markup=dates_kb(campus_key), parse_mode=ParseMode.HTML)
    elif data.startswith("back:course:"):
        _, _, campus_key, date_idx = data.split(":")
        cfg = SHEETS[campus_key]
        dates = get_dates(campus_key)
        date_str = dates[int(date_idx)] if dates else ""
        await cb.message.edit_text(f"{cfg['emoji']} <b>{cfg['name']} • {date_str}</b>\n<i>выбери курс:</i>", reply_markup=courses_kb(campus_key, date_idx), parse_mode=ParseMode.HTML)
    elif data.startswith("back:groups:"):
        _, _, campus_key, date_idx, course = data.split(":",4)
        cfg = SHEETS[campus_key]
        dates = get_dates(campus_key)
        date_str = dates[int(date_idx)] if dates else ""
        await cb.message.edit_text(f"{cfg['emoji']} <b>{cfg['name']} • {date_str} • {course}</b>\n<i>выбери группу:</i>", reply_markup=groups_kb(campus_key, date_idx, course), parse_mode=ParseMode.HTML)

async def cmd_schedule(message: Message):
    _log_start(message.from_user)
    await message.answer("👇 Выбери корпус:\n\n👨‍💻 <i>Создатель бота — @hohkam</i>", reply_markup=campus_kb(message.from_user.id), parse_mode=ParseMode.HTML)

def main():
    if not TOKEN:
        print("BOT_TOKEN missing!")
        return
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.message.register(start_handler, CommandStart())
    dp.message.register(cmd_schedule, Command("schedule"))
    dp.message.register(cmd_schedule, Command("rasp"))
    dp.message.register(bells_cmd, Command("bells"))
    dp.message.register(bells_cmd, Command("zvonki"))
    dp.message.register(stats_cmd, Command("stats"))
    dp.message.register(stats_cmd, Command("stat"))
    dp.callback_query.register(about_handler, F.data == "about")
    dp.callback_query.register(bells_handler, F.data == "bells")
    dp.callback_query.register(stats_handler, F.data == "stats")
    dp.callback_query.register(campus_cb, F.data.startswith("campus:"))
    dp.callback_query.register(date_cb, F.data.startswith("date:"))
    dp.callback_query.register(course_cb, F.data.startswith("course:"))
    dp.callback_query.register(group_cb, F.data.startswith("group:"))
    dp.callback_query.register(refresh_cb, F.data.startswith("refresh:"))
    dp.callback_query.register(back_cb, F.data.startswith("back:"))
    print("Bot started. Waiting /start")
    asyncio.run(dp.start_polling(bot))

if __name__ == "__main__":
    main()
