# Синтетические проверки методов

Прочитай исходники перед запуском. Здесь нет сетевых клиентов и пользовательских
БД. Эти примеры проверяют отдельные методы, а не производительность вашего проекта.
Команды выполняются из корня skill, который может отличаться от корня проекта.
Примеры ниже рассчитаны на Bash в Linux/WSL. Следуй выбранному проектом runtime;
на Windows с WSL-default сначала явно выбери дистрибуцию/cwd по [интеграции](integration.md).

## Сначала выбери рабочий каталог

В Bash укажи реальный корень проекта и предварительно проверь его физический путь:

```bash
project_root=/absolute/path/to/project
work="$project_root/.tmp/optimize-codebase"
mkdir -p "$work" "$work/go-cache" "$work/go-tmp" "$work/go-modcache" "$work/go-path"
export TEMP="$work" TMP="$work" TMPDIR="$work"
export GOCACHE="$work/go-cache" GOTMPDIR="$work/go-tmp"
export GOMODCACHE="$work/go-modcache" GOPATH="$work/go-path"
```

Это пример для уже проверенного каталога без перенаправленных ancestors.
Для PowerShell настрой те же process-scoped переменные и явные пути вывода.
Не используй /tmp или текущую папку как неявный путь build/profile output.

## Go

Из `examples/go` при уже установленном Go:

```bash
GO111MODULE=off GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off GOTELEMETRY=off go test -v
```

Если проект поддерживает race detector и компилятор уже есть, отдельно запусти
ту же проверку с `-race`. Benchmark — отдельное разрешённое измерение; чередуй
Bytes/Packed в соседних AB/BA запусках, не запускай их параллельно.
Count читает подготовленное представление; Lifecycle включает copy/pack и 20
подсчётов с общим исходным input. B/op не равен RSS. Bitset helpers не являются
парсером произвольного непроверенного бинарного формата.

## JavaScript

`node examples/js/check.mjs` проверяет lookup semantics и печатает 12 пар.
Поддерживаются finite integer/string IDs; для дублей возвращается первый объект.
Map construction входит в candidate timing. Это не React/browser или RAM-тест;
результат остаётся CPU-гипотезой до измерения остальных существенных ограничений.

## SQLite

`python3 -B examples/sql/check_sqlite.py` создаёт synthetic SQLite-базы внутри
настроенного temporary каталога, проверяет 24 набора SELECT и размер страниц.
Соединения закрываются до очистки. Индекс ускоряет отдельные чтения ценой хранения;
нулевой storage budget отклоняет этот вариант. PostgreSQL, RAM, WAL, запись и
production-нагрузка этим примером не проверяются.

## Rust

Из корня skill при уже установленном rustc:

```bash
rustc --edition=2021 --test examples/rust/flags.rs -o "$work/flags-tests"
"$work/flags-tests"
```

Выбери свободное имя без перезаписи чужого файла; на Windows используй .exe.
Флаги реального проекта и production panic strategy требуют отдельных проверок,
описанных в Rust-справочнике. Пакет не устанавливает toolchain автоматически.
