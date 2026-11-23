-- Восстановление метаданных пяти снимков Bronze от 2026-11-17.
--
-- Причина: снимки попали в RustFS и MinIO до записи в orbital.snapshots,
-- а в текущей базе после переезда остался только прогон от 2026-11-22.
-- Источник: дамп postgres/orbital_data_2026-11-19T08-38-59Z.sql.gz.
-- Размеры и sha256 всех пяти объектов совпали с дампом в обоих хранилищах.
--
-- Что делает: дописывает два прогона, пять снимков и десять копий
-- (rustfs и minio). Существующие записи не меняет. Копии yandex
-- не пишет: их отметит ближайший запуск utils/backup_to_cloud.py.
-- Снимки того же дня, которых уже нет в хранилище, не переносит.
--
-- Применять только на устройстве, где объекты есть в бакете bronze.
-- Скрипт идемпотентен: повторный запуск ничего не меняет.
-- Каталог sql/repair не входит в `apply_sql.py sql`: это разовое
-- исправление данных, а не изменение схемы.
--
-- Запуск из корня проекта:
--   uv run --env-file .env python utils/apply_sql.py \
--       sql/repair/2026_11_17_restore_metadata.sql
--
-- Проверка после запуска:
--   uv run --env-file .env python utils/check_snapshots.py

DO $$
DECLARE
    first_run integer;
    second_run integer;
    inserted_snapshots integer;
    inserted_copies integer;
BEGIN
    IF EXISTS (
        SELECT 1
        FROM orbital.snapshots
        WHERE storage_path =
            'celestrak/gp_stations/2026-11-17T17-55-54Z.csv'
    ) THEN
        RAISE NOTICE 'Снимки 2026-11-17 уже есть, изменений нет';
        RETURN;
    END IF;

    INSERT INTO orbital.runs (started_at, finished_at, status)
    VALUES ('2026-11-17 14:54:50.438769+00',
            '2026-11-17 14:55:08.506069+00',
            'success')
    RETURNING run_id INTO first_run;

    INSERT INTO orbital.runs (started_at, finished_at, status)
    VALUES ('2026-11-17 17:55:53.962187+00',
            '2026-11-17 17:56:07.934558+00',
            'success')
    RETURNING run_id INTO second_run;

    INSERT INTO orbital.snapshots (
        run_id, dataset_id, fetched_at, file_name,
        file_size_bytes, checksum_sha256, storage_path
    )
    SELECT v.run_id, d.dataset_id, v.fetched_at, v.file_name,
           v.file_size_bytes, v.checksum_sha256, v.storage_path
    FROM (VALUES
        (first_run, 'space_track', 'satcat',
         '2026-11-17 14:54:50+00'::timestamptz,
         '2026-11-17T14-54-50Z.json', 33467318::bigint,
         '344c3626d50ac84b25e2bb2c4cace5d4be335071bcf338ebc2ba3d9057447098',
         'space_track/satcat/2026-11-17T14-54-50Z.json'),
        (first_run, 'space_track', 'decay',
         '2026-11-17 14:54:50+00',
         '2026-11-17T14-54-50Z.json', 43365302,
         '21026cc095353ebf1574b484a3cc2262d9757c92fe7fa2b6909fb73262b157bd',
         'space_track/decay/2026-11-17T14-54-50Z.json'),
        (second_run, 'celestrak', 'gp_stations',
         '2026-11-17 17:55:54+00',
         '2026-11-17T17-55-54Z.csv', 2794,
         '587cb4421403e442abfc5139295da9cc69cf836a257879784d156ea419d273dc',
         'celestrak/gp_stations/2026-11-17T17-55-54Z.csv'),
        (second_run, 'celestrak', 'gp_active',
         '2026-11-17 17:55:54+00',
         '2026-11-17T17-55-54Z.csv', 2516810,
         'a26a145fae7ae760b33011a28f5be34b1f2e277e86631cfaaf6a20ce09883a0e',
         'celestrak/gp_active/2026-11-17T17-55-54Z.csv'),
        (second_run, 'space_track', 'gp',
         '2026-11-17 17:55:54+00',
         '2026-11-17T17-55-54Z.json', 79372962,
         'a2db2482c01c77e3a3f5f380b28f343c230252e0213e22dbd1b39fd6b91fabaa',
         'space_track/gp/2026-11-17T17-55-54Z.json')
    ) AS v(run_id, source_code, dataset_code, fetched_at, file_name,
           file_size_bytes, checksum_sha256, storage_path)
    JOIN orbital.sources s ON s.code = v.source_code
    JOIN orbital.datasets d
        ON d.source_id = s.source_id
       AND d.code = v.dataset_code;

    GET DIAGNOSTICS inserted_snapshots = ROW_COUNT;

    INSERT INTO orbital.snapshot_copies (
        snapshot_id, storage, object_key, file_size_bytes, status, copied_at
    )
    SELECT sn.snapshot_id, v.storage, sn.storage_path,
           sn.file_size_bytes, 'ok', v.copied_at
    FROM (VALUES
        ('celestrak/gp_stations/2026-11-17T17-55-54Z.csv', 'rustfs',
         '2026-11-17 17:56:07.860893+00'::timestamptz),
        ('celestrak/gp_stations/2026-11-17T17-55-54Z.csv', 'minio',
         '2026-11-19 08:38:43.768788+00'),
        ('celestrak/gp_active/2026-11-17T17-55-54Z.csv', 'rustfs',
         '2026-11-17 17:56:07.869538+00'),
        ('celestrak/gp_active/2026-11-17T17-55-54Z.csv', 'minio',
         '2026-11-19 08:38:43.736330+00'),
        ('space_track/gp/2026-11-17T17-55-54Z.json', 'rustfs',
         '2026-11-17 17:56:07.932584+00'),
        ('space_track/gp/2026-11-17T17-55-54Z.json', 'minio',
         '2026-11-19 08:38:43.771492+00'),
        ('space_track/decay/2026-11-17T14-54-50Z.json', 'rustfs',
         '2026-11-17 14:55:08.503906+00'),
        ('space_track/decay/2026-11-17T14-54-50Z.json', 'minio',
         '2026-11-17 15:08:00.419703+00'),
        ('space_track/satcat/2026-11-17T14-54-50Z.json', 'rustfs',
         '2026-11-17 14:55:08.468914+00'),
        ('space_track/satcat/2026-11-17T14-54-50Z.json', 'minio',
         '2026-11-17 15:08:00.423790+00')
    ) AS v(storage_path, storage, copied_at)
    JOIN orbital.snapshots sn ON sn.storage_path = v.storage_path
    ON CONFLICT (snapshot_id, storage) DO NOTHING;

    GET DIAGNOSTICS inserted_copies = ROW_COUNT;

    RAISE NOTICE 'Восстановлено снимков: %, копий: %',
        inserted_snapshots, inserted_copies;
END
$$;
