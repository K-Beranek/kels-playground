-- Campus - single record
INSERT INTO els.campus (
    code,
    uuid,
    name,
    description
)
VALUES (
	'{campus_code}',
	newid(),
	'{name}',
	N'Generated synthetic data, complexity {complexity}'
);
