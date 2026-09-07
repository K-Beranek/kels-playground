-- We are going to alter primary keys. Existing Foreign keys would prevent us from doing so
-- We need to drop these FK first, we re-create them later with correct columns
ALTER TABLE els.course DROP CONSTRAINT FK_course_campus_id;
ALTER TABLE els.course_content DROP CONSTRAINT FK_course_content_campus_id;
ALTER TABLE els.course_content DROP CONSTRAINT FK_course_content_course_id;
ALTER TABLE els.course_person DROP CONSTRAINT FK_course_person_campus_id;
ALTER TABLE els.course_person DROP CONSTRAINT FK_course_person_course_id;
ALTER TABLE els.course_person DROP CONSTRAINT FK_course_person_person_id;
ALTER TABLE els.course_test DROP CONSTRAINT FK_course_test_campus_id;
ALTER TABLE els.course_test DROP CONSTRAINT FK_course_test_course_id;
ALTER TABLE els.person DROP CONSTRAINT FK_person_campus_id;
ALTER TABLE els.semester DROP CONSTRAINT FK_semester_campus_id;
ALTER TABLE els.semester DROP CONSTRAINT FK_semester_semester_type;
ALTER TABLE els.study_program DROP CONSTRAINT FK_study_program_campus_id;
ALTER TABLE els.submission DROP CONSTRAINT FK_submission_campus_id;
ALTER TABLE els.submission DROP CONSTRAINT FK_submission_course_person_id;
ALTER TABLE els.submission DROP CONSTRAINT FK_submission_course_test_id;
ALTER TABLE els.term DROP CONSTRAINT FK_term_campus_id;
ALTER TABLE els.term DROP CONSTRAINT FK_term_study_program_id;
ALTER TABLE els.term DROP CONSTRAINT FK_term_semester_id;
ALTER TABLE els.term_course DROP CONSTRAINT FK_term_course_campus_id;
ALTER TABLE els.term_course DROP CONSTRAINT FK_term_course_term_id;
ALTER TABLE els.term_course DROP CONSTRAINT FK_term_course_course_id;
GO

-- Drop obsolete keys
ALTER TABLE els.term DROP CONSTRAINT UQ_term_semester_id;
GO

-- Alter the primary keys
ALTER TABLE els.course DROP CONSTRAINT PK_course;
ALTER TABLE els.course ADD CONSTRAINT PK_course PRIMARY KEY (campus_id, id);
ALTER TABLE els.course_content DROP CONSTRAINT PK_course_content;
ALTER TABLE els.course_content ADD CONSTRAINT PK_course_content PRIMARY KEY (campus_id, id);
ALTER TABLE els.course_person DROP CONSTRAINT PK_course_person;
ALTER TABLE els.course_person ADD CONSTRAINT PK_course_person PRIMARY KEY (campus_id, id);
ALTER TABLE els.course_test DROP CONSTRAINT PK_course_test;
ALTER TABLE els.course_test ADD CONSTRAINT PK_course_test PRIMARY KEY (campus_id, id);
ALTER TABLE els.person DROP CONSTRAINT PK_person;
ALTER TABLE els.person ADD CONSTRAINT PK_person PRIMARY KEY (campus_id, id);
ALTER TABLE els.study_program DROP CONSTRAINT PK_study_program;
ALTER TABLE els.study_program ADD CONSTRAINT PK_study_program PRIMARY KEY (campus_id, id);
ALTER TABLE els.submission DROP CONSTRAINT PK_submission;
ALTER TABLE els.submission ADD CONSTRAINT PK_submission PRIMARY KEY (campus_id, id);
ALTER TABLE els.term DROP CONSTRAINT PK_term;
ALTER TABLE els.term ADD CONSTRAINT PK_term PRIMARY KEY (campus_id, id);
ALTER TABLE els.term_course DROP CONSTRAINT PK_term_course;
ALTER TABLE els.term_course ADD CONSTRAINT PK_term_course PRIMARY KEY (campus_id, id);
GO

-- We rename some constraints
EXEC sp_rename N'els.FK_course_content_content_type', N'FK_course_content_course_content_type', N'OBJECT';
EXEC sp_rename N'els.FK_course_person_course_role', N'FK_course_person_course_person_role', N'OBJECT';
GO

