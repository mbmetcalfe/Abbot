PRAGMA foreign_keys=off;

BEGIN TRANSACTION;

ALTER TABLE usage_commands_archive RENAME TO usage_commands_archive_orig;

CREATE TABLE IF NOT EXISTS `usage_commands_archive` (
	`user`	TEXT NOT NULL,
	`server`	TEXT NOT NULL,
	`channel`	TEXT NOT NULL,
	`command_name`	TEXT NOT NULL,
	`valid`	INTEGER DEFAULT 1,
	`count`	INTEGER DEFAULT 1,
	`year` INTEGER NOT NULL,
	`month` INTEGER NOT NULL,
	PRIMARY KEY(`user`,`command_name`,`server`,`channel`, `year`, `month`)
);


INSERT INTO usage_commands_archive (user, server, channel, command_name, valid, count, year, month)
    SELECT user, server, channel, command_name, valid, count, year, month FROM usage_commands_archive_orig;
DROP TABLE IF EXISTS `usage_commands_archive_orig`;
 
COMMIT;
 
PRAGMA foreign_keys=on;