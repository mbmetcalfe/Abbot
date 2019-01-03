PRAGMA foreign_keys=off;

BEGIN TRANSACTION;

DROP TABLE IF EXISTS `usage_reactions_archive`;
CREATE TABLE `usage_reactions_archive` (
    `user`  TEXT NOT NULL,
    `server`        TEXT NOT NULL,
    `channel`       TEXT NOT NULL,
    `messages_reacted_count`   INTEGER DEFAULT 0,
    `user_reacted_count` INTEGER DEFAULT 0,
    `message_reactions_received_count`       INTEGER DEFAULT 0,
    `reactions_received_count`       INTEGER DEFAULT 0,
	`year` INTEGER NOT NULL,
	`month` INTEGER NOT NULL,
    PRIMARY KEY(`user`,`server`,`channel`, `year`, `month`)
);

 
-- INSERT INTO usage_reactions_archive (user, server, channel, messages_reacted_count, user_reacted_count, message_reactions_received_count, reactions_received_count, year, month)
--     SELECT user, server, channel, messages_reacted_count, user_reacted_count, message_reactions_received_count, reactions_received_count, year, month FROM usage_reactions_archive_orig;
 
COMMIT;
 
PRAGMA foreign_keys=on;