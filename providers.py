"""Бэкенды перевода.

Все общаются по OpenAI-совместимому протоколу, поэтому один и тот же
код работает с LM Studio, Ollama и встроенным llama.cpp. Новый бэкенд
добавляется наследником Backend и строкой в BACKEND_CLASSES.
"""

from urllib.parse import urlsplit

from openai import OpenAI, BadRequestError


class BackendError(RuntimeError):
    """Бэкенд не ответил или вернул ошибку."""


def normalize_base_url(url, default):
    """Приводит адрес к виду .../v1, не ломая нестандартные пути."""
    url = (url or "").strip().rstrip("/")
    if not url:
        url = default
    if urlsplit(url).path in ("", "/"):
        url += "/v1"
    return url


class Backend:
    """Общий интерфейс. Модель, температура и лимит токенов — здесь же,
    чтобы движку перевода не приходилось знать про конкретный сервер."""

    kind = "openai"
    label = "OpenAI"
    default_base_url = "http://localhost:8080/v1"
    default_api_key = "none"
    # True у бэкендов, которые сами поднимают сервер (встроенный движок).
    managed = False

    def __init__(self, base_url=None, api_key=None, model="",
                 temperature=0.5, max_tokens=300, extra_body=None):
        self.base_url = normalize_base_url(base_url, self.default_base_url)
        self.api_key = (api_key or "").strip() or self.default_api_key
        self.model = (model or "").strip()
        self.temperature = float(temperature)
        self.max_tokens = int(max_tokens)
        self.extra_body = extra_body or None
        self._client = None

    # ---------- жизненный цикл ----------
    def start(self):
        """Поднять сервер (нужно только встроенному движку)."""

    def stop(self):
        """Остановить сервер (нужно только встроенному движку)."""

    # ---------- работа ----------
    @property
    def client(self):
        if self._client is None:
            # max_retries=0: локальный сервер либо отвечает, либо нет.
            # Иначе недоступный LM Studio тормозит запуск на ~10 секунд.
            self._client = OpenAI(base_url=self.base_url,
                                  api_key=self.api_key, max_retries=0)
        return self._client

    def list_models(self, timeout=3.0):
        """Список моделей сервера. Пустой список, если сервер недоступен."""
        try:
            models = self.client.with_options(timeout=timeout).models.list()
            return sorted(m.id for m in models.data)
        except Exception:
            return []

    def chat(self, messages, temperature=None, max_tokens=None, timeout=120.0):
        """Один запрос к модели. Возвращает текст ответа."""
        if not self.model:
            raise BackendError("Модель не выбрана")
        try:
            response = self._create(messages, temperature, max_tokens,
                                    timeout, self.extra_body)
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(str(exc)) from exc
        return (response.choices[0].message.content or "").strip()

    def _create(self, messages, temperature, max_tokens, timeout, extra_body):
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": (self.temperature if temperature is None
                            else temperature),
            "max_tokens": (self.max_tokens if max_tokens is None
                           else max_tokens),
        }
        if extra_body:
            kwargs["extra_body"] = extra_body
        try:
            return self.client.with_options(
                timeout=timeout).chat.completions.create(**kwargs)
        except BadRequestError:
            # Старые сборки llama-server не знают chat_template_kwargs —
            # повторяем запрос без них, чтобы не терять перевод.
            if not extra_body:
                raise
            kwargs.pop("extra_body", None)
            return self.client.with_options(
                timeout=timeout).chat.completions.create(**kwargs)
        except Exception as exc:
            raise BackendError(str(exc)) from exc

    # ---------- конфиг и отображение ----------
    def to_config(self):
        return {
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model": self.model,
        }

    def describe(self):
        return f"{self.label} · {self.model or '—'}"


class LMStudioBackend(Backend):
    kind = "lmstudio"
    label = "LM Studio"
    default_base_url = "http://localhost:1234/v1"
    default_api_key = "lm-studio"


class OllamaBackend(Backend):
    kind = "ollama"
    label = "Ollama"
    default_base_url = "http://localhost:11434/v1"
    default_api_key = "ollama"


class OpenAICompatibleBackend(Backend):
    kind = "openai"
    label = "OpenAI-совместимый API"
    default_base_url = "http://localhost:8080/v1"
    default_api_key = "none"


