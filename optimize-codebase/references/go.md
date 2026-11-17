# Go: CPU, память, IO

## Обнаружение и измерения

Сначала проверь `go version`, go.mod/toolchain, GOARCH/GOOS, build tags, CGO, CPU limits и GOMAXPROCS. Не используй новую API, пока версия проекта её не поддерживает. В примере пакета используется `b.N`; `b.Loop` требует подходящей версии.

Выбирай команды из проекта. До запуска настрой `$work`, TEMP/TMP/TMPDIR и Go cache/output paths по [примеру](examples.md#сначала-выбери-рабочий-каталог). В локальном стенде без внешних эффектов типовой набор:

```bash
go test ./path/to/package
go test -race ./path/to/package
go test -run '^$' -bench '^BenchmarkTarget$' -benchmem -count 10 ./path/to/package
go test -run '^$' -bench '^BenchmarkTarget$' -o "$work/profile.test" -outputdir "$work" -cpuprofile "$work/cpu.out" -memprofile "$work/mem.out" ./path/to/package
go tool pprof -top "$work/cpu.out"
go tool pprof -alloc_space -top "$work/mem.out"
go tool pprof -inuse_space -top "$work/mem.out"
```

Профилирование выполняй отдельно от измерения обычного времени. Недоступные race/pprof проверки отмечай. Не публикуй net/http/pprof в интернет. Не ставь benchstat или другой инструмент без разрешения; при отсутствии не выдумывай его результат.

## Кандидаты по профилю

| Сигнал | Что попробовать | Что может ухудшиться |
|---|---|---|
| Аллокации/copies на горячем пути | Предвыделение по достоверной ограниченной длине, reuse buffer, типизированный formatting, потоковый IO | Завышенная capacity, удержание больших backing arrays, aliasing |
| Повторный поиск/парсинг | Индекс по ключу, устранение дублированной работы, заранее подготовленный неизменяемый объект | Память/подготовка, правила invalidation, stale data |
| Давление GC | Меньше краткоживущих объектов и pointer-rich структур | Изменение lifetime, рост retained heap |
| CPU/cache misses | Непрерывные массивы, плотный bitset, data-oriented layout | Сложность обновлений, false sharing, цена упаковки |
| Ожидание IO | Batch/stream, корректное reuse соединений, ограниченная конкурентность | Пиковая память, порядок/транзакции, нагрузка downstream |
| Locks/goroutines | Mutex/block/trace и сокращение секции/очереди | Races, starvation, потеря cancellation/backpressure |

`sync.Pool` не является постоянным кэшем и не гарантирует наличие объектов. Ограничивай сохраняемую capacity; reset не должен оставлять приватные данные или ссылки. Перевод string/bytes через unsafe без копирования не входит в автономный безопасный режим.

## RAM: отдельная проверка

Для заявления о RAM измеряй peak RSS и подходящие метрики runtime/живого heap под длительной представительной нагрузкой. Фиксируй GOGC/GOMEMLIMIT, GC activity, phase, concurrency. `B/op` и `allocs/op` оставляй диагностикой аллокаций. Уменьшение GC за счёт более живучего кэша может повысить RAM.

GOMEMLIMIT — мягкий лимит учитываемой runtime памяти, а не жёсткий предел всего RSS. Не подставляй универсальный процент от памяти контейнера. Тюнинг GC меняет баланс CPU/память и требует нагрузочного замера. Советы про escape/inlining относятся к конкретным implementation+toolchain; после обновления Go прежний выигрыш проверяется заново.

Перестановка struct fields требует проверки layout, atomics alignment, unsafe/FFI/serialization/reflection и source compatibility. Она не применяется по одной подсказке линтера.

Источники: [GO-SKILL], [GO-DIAG], [GO-GC], [GO-PPROF], [BENCHSTAT].
