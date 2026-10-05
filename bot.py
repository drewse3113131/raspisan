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
from aiogram.exceptions import TelegramBadRequest

from config import SHEETS, BOT_TOKEN
from parser import get_dates, get_courses, get_groups, get_schedule, format_schedule

logging.basicConfig(level=logging.INFO)

ADMIN_ID = 8275952252
ADMIN_IDS = {8275952252, 8203111503}
STATS_FILE = os.path.join(os.path.dirname(__file__), "stats.json")
BROADCAST_PENDING = set()  # id админов ожидающих сообщение для рассылки

def is_admin(user_id) -> bool:
    if not user_id:
        return False
    try:
        return int(user_id) in ADMIN_IDS
    except:
        return False


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

# --- healthcheck для Render (чтобы не было Timed Out) ---
async def healthcheck_server():
    try:
        from aiohttp import web
        app = web.Application()
        async def handle(request):
            return web.Response(text="Bot is running - @hohkam")
        app.router.add_get("/", handle)
        app.router.add_get("/health", handle)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.getenv("PORT", "10000"))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logging.info(f"Healthcheck server started on port {port}")
        while True:
            await asyncio.sleep(3600)
    except Exception as e:
        logging.warning(f"Healthcheck server not started: {e}")

async def safe_edit(cb: CallbackQuery, text: str, markup):
    try:
        await cb.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            try:
                await cb.answer()
            except: pass
        else:
            logging.warning(f"edit_text error: {e}")
            try:
                await cb.answer("⚠️ Ошибка обновления", show_alert=False)
            except: pass
    except Exception as e:
        logging.exception(e)

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

_admin_env = os.getenv("ADMIN_ID") or os.getenv("ADMIN_IDS") or ""
if _admin_env:
    for _a in _admin_env.replace(";", ",").split(","):
        _a = _a.strip()
        if _a.isdigit():
            ADMIN_IDS.add(int(_a))

TOKEN = BOT_TOKEN or os.getenv("BOT_TOKEN") or ""

def campus_kb(user_id=None):
    buttons = []
    for key, cfg in SHEETS.items():
        buttons.append([InlineKeyboardButton(text=f"{cfg['emoji']} {cfg['name']}", callback_data=f"campus:{key}")])
    buttons.append([InlineKeyboardButton(text="🔔 Расписание звонков", callback_data="bells")])
    buttons.append([InlineKeyboardButton(text="ℹ️ О боте", callback_data="about")])
    buttons.append([InlineKeyboardButton(text="👨‍💻 Создатель бота — @hohkam", url="https://t.me/hohkam")])
    if is_admin(user_id):
        buttons.append([InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Рассылка (сообщение всем)", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📊 Статистика бота", callback_data="stats")],
        [InlineKeyboardButton(text="🔄 Сбросить кэш расписания", callback_data="admin_clear_cache")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back:campus")],
    ])


def bells_kb(user_id=None):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back:campus")],
    ])

def dates_kb(campus_key):
    dates = get_dates(campus_key)
    rows = []
    for idx, d in enumerate(dates):
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
    await safe_edit(cb, txt, campus_kb(cb.from_user.id))

async def bells_handler(cb: CallbackQuery):
    await cb.answer()
    await safe_edit(cb, BELLS_TEXT, bells_kb(cb.from_user.id))

async def bells_cmd(message: Message):
    await message.answer(BELLS_TEXT, reply_markup=bells_kb(message.from_user.id), parse_mode=ParseMode.HTML)

async def stats_handler(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔ Только для админа", show_alert=True)
        return
    await cb.answer()
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
        [InlineKeyboardButton(text="📢 Рассылка всем", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="stats")],
        [InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back:campus")],
    ])
    await safe_edit(cb, txt, kb)

