# SQL: запросы, хранение и цена записи

Определи engine и точную версию. PostgreSQL, MySQL, SQLite и другие движки имеют разные планы, типы и DDL. Команды PostgreSQL ниже не переносятся вслепую.

## Безопасный вход

По умолчанию рассматривай SQL и существующий planning-only EXPLAIN. Новое выполнение запроса даже с EXPLAIN требует проверенной изолированной среды. `EXPLAIN ANALYZE` действительно исполняет statement. Разрешай его только в disposable стенде с синтетическими/обезличенными данными после проверки statement и вызываемых функций. SELECT/EXECUTE могут иметь внешние эффекты; read-only transaction/ROLLBACK не являются полной песочницей. Неизвестные функции, CREATE TABLE AS, EXECUTE и materialized-view операции не запускать автоматически.

Пример для **проверенного безопасного SELECT в disposable PostgreSQL**:

```sql
EXPLAIN (FORMAT JSON, SETTINGS) SELECT ...;
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SETTINGS, FORMAT JSON) SELECT ...;
```

Прочитай поддержку options в версии проекта. EXPLAIN cost не время. Plan instrumentation имеет overhead, а TIMING OFF не делает его обычным application request. Для основного результата отдельно меряй нормальный клиентский путь, fetch/serialization/round trips и concurrency. Планы сравнивай с одинаковыми options/параметрами/cache state.

## Контекст плана

Зафиксируй данные/распределение параметров, statistics freshness/ANALYZE policy, snapshot статистики, planner settings, версию и generic/custom prepared plan. Регенерация статистики только у candidate портит сравнение. Изменение плана без контролируемого состояния не приписывай переписыванию SQL. Тестируй частые и редкие параметры, а не один удачный tenant.

## Направления оптимизации

| Сигнал | Кандидат | Обязательная проверка |
|---|---|---|
| N+1 и много round trips | Join/batch/предзагрузка нужного | Дубли, NULL, права, cardinality, peak memory |
| Сканирование большой таблицы | Подходящий composite/partial/expression/covering index | Plan, селективность, размер индекса, write/WAL cost |
| SELECT * / огромный JSON | Нужные столбцы, перенос фильтра ближе к данным | API schema, TOAST/IO, serializer cost |
| Большой OFFSET | Keyset на устойчивом уникальном порядке | Сортировка/NULL, concurrent changes, прежний pagination contract |
| Spill/temp IO | Уменьшить строки/сортировку/агрегацию, правильный индекс | work_mem на узел × workers × sessions |
| Bloated storage | Диагностика таблиц/индексов/TOAST и жизненного цикла | Locks, vacuum/rewrite, replica/backup/migration safety |

Индекс не бесплатен: измерь размер таблицы+индексов, время/объём insert/update/delete, WAL и место временной миграции при PostgreSQL. Только чтение быстрее не означает системный выигрыш. Добавление/удаление индекса оформляется миграцией для review; на рабочей БД автоматически не выполняется. Даже CONCURRENTLY имеет ограничения и влияние, это не разрешение на production DDL.

Для PG сравни `pg_table_size`, `pg_indexes_size`, `pg_total_relation_size` по точной версии. Размер логического JSON или `pg_column_size` одной строки не заменяет полный footprint. SQLite page_count×page_size измеряет страницы SQLite-файла, не PostgreSQL и не размер WAL/backup.

Не сокращай TEXT до малых числовых/битовых типов без доказанных диапазонов, NULL-модели, старых читателей, миграции и обратимости. Битовая маска может сделать predicates/indexing хуже. Сохранение места в приложении не доказывает экономию SQL-таблицы из-за overhead и компрессии.

Никогда не выключай RLS, constraints, fsync, synchronous_commit, validation или isolation ради скорости. Не меняй LIMIT/order/distinct/join semantics так, чтобы «ускорение» получалось пропуском работы.

Источники: [SUPABASE], [PG-EXPLAIN], [PG-SIZES], [PG-INDEX], [PG-TOAST], [PG-MEM], [PG-BITS].
