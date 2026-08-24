------------------------------------------------------------------------------
--  This script takes care of adding new lookup values and modifying existing ones
--  This script does not take care of deleting unwanted lookup values. If you want to remove a value then:
--      1. Remove it from this file so it does not get re-created
--      2. Decide how to deal with existing records and build an appropriate versioned script to do so

MERGE INTO els.course_content_type AS trg
USING
	(
	VALUES
		(1, 'INTRODUCTION', 'Introduction', 1),
		(2, 'LECTURE', 'Lecture', 1),
		(3, 'ANNOUNCEMENT', 'Announcement', 1)
	) as src(sort_order, code, display_name, is_active)
	ON trg.code = src.code
WHEN MATCHED AND
		HASHBYTES('MD5', (select src.display_name, src.sort_order, src.is_active FOR XML RAW)) <>
		HASHBYTES('MD5', (select trg.display_name, trg.sort_order, trg.is_active FOR XML RAW)) THEN
	UPDATE SET
		trg.display_name = src.display_name,
		trg.sort_order = src.sort_order,
		trg.is_active = src.is_active
WHEN NOT MATCHED THEN
	INSERT (code, display_name, sort_order, is_active)
	VALUES (src.code, src.display_name, src.sort_order, src.is_active)
;

------------------------------------------------------------------------------
MERGE INTO els.course_person_role AS trg
USING
	(
	VALUES
		(1, 'STUDENT', 'Student', 1),
		(2, 'INSTRUCTOR', 'Instructor', 1),
		(3, 'OWNER', 'Owner', 1)
	) as src(sort_order, code, display_name, is_active)
	ON trg.code = src.code
WHEN MATCHED AND
		HASHBYTES('MD5', (select src.display_name, src.sort_order, src.is_active FOR XML RAW)) <>
		HASHBYTES('MD5', (select trg.display_name, trg.sort_order, trg.is_active FOR XML RAW)) THEN
	UPDATE SET
		trg.display_name = src.display_name,
		trg.sort_order = src.sort_order,
		trg.is_active = src.is_active
WHEN NOT MATCHED THEN
	INSERT (code, display_name, sort_order, is_active)
	VALUES (src.code, src.display_name, src.sort_order, src.is_active)
;

------------------------------------------------------------------------------
MERGE INTO els.course_type AS trg
USING
	(
	VALUES
		(1, 'IN_PERSON', 'In Person', 1),
		(2, 'ONLINE', 'Online', 1),
		(3, 'HYBRID', 'Hybrid', 1),
		(4, 'NA', 'N/A', 1)
	) as src(sort_order, code, display_name, is_active)
	ON trg.code = src.code
WHEN MATCHED AND
		HASHBYTES('MD5', (select src.display_name, src.sort_order, src.is_active FOR XML RAW)) <>
		HASHBYTES('MD5', (select trg.display_name, trg.sort_order, trg.is_active FOR XML RAW)) THEN
	UPDATE SET
		trg.display_name = src.display_name,
		trg.sort_order = src.sort_order,
		trg.is_active = src.is_active
WHEN NOT MATCHED THEN
	INSERT (code, display_name, sort_order, is_active)
	VALUES (src.code, src.display_name, src.sort_order, src.is_active)
;

------------------------------------------------------------------------------
MERGE INTO els.curriculum_type AS trg
USING
	(
	VALUES
		(1, 'MANDATORY', 'Mandatory', 1),
		(2, 'OPTIONAL', 'Optional', 1)
	) as src(sort_order, code, display_name, is_active)
	ON trg.code = src.code
WHEN MATCHED AND
		HASHBYTES('MD5', (select src.display_name, src.sort_order, src.is_active FOR XML RAW)) <>
		HASHBYTES('MD5', (select trg.display_name, trg.sort_order, trg.is_active FOR XML RAW)) THEN
	UPDATE SET
		trg.display_name = src.display_name,
		trg.sort_order = src.sort_order,
		trg.is_active = src.is_active
WHEN NOT MATCHED THEN
	INSERT (code, display_name, sort_order, is_active)
	VALUES (src.code, src.display_name, src.sort_order, src.is_active)
;

------------------------------------------------------------------------------
MERGE INTO els.semester_type AS trg
USING
	(
	VALUES
		(1, 'WINTER', 'Winter', 1),
		(2, 'SUMMER', 'Summer', 1)
	) as src(sort_order, code, display_name, is_active)
	ON trg.code = src.code
WHEN MATCHED AND
		HASHBYTES('MD5', (select src.display_name, src.sort_order, src.is_active FOR XML RAW)) <>
		HASHBYTES('MD5', (select trg.display_name, trg.sort_order, trg.is_active FOR XML RAW)) THEN
	UPDATE SET
		trg.display_name = src.display_name,
		trg.sort_order = src.sort_order,
		trg.is_active = src.is_active
WHEN NOT MATCHED THEN
	INSERT (code, display_name, sort_order, is_active)
	VALUES (src.code, src.display_name, src.sort_order, src.is_active)
;