async def stats_cmd(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для админа")
        return
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
        [InlineKeyboardButton(text="📢 Рассылка всем", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")],
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
    await safe_edit(cb, txt, dates_kb(campus_key))

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
    await safe_edit(cb, txt, courses_kb(campus_key, date_idx))

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
    await safe_edit(cb, txt, groups_kb(campus_key, date_idx, course))

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
    await safe_edit(cb, text, schedule_kb(campus_key, date_idx, course, group))

async def refresh_cb(cb: CallbackQuery):
    _, campus_key, date_idx, course, group = cb.data.split(":",4)
    from parser import _cache
    _cache.pop(campus_key, None)
    await cb.answer("Обновляю...")
    try:
        lessons, date_str = get_schedule(campus_key, course, group, date_idx)
        cfg = SHEETS[campus_key]
        text = format_schedule(group, lessons, date_str, cfg['name'])
        await safe_edit(cb, text, schedule_kb(campus_key, date_idx, course, group))
    except Exception as e:
        logging.exception(e)
        await cb.answer("Ошибка обновления", show_alert=True)
    try:
        await cb.answer("Обновлено ✅")
    except: pass

async def back_cb(cb: CallbackQuery):
    data = cb.data
    await cb.answer()
    if data == "back:campus":
        await safe_edit(cb, "👇 <b>Выбери площадку:</b>\n\n👨‍💻 <i>Создатель бота — @hohkam</i>", campus_kb(cb.from_user.id))
    elif data.startswith("back:dates:"):
        _, _, campus_key = data.split(":")
        cfg = SHEETS[campus_key]
        await safe_edit(cb, f"{cfg['emoji']} <b>{cfg['full']}</b>\n<i>выбери дату:</i>", dates_kb(campus_key))
    elif data.startswith("back:course:"):
        _, _, campus_key, date_idx = data.split(":")
        cfg = SHEETS[campus_key]
        dates = get_dates(campus_key)
        date_str = dates[int(date_idx)] if dates else ""
        await safe_edit(cb, f"{cfg['emoji']} <b>{cfg['name']} • {date_str}</b>\n<i>выбери курс:</i>", courses_kb(campus_key, date_idx))
    elif data.startswith("back:groups:"):
        _, _, campus_key, date_idx, course = data.split(":",4)
        cfg = SHEETS[campus_key]
        dates = get_dates(campus_key)
        date_str = dates[int(date_idx)] if dates else ""
        await safe_edit(cb, f"{cfg['emoji']} <b>{cfg['name']} • {date_str} • {course}</b>\n<i>выбери группу:</i>", groups_kb(campus_key, date_idx, course))

async def admin_panel_handler(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔ Только для админа", show_alert=True)
        return
    await cb.answer()
    data = _load_stats()
    users_cnt = len(data.get("users", {}))
    txt = (
        "👑 <b>Панель администратора</b>\n\n"
        f"👥 Пользователей в базе: <b>{users_cnt}</b>\n"
        f"▶️ Всего запусков: <b>{data.get('total_starts', 0)}</b>\n"
        f"👁️ Просмотров расписания: <b>{data.get('total_views', 0)}</b>\n\n"
        "Выбери нужный раздел:"
    )
    await safe_edit(cb, txt, admin_kb())

async def admin_cmd(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для админа")
        return
    data = _load_stats()
    users_cnt = len(data.get("users", {}))
    txt = (
        "👑 <b>Панель администратора</b>\n\n"
        f"👥 Пользователей в базе: <b>{users_cnt}</b>\n"
        f"▶️ Всего запусков: <b>{data.get('total_starts', 0)}</b>\n"
        f"👁️ Просмотров расписания: <b>{data.get('total_views', 0)}</b>\n\n"
        "Выбери нужный раздел:"
    )
    await message.answer(txt, reply_markup=admin_kb(), parse_mode=ParseMode.HTML)

async def admin_clear_cache_cb(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔ Только для админа", show_alert=True)
        return
    from parser import _cache
    _cache.clear()
    await cb.answer("✅ Кэш расписания очищен!", show_alert=True)

async def admin_broadcast_cb(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔ Только для админа", show_alert=True)
        return
    await cb.answer()
    BROADCAST_PENDING.add(cb.from_user.id)
    data = _load_stats()
    users_count = len(data.get("users", {}))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")],
        [InlineKeyboardButton(text="👑 В админку", callback_data="admin_panel")],
    ])
    txt = (
        "📢 <b>Режим рассылки сообщений</b>\n\n"
        "Отправь прямо сейчас сообщение, которое нужно переслать <b>всем пользователям</b> бота.\n\n"
        "<b>Поддерживается:</b>\n"
        "• Текст (с форматированием HTML/ссылками)\n"
        "• Фото, видео, кружочки, голосовые, документы\n"
        "• Пересланные сообщения\n\n"
        f"👥 Получателей в базе: <b>{users_count}</b>\n\n"
        "<i>Нажми кнопку ниже для отмены или отправь /cancel.</i>"
    )
    await safe_edit(cb, txt, kb)

async def broadcast_cmd(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для админа")
        return
    # если команда с текстом: /broadcast Текст -> сразу рассылаем
    text = message.text or ""
    # убираем команду
    parts = text.split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        # сразу рассылка текста
        msg_text = parts[1].strip()
        data = _load_stats()
        users = list(data["users"].keys())
        if not users:
            await message.answer("📭 База пуста, некому слать.", reply_markup=admin_kb())
            return
        status_msg = await message.answer(f"📢 Начинаю рассылку на <b>{len(users)}</b> юзеров...\nТекст: {msg_text[:100]}", parse_mode=ParseMode.HTML)
        sent = 0
        failed = 0
        for idx, uid in enumerate(users, 1):
            try:
                await message.bot.send_message(chat_id=int(uid), text=msg_text, parse_mode=ParseMode.HTML)
                sent += 1
            except Exception as e:
                failed += 1
                logging.warning(f"broadcast to {uid} failed: {e}")
            await asyncio.sleep(0.05)
            if idx % 25 == 0:
                try:
                    await status_msg.edit_text(f"⏳ Прогресс: <b>{idx}/{len(users)}</b>", parse_mode=ParseMode.HTML)
                except: pass
        await message.answer(
            f"✅ <b>Рассылка завершена!</b>\n\n"
            f"📨 Успешно отправлено: <b>{sent}</b>\n"
            f"❌ Ошибок / заблокировали: <b>{failed}</b>\n"
            f"👥 Всего в базе: <b>{len(users)}</b>",
            reply_markup=admin_kb(),
            parse_mode=ParseMode.HTML
        )
        return
    # иначе ждем следующее сообщение
    BROADCAST_PENDING.add(message.from_user.id)
    data = _load_stats()
    users_count = len(data.get("users", {}))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")],
        [InlineKeyboardButton(text="👑 В админку", callback_data="admin_panel")],
    ])
    await message.answer(
        "📢 <b>Режим рассылки сообщений</b>\n\n"
        "Отправь мне прямо сейчас сообщение (текст, фото, видео, голосовое, кружок, документ) — я разошлю его всем юзерам.\n\n"
        f"👥 Получателей в базе: <b>{users_count}</b>\n\n"
        "<i>Нажми кнопку ниже для отмены или отправь /cancel.</i>",
        reply_markup=kb, parse_mode=ParseMode.HTML
    )

async def broadcast_cancel_cb(cb: CallbackQuery):
    BROADCAST_PENDING.discard(cb.from_user.id)
    await cb.answer("Отменено")
    kb = admin_kb() if is_admin(cb.from_user.id) else campus_kb(cb.from_user.id)
    await safe_edit(cb, "❌ Рассылка отменена", kb)

async def broadcast_content_handler(message: Message):
    if not is_admin(message.from_user.id) or message.from_user.id not in BROADCAST_PENDING:
        return
    # если это команда - не считаем контентом (кроме /cancel)
    if message.text and message.text.startswith("/"):
        if message.text.strip() == "/cancel":
            BROADCAST_PENDING.discard(message.from_user.id)
            await message.answer("❌ Рассылка отменена", reply_markup=admin_kb())
            return
        return
    BROADCAST_PENDING.discard(message.from_user.id)
    data = _load_stats()
    users = list(data.get("users", {}).keys())
    if not users:
        await message.answer("📭 База пользователей пуста, некому слать.", reply_markup=admin_kb())
        return
    status_msg = await message.answer(f"📢 Начинаю рассылку на <b>{len(users)}</b> пользователей...", parse_mode=ParseMode.HTML)
    sent = 0
    failed = 0
    # показываем прогресс каждые 25
    for idx, uid in enumerate(users, 1):
        try:
            await message.bot.copy_message(chat_id=int(uid), from_chat_id=message.chat.id, message_id=message.message_id)
            sent += 1
        except Exception as e:
            failed += 1
            logging.warning(f"broadcast copy to {uid} failed: {e}")
        await asyncio.sleep(0.05)
        if idx % 25 == 0:
            try:
                await status_msg.edit_text(f"⏳ Прогресс: <b>{idx}/{len(users)}</b>", parse_mode=ParseMode.HTML)
            except: pass
    await message.answer(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📨 Успешно отправлено: <b>{sent}</b>\n"
        f"❌ Ошибок / заблокировали: <b>{failed}</b>\n"
        f"👥 Всего в базе: <b>{len(users)}</b>",
        reply_markup=admin_kb(),
        parse_mode=ParseMode.HTML
    )

async def cmd_schedule(message: Message):
    _log_start(message.from_user)
    await message.answer("👇 Выбери корпус:\n\n👨‍💻 <i>Создатель бота — @hohkam</i>", reply_markup=campus_kb(message.from_user.id), parse_mode=ParseMode.HTML)

def main():
    if not TOKEN:
        print("BOT_TOKEN missing!")
        return
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.message.register(admin_cmd, Command("admin"))
    dp.message.register(broadcast_cmd, Command("broadcast"))
    dp.message.register(broadcast_cmd, Command("sendall"))
    dp.message.register(broadcast_cmd, Command("announce"))
    dp.message.register(broadcast_cmd, Command("rassilka"))
    dp.message.register(broadcast_content_handler, lambda m: m.from_user and is_admin(m.from_user.id) and m.from_user.id in BROADCAST_PENDING)
    dp.message.register(start_handler, CommandStart())
    dp.message.register(cmd_schedule, Command("schedule"))
    dp.message.register(cmd_schedule, Command("rasp"))
    dp.message.register(bells_cmd, Command("bells"))
    dp.message.register(bells_cmd, Command("zvonki"))
    dp.message.register(stats_cmd, Command("stats"))
    dp.message.register(stats_cmd, Command("stat"))
    dp.callback_query.register(about_handler, F.data == "about")
    dp.callback_query.register(bells_handler, F.data == "bells")
    dp.callback_query.register(admin_panel_handler, F.data == "admin_panel")
    dp.callback_query.register(admin_broadcast_cb, F.data == "admin_broadcast")
    dp.callback_query.register(admin_clear_cache_cb, F.data == "admin_clear_cache")
    dp.callback_query.register(stats_handler, F.data == "stats")
    dp.callback_query.register(broadcast_cancel_cb, F.data == "broadcast_cancel")
    dp.callback_query.register(campus_cb, F.data.startswith("campus:"))
    dp.callback_query.register(date_cb, F.data.startswith("date:"))
    dp.callback_query.register(course_cb, F.data.startswith("course:"))
    dp.callback_query.register(group_cb, F.data.startswith("group:"))
    dp.callback_query.register(refresh_cb, F.data.startswith("refresh:"))
    dp.callback_query.register(back_cb, F.data.startswith("back:"))
    print("Bot started. Waiting /start")

    async def runner():
        # запускаем healthcheck параллельно с ботом (для Render)
        asyncio.create_task(healthcheck_server())
        await dp.start_polling(bot)

    asyncio.run(runner())

if __name__ == "__main__":
    main()
