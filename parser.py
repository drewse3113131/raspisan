import re
import csv
import io
import time
import urllib.request
from collections import defaultdict

from config import SHEETS, CACHE_TTL

_cache = {}  # campus -> (ts, data)

def _fetch_csv(sid, gid):
    url = f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid={gid}"
    data = urllib.request.urlopen(url, timeout=15).read().decode("utf-8")
    return data

def _extract_date(text: str):
    # ищем "01 сентября", "04 сентября ПЯТНИЦА", "07 сентября (ПОНЕДЕЛЬНИК)", "05 сентября 2026 г.(СУББОТА)"
    m = re.search(r"(\d{1,2}\s+сентября[^\n,]*)", text, re.I)
    if m:
        s = m.group(1).strip().strip(' "').strip()
        # убрать лишнее "(очная форма обучения)" - не попадает
        # нормализуем двойные пробелы
        s = re.sub(r"\s+", " ", s)
        return s
    m2 = re.search(r"на\s+(\d{1,2}\s+[а-яА-ЯёЁ]+[^\n]*)", text, re.I)
    if m2:
        return m2.group(1).strip()
    return ""

def parse_campus_multi(campus_key: str):
    """возвращает {days: [{date, courses: {course: {group: [lessons]}}, course_order: []}], dates: []}"""
    cfg = SHEETS[campus_key]
    now = time.time()
    if campus_key in _cache and now - _cache[campus_key][0] < CACHE_TTL:
        cached = _cache[campus_key][1]
        # обратная совместимость: если кэш старый формат — перепарсить
        if "days" in cached:
            return cached

    csv_text = _fetch_csv(cfg["id"], cfg["gid"])
    lines = list(csv.reader(io.StringIO(csv_text)))

    days = []
    current_day = None
    current_course = None
    group_cols = []
    seen_courses_for_day = set()

    def new_day(date_str):
        nonlocal current_day, seen_courses_for_day, current_course, group_cols
        if not date_str:
            date_str = "сегодня"
        # если дата уже есть и это тот же день — не дублируем
        current_day = {"date": date_str, "courses": defaultdict(lambda: defaultdict(list)), "course_order": []}
        days.append(current_day)
        seen_courses_for_day = set()
        current_course = None
        group_cols = []

    i = 0
    while i < len(lines):
        row = [c.strip() for c in lines[i]]
        joined = " ".join(row)
        low_joined = joined.lower()

        # детект даты: строка с "сентября" или "корректировка" + дата
        is_date_row = False
        date_candidate = ""
        if "сентября" in low_joined:
            date_candidate = _extract_date(joined)
            if date_candidate:
                is_date_row = True
        # строка "КОРРЕКТИРОВКА РАСПИСАНИЯ" сама по себе не дата, но следом будет дата
        # поэтому чекаем именно наличие сентября

        if is_date_row:
            # новая дата — заводим новый день
            new_day(date_candidate)
            i += 1
            continue

        # детект шапки курса
        joined0 = row[0].lower() if row else ""
        if "курс" in joined0:
            if current_day is None:
                # если до этого даты не было — создаём день с дефолтной датой
                new_day("сегодня")
            raw_course = row[0].strip()
            # если курс уже был в этом дне — значит начался новый день без явной даты (редко), создаём новый
            if raw_course in seen_courses_for_day and current_day["course_order"]:
                # создаём новый день без даты (наследник)
                new_day(current_day["date"])
            seen_courses_for_day.add(raw_course)
            current_course = raw_course
            if raw_course not in current_day["course_order"]:
                current_day["course_order"].append(raw_course)
            group_cols = []
            for col_idx, cell in enumerate(row):
                cell = cell.strip()
                if not cell:
                    continue
                low = cell.lower()
                if "курс" in low or low in ("время","№ пары","№","к","№ к"):
                    continue
                raw_group = cell.strip()
                if raw_group:
                    group_cols.append((col_idx, [raw_group]))
                    # предсоздаём группу даже если пар нет — чтобы показать "выходной"
                    if raw_group not in current_day["courses"][raw_course]:
                        current_day["courses"][raw_course][raw_group] = []
            i += 1
            continue

        if current_day is None or current_course is None or not group_cols:
            i += 1
            continue

        if not any(c.strip() for c in row):
            i += 1
            continue

        time_str = row[1].strip() if len(row) > 1 else ""
        pair_str = row[2].strip() if len(row) > 2 else ""

        has_pair = False
        if pair_str.isdigit():
            has_pair = True
        elif re.search(r"\d+\s*пара", time_str, re.I):
            has_pair = True
        elif time_str and re.match(r"\d{1,2}[:.]\d{2}", time_str):
            has_pair = True

        if has_pair:
            teacher_row = []
            if i+1 < len(lines):
                tr = [c.strip() for c in lines[i+1]]
                tr_time = tr[1].strip() if len(tr)>1 else ""
                tr_pair = tr[2].strip() if len(tr)>2 else ""
                if not tr_time and not tr_pair:
                    teacher_row = tr

            pair_num = pair_str if pair_str.isdigit() else ""
            if not pair_num:
                m = re.search(r"(\d+)\s*пара", time_str, re.I)
                if m:
                    pair_num = m.group(1)

            time_range = ""
            mtime = re.search(r"(\d{1,2}[:.]\d{2}\s*[-–]\s*\d{1,2}[:.]\d{2})", time_str)
            if mtime:
                time_range = mtime.group(1).replace(".", ":").replace(" ", "")
            elif re.match(r"\d{1,2}[:.]\d{2}", time_str):
                time_range = time_str.replace(".", ":")

            for col_idx, groups in group_cols:
                subj = row[col_idx].strip() if col_idx < len(row) else ""
                room = row[col_idx+1].strip() if col_idx+1 < len(row) else ""
                teacher = teacher_row[col_idx].strip() if teacher_row and col_idx < len(teacher_row) else ""
                if not subj:
                    continue
                lesson = {
                    "pair": int(pair_num) if pair_num.isdigit() else 0,
                    "time": time_range or time_str,
                    "subject": subj,
                    "room": room,
                    "teacher": teacher,
                }
                for g in groups:
                    current_day["courses"][g].append(lesson) if False else current_day["courses"][current_course][g].append(lesson)

            if teacher_row:
                i += 2
            else:
                i += 1
            continue
        else:
            i += 1
            continue

    # сортировка и конвертация defaultdict -> dict
    for day in days:
        for course in day["courses"]:
            for g in day["courses"][course]:
                day["courses"][course][g] = sorted(day["courses"][course][g], key=lambda x: x["pair"])
        day["courses"] = dict(day["courses"])
        # убрать пустые дни (без курсов)
        # но оставляем хотя бы один

    # фильтруем дни без курсов
    days = [d for d in days if d["course_order"]]

    # если дней не нашлось — fallback к старому поведению
    if not days:
        days = [{"date": "сегодня", "courses": {}, "course_order": []}]

    # дедупликация по дате если дубли (иногда первая дата дублируется)
    # но оставляем как есть — разные дни с одинаковой датой считаются разными если курсы отличаются

    result = {"days": days, "dates": [d["date"] for d in days]}
    # для обратной совместимости также кладем поля первого дня как раньше
    if days:
        first = days[0]
        result["courses"] = first["courses"]
        result["course_order"] = first["course_order"]
        result["date"] = first["date"]
    _cache[campus_key] = (now, result)
    return result

