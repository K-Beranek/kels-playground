------------------------------------------------------------------------------
--  Person
------------------------------------------------------------------------------
WITH campus AS (
    SELECT id
    FROM   els.campus
    WHERE  code = '{campus_code}'),
desired_record_count AS (
    SELECT (100 + '{complexity}' * 20) AS max_row_num),
first_name AS (
    SELECT first_name
    FROM   (VALUES ('Liam'), ('Noah'), ('Oliver'), ('Olivia'), ('Charlotte'), ('Theodore'), ('Emma'), ('Amelia'), ('Sophia'), ('Henry'), ('James'), ('Elijah'), ('Mia'), ('Mateo'), ('Isabella'), ('William'), ('Lucas'), ('Benjamin'), ('Levi'), ('Evelyn'), ('Elias'), ('Luca'), ('Jack'), ('Sebastian'), ('Hudson'), ('Samuel'), ('Sofia'), ('Eliana'), ('Leo'), ('Ezra'), ('Michael'), ('Daniel'), ('John'), ('Ethan'), ('Ava'), ('Eleanor'), ('Julian'), ('Santiago'), ('Violet'), ('Cooper'), ('Asher'), ('Joseph'), ('Alexander'), ('Owen'), ('Ailany'), ('Aurora'), ('Matthew'), ('Luke'), ('Thomas'), ('David'), ('Harper'), ('Elizabeth'), ('Lily'), ('Camila'), ('Jackson'), ('Gabriel'), ('Wyatt'), ('Nora'), ('Hazel'), ('Mason'), ('Bennett'), ('Penelope'), ('Dylan'), ('Chloe'), ('Ellie'), ('Lucy'), ('Roman'), ('Jacob'), ('Aria'), ('Luna'), ('Miles'), ('Carter'), ('Isla'), ('Anthony'), ('Isaac'), ('Charles'), ('Maverick'), ('Thiago'), ('Ella'), ('Grayson'), ('Lainey'), ('Zoe'), ('Scarlett'), ('Gianna'), ('Wesley'), ('Logan'), ('Josiah'), ('Weston'), ('Emily'), ('Waylon'), ('Valentina'), ('Layla'), ('Isaiah'), ('Avery'), ('Caleb'), ('Rowan'), ('Beau'), ('Grace'), ('Ivy'), ('Ezekiel')) AS src(first_name)),
first_name_suffix AS (
    SELECT first_name_suffix
    FROM   (VALUES (''), (''), (''), (''), (''), (' A.'), (' B.'), (' W.'), (' X.'), (' Q.'), (' Joe'), (' Jean'), (' D.')) AS src(first_name_suffix)),
last_name AS (
    SELECT last_name
    FROM   (VALUES ('Smith'), ('Johnson'), ('Williams'), ('Brown'), ('Jones'), ('Garcia'), ('Miller'), ('Rodriguez'), ('Davis'), ('Martinez'), ('Hernandez'), ('Lopez'), ('Gonzalez'), ('Wilson'), ('Anderson'), ('Thomas'), ('Taylor'), ('Moore'), ('Jackson'), ('Martin')) AS src(last_name)),
generated_data AS (
    SELECT
        c.id AS campus_id,
        fn.first_name || fns.first_name_suffix AS first_name,
        ln.last_name AS last_name,
        row_number() OVER (ORDER BY checksum(newid())) AS row_num
    FROM
        campus AS c
        CROSS JOIN first_name AS fn
        CROSS JOIN first_name_suffix AS fns
        CROSS JOIN last_name AS ln)
INSERT INTO els.person (
    campus_id,
    uuid,
    first_name,
    last_name
)
SELECT
    gd.campus_id,
    NEWID(),
    gd.first_name,
    gd.last_name
FROM
    generated_data AS gd
    CROSS JOIN desired_record_count AS drc
WHERE
    gd.row_num <= drc.max_row_num;
