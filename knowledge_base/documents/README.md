# 📂 knowledge_base/documents/

Положи сюда PDF документы WB:

- **Оферта WB** (скачать: https://seller.wildberries.ru/legal)
- **Тарифы и условия** (из личного кабинета WB)
- **Инструкции по API WB**

Система автоматически:
1. Прочитает PDF при старте
2. Извлечёт термины и определения
3. Обогатит SmartMapper новыми знаниями
4. Поиск через API: GET /api/kb/search?q=кВВ

## Установка зависимостей для PDF:
```
pip install pdfplumber     # рекомендуется
# или
pip install pymupdf        # альтернатива
```
