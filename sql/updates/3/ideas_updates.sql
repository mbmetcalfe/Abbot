PRAGMA foreign_keys=off;

BEGIN TRANSACTION;

ALTER TABLE ideas RENAME TO ideas_orig;

DROP TABLE IF EXISTS `ideas`;
CREATE TABLE `ideas` (
	`user`	TEXT NOT NULL,
	`server`	TEXT NOT NULL,
	`channel`	TEXT NOT NULL,
	`idea`	TEXT NOT NULL,
	`idea_date`	TEXT,
	PRIMARY KEY(`user`,`server`,`channel`,`idea`)
);
 
INSERT INTO ideas (user, server, channel, idea, idea_date)
    SELECT user, server, channel, idea, idea_date FROM ideas_orig;
DROP TABLE IF EXISTS `ideas_orig`;

COMMIT;
 
PRAGMA foreign_keys=on;