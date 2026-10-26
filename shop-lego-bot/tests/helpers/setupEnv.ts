// Імпортується першим у тестах: вимикає журнали та позначає тестове середовище.
process.env.NODE_ENV = "test";
process.env.LOG_LEVEL = process.env.TEST_LOG_LEVEL ?? "silent";
