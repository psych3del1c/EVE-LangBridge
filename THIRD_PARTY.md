# Сторонние компоненты

EVE LangBridge использует следующие компоненты и данные. Их авторы
и лицензии перечислены ниже.

## Код и библиотеки

| Компонент | Лицензия | Как используется |
|---|---|---|
| [llama.cpp](https://github.com/ggml-org/llama.cpp) | MIT | движок `llama-server`, скачивается при первом запуске |
| [customtkinter](https://github.com/TomSchimansky/CustomTkinter) | MIT | элементы интерфейса |
| [pystray](https://github.com/moses-palmer/pystray) | LGPL-3.0 | значок в системном трее |
| [Pillow](https://python-pillow.org/) | HPND | иконки и картинки |
| [openai-python](https://github.com/openai/openai-python) | Apache-2.0 | клиент OpenAI-совместимого API |
| [chardet](https://github.com/chardet/chardet) | LGPL-2.1 | определение кодировки логов |
| [Python](https://www.python.org/) | PSF License | среда выполнения |
| [Inno Setup](https://jrsoftware.org/isinfo.php) | бесплатная лицензия | установщик для Windows |

## Модели

Модели не входят в поставку, а скачиваются с HuggingFace по выбору
пользователя:

| Модель | Лицензия |
|---|---|
| [tencent/Hy-MT2-1.8B-GGUF](https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF) | Apache-2.0 |
| [bartowski/Qwen_Qwen3-1.7B-GGUF](https://huggingface.co/bartowski/Qwen_Qwen3-1.7B-GGUF) | Apache-2.0 |

## Данные EVE Online

Названия предметов, кораблей, систем и регионов собраны из статического
экспорта данных (SDE), который публикует CCP Games. Файл `eve_terms.json`
генерируется скриптом `build_terms.py`.

EVE Online и все связанные названия — торговая марка CCP hf.
Это приложение не связано с CCP и не одобрено ею.
