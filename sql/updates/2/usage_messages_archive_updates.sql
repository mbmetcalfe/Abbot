PRAGMA foreign_keys=off;

BEGIN TRANSACTION;

ALTER TABLE usage_messages_archive RENAME TO usage_messages_archive_orig;

CREATE TABLE IF NOT EXISTS `usage_messages_archive` (
	`user`	TEXT NOT NULL,
	`server`	TEXT NOT NULL,
	`channel`	TEXT NOT NULL,
	`word_count`	INTEGER DEFAULT 1,
	`character_count`	INTEGER,
	`max_message_length`	INTEGER DEFAULT 1,
	`last_message_timestamp`	TEXT,
    `message_count` integer DEFAULT 1,
	`year` INTEGER NOT NULL,
	`month` INTEGER NOT NULL,
	PRIMARY KEY(`user`,`server`,`channel`, `year`, `month`)
);
 
-- message_count was not in usage_messages_archive before this update, so default it to 1 for existing records.
INSERT INTO usage_messages_archive (user, server, channel, word_count, character_count, max_message_length, last_message_timestamp, message_count, year, month)
    SELECT user, server, channel, word_count, character_count, max_message_length, last_message_timestamp, 1 as message_count, year, month FROM usage_messages_archive_orig;
DROP TABLE IF EXISTS `usage_messages_archive_orig`;
 
COMMIT;
 
PRAGMA foreign_keys=on;