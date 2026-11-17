# Каталог code smells и решений

Используй признаки как сигналы для чтения, а не как автоматические пороги.
Ни одна метрика сама по себе не доказывает, что код надо менять.

| Признак | Что проверить | Возможные приёмы |
|---|---|---|
| Long Method | Смешаны ли уровни абстракции, обязанности, IO и вычисления? | Extract Function, Split Phase |
| Deep Nesting | Можно ли применить guard clauses без изменения порядка эффектов? | Replace Nested Conditional |
| Long Parameter List | Являются ли параметры смысловой группой? | Introduce Parameter Object |
| Flag Argument | Выбирает ли boolean разные сценарии/контракты? | Split Function, Enum/Strategy |
| Repeated Switch | Повторяются ли ветви по типам? | Strategy, Polymorphism |
| Feature Envy | Функция чаще использует данные другого владельца? | Move Method |
| Side-effect soup | Перемешаны ли решения и IO? | Functional Core / Imperative Shell |
| God Object/Class | Несколько независимых причин изменения? | Extract Class/Module |
| Divergent Change | Один модуль меняется по несвязанным причинам? | Extract Module |
| Shotgun Surgery | Одно правило меняется в разных местах? | Move/Extract Module |
| Inappropriate Intimacy | Модули читают/меняют внутренности друг друга? | Encapsulate, ownership, seam |
| Pass-through Module | Слой только пересылает вызов? | Inline/Collapse Module |
| Speculative Generality | Абстракция существует ради гипотетического будущего? | Remove abstraction |
| Cyclic Dependency | Модули образуют цикл? | Invert dependency, stable contract |
| Duplicate Code | Совпадает бизнес-смысл или только текст? | Extract Function/Module |
| Data Clumps | Поля часто передаются совместно? | Parameter Object / Value Object |
| Primitive Obsession | Примитив кодирует доменное понятие с правилами? | Value Object / Newtype |
| Magic Literal | Значение имеет смысловое имя? | Extract Constant / Enum |
| Scattered Configuration | Настройка меняется в нескольких местах? | Configuration object |
| Mutable Shared State | Несколько владельцев меняют один объект? | Encapsulation, ownership |
| Hidden State Machine | Флаги образуют невозможные сочетания? | Tagged union / state machine |
| Temporal Coupling | Один метод допустим только после другого? | Explicit lifecycle / type-state |
| Hardcoded Dependency | Бизнес-логика сама создаёт DB/client/clock/SDK? | DI, adapter |
| External Type Leakage | Тип SDK проходит через бизнес-слои? | Anti-corruption layer |
| Error Leakage | Низкоуровневые ошибки протекают наружу? | Translate at module boundary |
| Unused Code | Проверены ли динамические callers/reflection/entrypoints и правила удаления? | Сохранить либо удалить после требуемого разрешения |

## Safe Abstraction Gate для дублирования

Перед объединением ответь:
1. Это одна бизнес-политика или только похожая реализация?
2. Изменяются ли оба фрагмента по одной причине?
3. Есть ли общее понятие/имя, честное для всех вызовов?
4. Сохраняются ли различия ошибок, прав, округления, defaults и side effects?
5. Не появятся ли caller-specific флаги и режимы?
6. Если реализации разойдутся, это будет баг или законная эволюция?

Если разойтись им законно, оставь их раздельными (`keep-duplicated`). Если общая
абстракция разрослась условными ветками, рассмотри `de-abstract`. Сходство строк
не является достаточным основанием для объединения.

Правило трёх — эвристика, не закон. Общее правило иногда нужно выделить при двух
потребителях, а три похожих блока могут быть разными доменными политиками.

## Приоритет

Оцени отдельно impact, likelihood, confidence и cost/risk. Не выдумывай частоту.
Редкий сценарий с потерей данных или обходом авторизации может иметь критичный приоритет.
