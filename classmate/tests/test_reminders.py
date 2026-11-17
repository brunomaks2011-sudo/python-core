from datetime import datetime, timezone


def at(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=timezone.utc)


def kinds(client):
    return sorted(n["kind"] for n in client.get("/api/notifications").get_json()["items"])


def test_day_before_and_due_today_respect_chosen_time(classroom, clock):
    anya, petya = classroom["anya"], classroom["petya"]
    petya.patch("/api/me", json={"reminderTime": "18:00", "notifyNew": False})
    anya.post("/api/homework", json={"subject": "Физика", "description": "§5", "dueDate": "2026-11-18"})

    clock["now"] = at(17, 17, 59)
    assert kinds(petya) == []
    clock["now"] = at(17, 18, 0)
    assert kinds(petya) == ["day_before"]
    assert kinds(petya) == ["day_before"]  # повторная проверка не дублирует

    clock["now"] = at(18, 9, 0)
    assert kinds(petya) == ["day_before"]
    clock["now"] = at(18, 18, 30)
    assert kinds(petya) == ["day_before", "due_today"]


def test_reminders_use_user_timezone(classroom, clock):
    anya, petya = classroom["anya"], classroom["petya"]
    petya.patch("/api/me", json={"reminderTime": "18:00", "notifyNew": False, "timezone": "Asia/Vladivostok"})
    anya.post("/api/homework", json={"subject": "Химия", "description": "Опыт", "dueDate": "2026-11-18"})
    # 08:00 UTC = 18:00 во Владивостоке (UTC+10) 17 ноября.
    clock["now"] = at(17, 8, 0)
    assert kinds(petya) == ["day_before"]


def test_completed_homework_is_not_reminded(classroom, clock):
    anya, petya = classroom["anya"], classroom["petya"]
    petya.patch("/api/me", json={"notifyNew": False})
    hw = anya.post("/api/homework", json={"subject": "ИЗО", "description": "Рисунок", "dueDate": "2026-11-18"}).get_json()
    petya.put(f"/api/homework/{hw['id']}/done", json={"done": True})
    clock["now"] = at(17, 23, 0)
    assert kinds(petya) == []


def test_disabled_reminders_and_scheduler(app, classroom, clock):
    from reminders import ReminderScheduler

    anya, petya = classroom["anya"], classroom["petya"]
    petya.patch("/api/me", json={"remindDayBefore": False, "notifyNew": False})
    anya.post("/api/homework", json={"subject": "Музыка", "description": "Песня", "dueDate": "2026-11-18"})
    clock["now"] = at(17, 20, 0)
    scheduler = ReminderScheduler(app.config["DB_PATH"], app.extensions["push"], lambda: clock["now"])
    created = scheduler.run_once()
    # Аня и администратор получили «за день», Петя отключил этот вид напоминаний.
    assert len(created) == 2
    assert kinds(petya) == []


def test_changing_due_date_resets_reminders(classroom, clock):
    anya = classroom["anya"]
    hw = anya.post("/api/homework", json={"subject": "Литература", "description": "Стих", "dueDate": "2026-11-18"}).get_json()
    clock["now"] = at(17, 19, 0)
    assert kinds(anya) == ["day_before"]
    anya.put(f"/api/homework/{hw['id']}", json={"subject": "Литература", "description": "Стих", "dueDate": "2026-11-20"})
    assert kinds(anya) == []