# обёртка для старого кода
def parse_campus(campus_key: str):
    return parse_campus_multi(campus_key)

def get_dates(campus_key):
    data = parse_campus_multi(campus_key)
    return data["dates"]

def get_courses(campus_key, date_idx=None):
    data = parse_campus_multi(campus_key)
    if date_idx is None or not data["days"]:
        # для совместимости без даты — первый день
        return data["days"][0]["course_order"] if data["days"] else []
    try:
        idx = int(date_idx)
        return data["days"][idx]["course_order"]
    except:
        return []

def get_groups(campus_key, course, date_idx=None):
    data = parse_campus_multi(campus_key)
    if not data["days"]:
        return []
    try:
        idx = 0 if date_idx is None else int(date_idx)
        return sorted(data["days"][idx]["courses"].get(course, {}).keys())
    except:
        return []

def get_schedule(campus_key, course, group, date_idx=None):
    data = parse_campus_multi(campus_key)
    if not data["days"]:
        return [], "сегодня"
    idx = 0 if date_idx is None else int(date_idx)
    try:
        day = data["days"][idx]
    except:
        day = data["days"][0]
        idx = 0
    return day["courses"].get(course, {}).get(group, []), day["date"]

def format_schedule(group, lessons, date_str, campus_name):
    if not lessons:
        return f"📭 <b>Для группы {group} на {date_str} пар нет</b>\n<i>{campus_name}</i>\n\nВозможно выходной или данные ещё не внесли."

    header = f"📅 <b>Расписание для {group}</b>\n"
    header += f"<i>{campus_name} • {date_str}</i>\n"
    header += "─" * 24 + "\n"

    nums = ["0️⃣","1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    def num_e(p):
        if p == 0:
            return "⭐"
        if 0 <= p < len(nums):
            return nums[p]
        return f"{p}⃣"

    lines = [header]
    for idx, les in enumerate(lessons):
        p = les["pair"]
        subj = les["subject"]
        teacher = les["teacher"]
        room = les["room"]
        t = les["time"]

        block = f"{num_e(p)} <b>{subj}</b>\n"
        if teacher:
            block += f"   👤 <i>{teacher}</i>\n"
        if room:
            if room.lower() in ("дист","дистант","дист."):
                block += f"   💻 <code>Дистант</code>"
            elif "чапаева" in room.lower() or "пушк" in room.lower():
                block += f"   📍 <code>{room}</code>"
            else:
                block += f"   🚪 <code>ауд. {room}</code>"
            if t:
                block += f" • ⏰ {t}\n"
            else:
                block += "\n"
        else:
            if t:
                block += f"   ⏰ {t}\n"

        if idx < len(lessons) - 1:
            br = 40 if p == 2 else 10
            block += f"   <i>— перерыв {br} мин —</i>\n\n"
        else:
            block += "\n"
        lines.append(block)

    lines.append(f"🔄 <i>Обновлено автоматически • {campus_name}</i>")
    return "".join(lines)