class LocalLlamaBackend(Backend):
    """Встроенный движок: llama-server + GGUF из local_engine."""

    kind = "builtin"
    label = "Встроенный движок"
    default_base_url = "http://127.0.0.1:1/v1"
    default_api_key = "local"
    managed = True

    def __init__(self, engine, model_id="", context=1024, threads=0,
                 gpu_layers="auto", **kwargs):
        from local_engine import DEFAULT_MODEL_ID, MODEL_CATALOG

        self.engine = engine
        self.model_id = (model_id if model_id in MODEL_CATALOG
                         else DEFAULT_MODEL_ID)
        info = MODEL_CATALOG[self.model_id]
        self.context = int(context or info.get("context", 1024))
        self.threads = int(threads or 0)
        self.gpu_layers = gpu_layers
        super().__init__(base_url=self.default_base_url,
                         api_key=self.default_api_key,
                         model="local",
                         extra_body=info.get("extra_body"),
                         **kwargs)

    # ---------- жизненный цикл ----------
    def start(self):
        self.engine.start_async(self.model_id, self.context,
                                self.threads, self.gpu_layers)

    def stop(self):
        self.engine.stop()

    # ---------- работа ----------
    def _sync_base_url(self):
        url = self.engine.base_url
        if url and url != self.base_url:
            self.base_url = url
            self._client = None

    def list_models(self, timeout=3.0):
        # У встроенного движка модель одна, и её id на сервере — это путь
        # к файлу. Для интерфейса отдаём понятное имя из каталога.
        return [self.model_name()]

    def chat(self, messages, temperature=None, max_tokens=None, timeout=120.0):
        # Первое сообщение может прийти, пока модель ещё грузится.
        if not self.engine.wait_ready(timeout=60):
            raise BackendError(self.engine.message or "Движок не запустился")
        self._sync_base_url()
        return super().chat(messages, temperature=temperature,
                            max_tokens=max_tokens, timeout=timeout)

    # ---------- конфиг и отображение ----------
    def model_name(self):
        from local_engine import MODEL_CATALOG
        return MODEL_CATALOG[self.model_id]["name"]

    def describe(self):
        mode = {"gpu": "GPU", "cpu": "CPU"}.get(self.engine.mode, "")
        parts = [self.label, self.model_name()]
        if mode:
            parts.append(mode)
        return " · ".join(parts)

    def to_config(self):
        return {
            "model_id": self.model_id,
            "context": self.context,
            "threads": self.threads,
            "gpu_layers": self.gpu_layers,
        }


BACKEND_CLASSES = {
    LocalLlamaBackend.kind: LocalLlamaBackend,
    LMStudioBackend.kind: LMStudioBackend,
    OllamaBackend.kind: OllamaBackend,
    OpenAICompatibleBackend.kind: OpenAICompatibleBackend,
}

# Ключевые слова для выбора модели, если в конфиге стоит заглушка.
MODEL_HINTS = ("hy-mt", "translate", "instruct", "chat")


def backend_kinds():
    """[(kind, подпись)] — для выпадающего списка в настройках."""
    return [(kind, cls.label) for kind, cls in BACKEND_CLASSES.items()]


def create_backend(llm_cfg):
    """Собирает бэкенд из секции config["llm"]."""
    llm_cfg = llm_cfg or {}
    kind = str(llm_cfg.get("backend") or LMStudioBackend.kind).lower()
    cls = BACKEND_CLASSES.get(kind, LMStudioBackend)
    section = llm_cfg.get(kind)
    if not isinstance(section, dict):
        section = {}
    common = dict(
        temperature=llm_cfg.get("temperature", 0.5),
        max_tokens=llm_cfg.get("max_tokens", 300),
    )
    if kind == LocalLlamaBackend.kind:
        from local_engine import LocalEngine
        return cls(
            engine=LocalEngine(),
            model_id=section.get("model_id") or "",
            context=section.get("context", 1024),
            threads=section.get("threads", 0),
            gpu_layers=section.get("gpu_layers", "auto"),
            **common,
        )
    return cls(
        base_url=section.get("base_url") or cls.default_base_url,
        api_key=section.get("api_key") or cls.default_api_key,
        model=section.get("model") or "",
        **common,
    )


def store_backend_config(llm_cfg, backend):
    """Переносит текущие настройки бэкенда обратно в config["llm"]."""
    llm_cfg["backend"] = backend.kind
    section = llm_cfg.setdefault(backend.kind, {})
    section.update(backend.to_config())


def resolve_model(backend, preferred=None):
    """Выбирает модель: сначала заданную, иначе «переводческую» из списка."""
    names = backend.list_models()
    preferred = (preferred or backend.model or "").strip()
    if not names:
        return preferred
    if preferred and preferred in names:
        return preferred
    usable = [n for n in names if "embed" not in n.lower()]
    if not usable:
        return names[0]
    for keyword in MODEL_HINTS:
        for name in usable:
            if keyword in name.lower():
                return name
    return usable[0]
