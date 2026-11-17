# Компактные данные: выбрать по workload, не по моде

## Плотные флаги

Для N независимых булевых значений в массиве с одним байтом на значение полезный payload равен N байтам. При упаковке по биту он равен ceil(N/8); хранение целыми 64-битными словами требует 8×ceil(N/64). Это арифметика payload, без длины, заголовков, capacity, allocator, validity map, индексов и обёрток.

Для 1 000 000 флагов: 1 000 000 байт против 125 000 байт полезных данных. Это НЕ обещание «весь процесс ест в 8 раз меньше». Текстовые JSON boolean/string и SQL storage имеют другой overhead; их размер измеряется отдельно.

Bitset особенно интересен для плотных ID, intersections/unions и popcount. Если установлен один ID с огромным номером, обычный плотный bitmap может проиграть sorted IDs/hash set/сжатой bitmap. Сравни реальную плотность, диапазон ID, частоту случайных updates и операции. Roaring и другие compressed bitmap требуют проверки workload и разрешения на зависимость, не являются универсальным выбором.

## Gate перед заменой representation

1. Установи домен: два состояния или true/false/null/unknown? Для nullable нужен дополнительный признак/bitmap, а не потеря состояния.
2. Зафиксируй bit numbering, ширину, длину и endian в сериализации; зарезервируй version/unknown bits. Не меняй внешние протоколы автоматически.
3. Проверь 0/1/word-1/word/word+1, отрицательные/слишком большие индексы, overflow при расчёте длины, хвостовые биты, malformed input и верхний лимит аллокации.
4. Сохрани read/update/clear semantics. Два потока, меняющие разные биты одного слова, всё равно могут конфликтовать. Нужны подходящие atomics/locks, но не самодельный lock-free код без доказательства.
5. Измерь pack/unpack, count/intersect, random reads/writes, allocation/retention и полный pipeline. Храни отдельно cold construction и steady-state.
6. Убедись в старом/новом reader compatibility. Миграция с dual-read/write требует отдельной задачи и проверки; skill не перекодирует production store без разрешения.

Для внешних форматов не сериализуй native struct memory как будто ABI стабилен. Go struct alignment и Rust repr(Rust) не являются portable wire format. JavaScript bitwise Number не является произвольной 64-битной арифметикой.

## Другие компактные представления

| Условия | Кандидат | Когда проигрывает |
|---|---|---|
| Небольшой диапазон integer | Проверенное сужение типа | Overflow/рост данных/ABI/nullability |
| Много повторяющихся строк | Dictionary IDs/interning с bounded lifetime | Высокая cardinality, глобальное удержание |
| Длинные одинаковые серии | RLE | Частые чередования и updates |
| Монотонные значения | Delta + varint/bit packing | Случайный доступ, отрицательные/крупкие дельты |
| Аналитические сканы по части полей | Columnar/SoA | Частые row updates, сборка целой записи |
| Повторяемый большой payload | Lossless compression с правильным block size | CPU/latency/random reads, incompressible input |
| Частые выборки/проверки membership | Индекс/map/bitmap | Дополнительное хранение и запись |

Упаковка до сжатия не гарантирует лучший итог. Сравни compressed bytes, CPU, decompression peak, latency и обратимость. Не вводи lossy quantization, Bloom false positives или truncated hashes вместо точного сравнения без отдельного изменения требований. Base64 увеличивает бинарный payload, поэтому победа «binary вместо JSON» должна учитывать фактический transport.

Храни компактное внутреннее представление за понятным интерфейсом: код не должен превращаться в россыпь необъяснённых masks. Комментарий фиксирует смысл битов и benchmark, а не обещание вечного ускорения.

Источники: [ROARING], [ARROW], [PROTOBUF], [PG-BITS], [ECMA-BITS]; математические примеры и gates являются синтезом для этого пакета.