-- Re-create foreign keys
ALTER TABLE els.course ADD CONSTRAINT FK_course_campus FOREIGN KEY (campus_id) REFERENCES els.campus (id);
ALTER TABLE els.course_content ADD CONSTRAINT FK_course_content_campus FOREIGN KEY (campus_id) REFERENCES els.campus (id);
ALTER TABLE els.course_content ADD CONSTRAINT FK_course_content_course FOREIGN KEY (campus_id, course_id) REFERENCES els.course (campus_id, id);
ALTER TABLE els.course_person ADD CONSTRAINT FK_course_person_campus FOREIGN KEY (campus_id) REFERENCES els.campus (id);
ALTER TABLE els.course_person ADD CONSTRAINT FK_course_person_course FOREIGN KEY (campus_id, course_id) REFERENCES els.course (campus_id, id);
ALTER TABLE els.course_person ADD CONSTRAINT FK_course_person_person FOREIGN KEY (campus_id, person_id) REFERENCES els.person (campus_id, id);
ALTER TABLE els.course_test ADD CONSTRAINT FK_course_test_campus FOREIGN KEY (campus_id) REFERENCES els.campus (id);
ALTER TABLE els.course_test ADD CONSTRAINT FK_course_test_course FOREIGN KEY (campus_id, course_id) REFERENCES els.course (campus_id, id);
ALTER TABLE els.person ADD CONSTRAINT FK_person_campus FOREIGN KEY (campus_id) REFERENCES els.campus (id);
ALTER TABLE els.study_program ADD CONSTRAINT FK_study_program_campus FOREIGN KEY (campus_id) REFERENCES els.campus (id);
ALTER TABLE els.submission ADD CONSTRAINT FK_submission_campus FOREIGN KEY (campus_id) REFERENCES els.campus (id);
ALTER TABLE els.submission ADD CONSTRAINT FK_submission_course_person FOREIGN KEY (campus_id, course_person_id) REFERENCES els.course_person (campus_id, id);
ALTER TABLE els.submission ADD CONSTRAINT FK_submission_course_test FOREIGN KEY (campus_id, course_test_id) REFERENCES els.course_test (campus_id, id);
ALTER TABLE els.term ADD CONSTRAINT FK_term_campus FOREIGN KEY (campus_id) REFERENCES els.campus (id);
ALTER TABLE els.term ADD CONSTRAINT FK_term_study_program FOREIGN KEY (campus_id, study_program_id) REFERENCES els.study_program (campus_id, id);
ALTER TABLE els.term_course ADD CONSTRAINT FK_term_course_campus FOREIGN KEY (campus_id) REFERENCES els.campus (id);
ALTER TABLE els.term_course ADD CONSTRAINT FK_term_course_course FOREIGN KEY (campus_id, course_id) REFERENCES els.course (campus_id, id);
ALTER TABLE els.term_course ADD CONSTRAINT FK_term_course_term FOREIGN KEY (campus_id, term_id) REFERENCES els.term (campus_id, id);
GO

-- Remove table els.semester, absorbed into els.term
ALTER TABLE els.term ADD semester_type NVARCHAR(30) NULL;
GO

UPDATE els.term
SET
    semester_type = (SELECT semester_type FROM els.semester semester WHERE term.semester_id = semester.id)
WHERE
    semester_type IS NULL;
GO

ALTER TABLE els.term ALTER COLUMN semester_type NVARCHAR(30) NOT NULL;
GO

ALTER TABLE els.term DROP COLUMN semester_id;
GO

ALTER TABLE els.term ADD CONSTRAINT FK_term_semester_type FOREIGN KEY (semester_type) REFERENCES els.semester_type (code);
GO

DROP TABLE els.semester;
GO

-- Update comments
EXEC utils.set_column_comment @schema_name = N'els', @table_name = N'course', @column_name = N'id', @comment = N'Surrogate identifier for the course, auto-generated by the database.';
EXEC utils.set_column_comment @schema_name = N'els', @table_name = N'course_content', @column_name = N'id', @comment = N'Surrogate identifier for the course content, auto-generated by the database.';
EXEC utils.set_column_comment @schema_name = N'els', @table_name = N'course_person', @column_name = N'id', @comment = N'Surrogate identifier for the course person, auto-generated by the database.';
EXEC utils.set_column_comment @schema_name = N'els', @table_name = N'submission', @column_name = N'id', @comment = N'Surrogate identifier for the submission, auto-generated by the database.';
EXEC utils.set_column_comment @schema_name = N'els', @table_name = N'term', @column_name = N'semester_type', @comment = N'Which semester type this is (e.g. Winter, Summer) -- references semester_type.code.';
EXEC utils.set_column_comment @schema_name = N'els', @table_name = N'term_course', @column_name = N'id', @comment = N'Surrogate identifier for the term course, auto-generated by the database.';
GO
