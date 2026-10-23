from aiogram.fsm.state import State, StatesGroup


class Input(StatesGroup):
    filter_name = State()
    filter_field = State()
    budget_field = State()
    notify_field = State()
