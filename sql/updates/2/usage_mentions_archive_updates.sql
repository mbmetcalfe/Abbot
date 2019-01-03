PRAGMA foreign_keys=off;

BEGIN TRANSACTION;

ALTER TABLE usage_mentions_archive RENAME TO usage_mentions_archive_orig;

CREATE TABLE IF NOT EXISTS `usage_mentions_archive` (
	`user`	TEXT NOT NULL,
	`server`	TEXT NOT NULL,
	`channel`	TEXT NOT NULL,
	`user_mentions`	INTEGER DEFAULT 0,
	`user_mentioned`	INTEGER DEFAULT 0,
	`channel_mentions`	INTEGER DEFAULT 0,
	`role_mentions`	INTEGER DEFAULT 0,
	`year` INTEGER NOT NULL,
	`month` INTEGER NOT NULL,
	PRIMARY KEY(`user`,`server`,`channel`, `year`, `month`)
);

INSERT INTO usage_mentions_archive (user, server, channel, user_mentions, user_mentioned, channel_mentions, role_mentions, year, month)
    SELECT user, server, channel, user_mentions, user_mentioned, channel_mentions, role_mentions, year, month FROM usage_mentions_archive_orig;
DROP TABLE IF EXISTS `usage_mentions_archive_orig`;
 
COMMIT;
 
PRAGMA foreign_keys=on;