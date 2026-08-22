-- Placeholder repeatable migration for the "els" schema.
--
-- Flyway repeatable migrations (the "R__" prefix, as opposed to "V1__" versioned ones) re-run
-- automatically whenever their checksum changes, always after every pending versioned migration,
-- in the alphabetical order of their <description> part. They're meant for objects that are fully
-- replaced on every run rather than incrementally altered: views, stored procedures, functions,
-- permissions grants, and so on.
--
-- This file is a stand-in so the migrations/els folder and the deploy script have something real
-- to run end-to-end before any actual schema objects exist. Replace its content (or add further
-- R__ files alongside it) once there's a real view/procedure/permission to manage here.

PRINT 'els schema: placeholder repeatable migration executed (no-op)';
