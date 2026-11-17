# Rust: данные, владение, сборка

Фиксируй `rustc -Vv`, Cargo.lock, target triple/CPU features, Cargo profile, RUSTFLAGS, config overrides, allocator, feature set. Сравнивай одинаковые режимы; `dev` против `release` не доказывает улучшение алгоритма. Тесты границ/ошибок выполняй также с production profile.

После проверки scripts/build.rs и локальной среды выбирай существующие проверки, например `cargo test --locked --offline`, `cargo test --release --locked --offline`, `cargo clippy --locked --offline`. Сначала настрой CARGO_TARGET_DIR и temporary/output paths внутри проектного .tmp по [интеграции](integration.md). Offline требует уже имеющихся зависимостей; при отсутствии не скачивай их молча. `cargo test --release` проверяет release-оптимизации, но test harness игнорирует профильный `panic=abort` и использует unwind; production panic-поведение при необходимости проверяй отдельно. `cargo bench` запускай только с известным harness/профилем проекта. `std::hint::black_box` препятствует некоторым оптимизациям benchmark, но не доказывает корректность измерения.

| Узкое место | Кандидат | Проверка обратной стороны |
|---|---|---|
| Лишние clone/owned strings | Borrow, &str/&[T], Cow там, где владение условно | Borrow может удерживать весь исходный большой буфер; concurrency/lifetime |
| Рост Vec/String | Ограниченное with_capacity, reuse, clone_from | Capacity/retention, вход не должен диктовать безлимитную allocation |
| Pointer chasing | Vec/arena/индексы, SoA для нужных полей | Удаление, стабильность адресов, locality при другом доступе |
| Большой enum/объект | Выделить крупный редкий payload, сократить representation | Новая allocation/indirection; size_of на целевой платформе |
| Повторные проходы | Устранить ненужный collect, entry вместо двойного поиска | Порядок, side effects iterator, lazy evaluation |
| Бинарник | Анализ мономорфизации/зависимостей, LTO/профиль как отдельный эксперимент | Build time, runtime, совместимость CPU, диагностика |

Нельзя автоматически включать `panic=abort`, менять overflow-checks, debug-assertions, отключать bounds checks, добавлять unsafe/repr(packed) или `target-cpu=native`. Это может менять контракты, безопасность или переносимость. Даже разрешённые flags сравнивай отдельно с теми же features/входами и тестами. «Больше opt-level» не гарантирует меньше времени или размер.

Не считай Vec<bool> упакованным bit-vector по аналогии с C++. Не делай layout сериализацией по умолчанию: явный byte format и versioning важнее `size_of`. Для плотных булевых наборов возможно Vec<u64>, но проверь tail bits, bounds, endian, update/race semantics и полную цену преобразований.

SmallVec, компактные строки, compressed bitmap и arena являются кандидатами только после профиля и с одобрением новых зависимостей. Inline payload уменьшает heap allocations, но увеличивает размер содержащего объекта; размер массива inline не выбирается «на глаз».

Если задача касается хранения сборки, отдельно замерь конечный executable, target/incremental/dependency artifacts, clean build и incremental rebuild. Уменьшение бинарника не означает меньший build cache. Не удаляй кэши пользователя ради цифры.

Источники: [RUST-SKILL], [RUST-PROFILES], [RUST-BLACKBOX], [RUST-ALLOC], [RUST-SIZE]. Пример в examples/rust дан для локальной проверки; факт его выполнения см. VALIDATION.md.
