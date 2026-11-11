# Сверка форматов GP: JSON и CSV

Время запуска (UTC): 20261111T092850Z

## Группа STATIONS

| Показатель | JSON | CSV |
|---|---|---|
| HTTP-статус | 200 | 200 |
| Content-Type | application/json; charset=UTF-8 | text/plain; charset=UTF-8 |
| Размер ответа, байт | 8010 | 3088 |
| Число записей | 19 | 19 |
| Число полей | 17 | 17 |

Отношение размера JSON к CSV: 2.59

### Постоянные поля OMM

| Поле | Есть в JSON | Есть в CSV |
|---|---|---|
| CENTER_NAME | False | False |
| REF_FRAME | False | False |
| TIME_SYSTEM | False | False |
| MEAN_ELEMENT_THEORY | False | False |

### Состав полей

- Только в JSON: нет
- Только в CSV: нет
- В JSON есть не в каждой записи: нет
- Порядок полей в CSV: ['OBJECT_NAME', 'OBJECT_ID', 'EPOCH', 'MEAN_MOTION', 'ECCENTRICITY', 'INCLINATION', 'RA_OF_ASC_NODE', 'ARG_OF_PERICENTER', 'MEAN_ANOMALY', 'EPHEMERIS_TYPE', 'CLASSIFICATION_TYPE', 'NORAD_CAT_ID', 'ELEMENT_SET_NO', 'REV_AT_EPOCH', 'BSTAR', 'MEAN_MOTION_DOT', 'MEAN_MOTION_DDOT']

### Типы значений в JSON

| Поле | Типы (число записей) |
|---|---|
| ARG_OF_PERICENTER | {'float': 19} |
| BSTAR | {'float': 19} |
| CLASSIFICATION_TYPE | {'str': 19} |
| ECCENTRICITY | {'float': 19} |
| ELEMENT_SET_NO | {'int': 19} |
| EPHEMERIS_TYPE | {'int': 19} |
| EPOCH | {'str': 19} |
| INCLINATION | {'float': 19} |
| MEAN_ANOMALY | {'float': 19} |
| MEAN_MOTION | {'float': 19} |
| MEAN_MOTION_DDOT | {'int': 17, 'float': 2} |
| MEAN_MOTION_DOT | {'float': 19} |
| NORAD_CAT_ID | {'int': 19} |
| OBJECT_ID | {'str': 19} |
| OBJECT_NAME | {'str': 19} |
| RA_OF_ASC_NODE | {'float': 19} |
| REV_AT_EPOCH | {'int': 19} |

### Пустые значения

- JSON, значение null: нет
- CSV, пустая строка: нет

### Идентификаторы

- Тип NORAD_CAT_ID в JSON: {'int': 19}
- Повторяющиеся идентификаторы: JSON 0, CSV 0
- Идентификаторы только в JSON: нет
- Идентификаторы только в CSV: нет

### Объекты с номером 100000 и выше

- JSON: 4 объектов, примеры [100057, 100712, 100882, 101031]
- CSV: 4 объектов, примеры [100057, 100712, 100882, 101031]
- Наибольший номер: JSON 101031, CSV 101031

### Сравнение значений

- Сопоставлено значений: 323
- Расхождений: 0

### Пример записи JSON

```json
{
  "OBJECT_NAME": "ISS (ZARYA)",
  "OBJECT_ID": "1998-067A",
  "EPOCH": "2026-11-10T21:13:46.284672",
  "MEAN_MOTION": 15.49305067,
  "ECCENTRICITY": 0.00073082,
  "INCLINATION": 51.6322,
  "RA_OF_ASC_NODE": 294.1523,
  "ARG_OF_PERICENTER": 11.5147,
  "MEAN_ANOMALY": 348.6007,
  "EPHEMERIS_TYPE": 0,
  "CLASSIFICATION_TYPE": "U",
  "NORAD_CAT_ID": 25544,
  "ELEMENT_SET_NO": 999,
  "REV_AT_EPOCH": 59449,
  "BSTAR": 0.00018692075,
  "MEAN_MOTION_DOT": 9.976e-05,
  "MEAN_MOTION_DDOT": 0
}
```

