INSERT INTO orbital.sources (code, title, base_url)
VALUES
    ('celestrak', 'CelesTrak', 'https://celestrak.org'),
    ('space_track', 'Space-Track', 'https://www.space-track.org')
ON CONFLICT (code) DO NOTHING;

INSERT INTO orbital.datasets (source_id, code, title, file_format)
VALUES
    ((SELECT source_id FROM orbital.sources WHERE code = 'celestrak'),
     'gp_stations', 'Орбитальные элементы космических станций', 'csv'),
    ((SELECT source_id FROM orbital.sources WHERE code = 'celestrak'),
     'gp_active', 'Орбитальные элементы активных спутников', 'csv'),
    ((SELECT source_id FROM orbital.sources WHERE code = 'space_track'),
     'gp', 'Орбитальные элементы GP', 'json'),
    ((SELECT source_id FROM orbital.sources WHERE code = 'space_track'),
     'satcat', 'Каталог космических объектов SATCAT', 'json'),
    ((SELECT source_id FROM orbital.sources WHERE code = 'space_track'),
     'decay', 'Сведения о сходе объектов с орбиты', 'json')
ON CONFLICT (source_id, code) DO NOTHING;
