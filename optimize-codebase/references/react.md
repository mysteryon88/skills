# React: пользовательская задержка, память, bundle

Установи React/version, framework/bundler, compiler configuration, development/production/production-profiling mode, StrictMode, SSR/RSC и клиентские границы. Не превращай проект в Next.js ради применения рецепта из Next.js.

## Измерения

React Profiler нужен для атрибуции рендеров, а не для заявления end-to-end latency. `actualDuration` относится к рендеру subtree; `baseDuration` является оценкой. Commit/paint, сеть и browser work измеряются отдельно. Profiler добавляет overhead; для production profiling нужна специальная сборка с profiling, обычная production-сборка отключает его по умолчанию. Development profiling такой production-сборки не требует. Сравнивай одинаковую instrumentation. Пользовательский выигрыш подтверждай обычной production сборкой на представительных устройствах.

Запиши сценарий click/type/scroll → видимый результат, p50/p95 событий при достаточной выборке, long tasks, количество/размер запросов, переданный сжатый JS, parsed JS и retained heap. Условный Node benchmark для чистой функции не является тестом React rendering/INP. Development/StrictMode timings не подменяют shipped production.

## Порядок поиска

Сначала network waterfalls и лишние запросы, затем bundle/serialization, затем объём рендеринга и вычисления. Используй существующий profiler/browser harness. Не скачивай инструменты, не создавай реальных рассылок/платежей и не отправляй пользовательские данные.

| Сигнал | Кандидат | Риск |
|---|---|---|
| Независимые await последовательно | Параллельный запуск с ограничением | Failure/cancellation/order, upstream load, RAM |
| Большой редко используемый код | Dynamic import и граница загрузки | Chunk waterfall, SSR/hydration, export semantics |
| Повторный поиск данных | Lookup map/предвычисление | Создание map, duplicate semantics, invalidation |
| Дорогие rerenders | Локализовать state, стабилизировать осмысленные props | Stale closure, лишний retained cache |
| Огромный DOM | Virtualization/visible subtree | Focus, accessibility, search, scroll state |
| Слишком много client props | Передавать нужные данные | SSR/client contracts, auth boundary |

Ручной useMemo вводи только после измерения. Calculation должна быть чистой; dependencies содержат все reactive values, имеют постоянную длину и проверяются lint. Тестируй смену каждой зависимости, mount/unmount, suspend/retry и StrictMode. Кэш может быть отброшен React, поэтому корректность не должна зависеть от его наличия/identity. Оцени retained memory и hit/miss/частоту смены dependencies. Проверь, не делает ли нужное уже React Compiler. Нельзя ставить useMemo/useCallback/memo повсюду по одному статическому признаку.

Не сохраняй межпользовательские данные в глобальном unbounded Map. Для кэша зафиксируй размер, eviction, lifetime, invalidation и tenant/auth key. TTL/consistency менять нельзя без отдельного решения. Переход на Map должен сохранить первый/последний duplicate и equality исходного кода: Map и === имеют нюансы, например NaN.

Для больших бинарных наборов рассмотрим TypedArray, но Number-bitwise имеет 32-битную семантику. Большие индексы нельзя вычислять через `i >> 5` без ограничения диапазона. Для BigInt и TypedArray отдельно проверь serialization/JSON и React immutability. Не изменяй буфер под прежней ссылкой так, чтобы memo/React не заметили обновление.

Источники: [VERCEL], [REACT-PROFILER], [REACT-MEMO], [ECMA-BITS].
