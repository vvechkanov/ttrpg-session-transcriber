# ADR-013: GigaAM speech backend — независимый модуль с собственным VAD

## Decision

`GigaAMSource` реализуется как полностью самодостаточный модуль в
`sources/speech/gigaam.py`. Все runtime-зависимости модуля (GigaAM encoder/
decoder/joiner, tokens, Silero VAD, hotwords) живут в одном каталоге
`<models_root>/gigaam/<variant>-<precision>/` и управляются самим модулем
через `Installable` Protocol. Shared инфраструктуры для VAD или download
между source-ами НЕ создаётся.

## Context

При проектировании GigaAM backend-а рассмотрены три варианта размещения
Silero VAD:

1. **Shared `sources/_infra/vad/silero.py`** — общий VAD для всех будущих
   ASR backend-ов.
2. **Core service `core/vad_service.py`** — централизованный VAD по
   запросу, один файл `silero_vad.onnx` на проект.
3. **Внутренняя деталь модуля** — `silero_vad.onnx` живёт в каталоге
   GigaAM, импортируется только из `gigaam.py`.

## Выбрано — вариант 3. Обоснование.

- **Один потребитель.** `faster-whisper` получает VAD от `ctranslate2`
  через `vad_filter=True`; WhisperX — свой pyannote-based VAD. На момент
  P2 единственный клиент Silero — GigaAM. Shared инфраструктура для
  одного клиента — преждевременное обобщение (YAGNI, принцип из
  `ARCHITECTURE.md`).
- **Независимость модуля upgrade-а.** GigaAM bundle может включать
  specific-версию Silero ONNX (совместимость с тренированным VAD
  threshold tuning). Shared Silero значит что апгрейд GigaAM может
  сломать faster-whisper или будущие модули.
- **Размер overhead тривиален.** `silero_vad.onnx` ~2 MB. Если завтра
  появится второй потребитель — он получит свою копию. 4 MB на диске
  дешевле чем shared-инфраструктурный слой.
- **Установка как единый atomic action.** `GigaAMSource.install()` знает
  что выкачать именно эти файлы вместе, в одну директорию, одной
  версией. Распределённое владение ("VAD качается core-сервисом,
  модель — source-ом") усложняет reindex-ы и rollback.

## Consequences

- (+) Каждый speech backend полностью автономен. Добавление/удаление
  backend не трогает соседей.
- (+) `sources/_infra/` или `sources/_shared/` не создаётся (нет
  преждевременной абстракции).
- (+) `Installable` Protocol (`sources/base.py`) — единственный общий
  контракт, и он тоже тривиален (три метода).
- (+) Тестирование проще: fake `models_root` per test, без координации
  с другими backend-ами.
- (−) Если в P6+ появится второй потребитель Silero (например
  `sources/emotion/ru_speech_emotion.py`), будет две копии onnx файла
  (4 MB вместо 2). Acceptable.
- (−) Если GigaAM и будущий backend захотят разные версии Silero —
  проблема решается автоматически (каждый качает свою). Если одну —
  дублирование. Пересмотрим только когда будет конкретный 2-й
  потребитель.

## Trigger для пересмотра

- Появился 2-й or 3-й `Installable` source, который использует Silero, И
- Все они согласны на одну и ту же версию Silero, И
- Размер модели > 20 MB (тогда 3x копии = 60 MB, что уже заметно).

Только при всех трёх условиях одновременно — вводим `sources/_infra/vad/`.