## Группа ANALYST

| Показатель | JSON | CSV |
|---|---|---|
| HTTP-статус | 200 | 200 |
| Content-Type | application/json; charset=UTF-8 | text/plain; charset=UTF-8 |
| Размер ответа, байт | 233464 | 78201 |
| Число записей | 576 | 576 |
| Число полей | 17 | 17 |

Отношение размера JSON к CSV: 2.99

### Постоянные поля OMM

| Поле | Есть в JSON | Есть в CSV |
|---|---|---|
| CENTER_NAME | False | False |
| REF_FRAME | False | False |
| TIME_SYSTEM | False | False |
| MEAN_ELEMENT_THEORY | False | False |

### Состав полей

- Только в JSON: нет
- Только в CSV: нет
- В JSON есть не в каждой записи: нет
- Порядок полей в CSV: ['OBJECT_NAME', 'OBJECT_ID', 'EPOCH', 'MEAN_MOTION', 'ECCENTRICITY', 'INCLINATION', 'RA_OF_ASC_NODE', 'ARG_OF_PERICENTER', 'MEAN_ANOMALY', 'EPHEMERIS_TYPE', 'CLASSIFICATION_TYPE', 'NORAD_CAT_ID', 'ELEMENT_SET_NO', 'REV_AT_EPOCH', 'BSTAR', 'MEAN_MOTION_DOT', 'MEAN_MOTION_DDOT']

### Типы значений в JSON

| Поле | Типы (число записей) |
|---|---|
| ARG_OF_PERICENTER | {'float': 576} |
| BSTAR | {'float': 573, 'int': 3} |
| CLASSIFICATION_TYPE | {'str': 576} |
| ECCENTRICITY | {'float': 576} |
| ELEMENT_SET_NO | {'int': 576} |
| EPHEMERIS_TYPE | {'int': 576} |
| EPOCH | {'str': 576} |
| INCLINATION | {'float': 576} |
| MEAN_ANOMALY | {'float': 576} |
| MEAN_MOTION | {'float': 576} |
| MEAN_MOTION_DDOT | {'int': 576} |
| MEAN_MOTION_DOT | {'float': 576} |
| NORAD_CAT_ID | {'int': 576} |
| OBJECT_ID | {'str': 576} |
| OBJECT_NAME | {'str': 576} |
| RA_OF_ASC_NODE | {'float': 576} |
| REV_AT_EPOCH | {'int': 576} |

### Пустые значения

- JSON, значение null: нет
- CSV, пустая строка: {'OBJECT_ID': 576}

### Идентификаторы

- Тип NORAD_CAT_ID в JSON: {'int': 576}
- Повторяющиеся идентификаторы: JSON 0, CSV 0
- Идентификаторы только в JSON: нет
- Идентификаторы только в CSV: нет

### Объекты с номером 100000 и выше

- JSON: 355 объектов, примеры [270000, 270001, 270003, 270004, 270005]
- CSV: 355 объектов, примеры [270000, 270001, 270003, 270004, 270005]
- Наибольший номер: JSON 270449, CSV 270449

### Сравнение значений

- Сопоставлено значений: 9792
- Расхождений: 0

### Пример записи JSON

```json
{
  "OBJECT_NAME": "UNKNOWN",
  "OBJECT_ID": "",
  "EPOCH": "2026-11-10T14:27:16.945344",
  "MEAN_MOTION": 14.08866567,
  "ECCENTRICITY": 0.0131657,
  "INCLINATION": 99.3531,
  "RA_OF_ASC_NODE": 341.876,
  "ARG_OF_PERICENTER": 307.8316,
  "MEAN_ANOMALY": 51.0996,
  "EPHEMERIS_TYPE": 0,
  "CLASSIFICATION_TYPE": "U",
  "NORAD_CAT_ID": 81011,
  "ELEMENT_SET_NO": 999,
  "REV_AT_EPOCH": 3036,
  "BSTAR": 0.0015062,
  "MEAN_MOTION_DOT": 2.77e-05,
  "MEAN_MOTION_DDOT": 0
}
```
