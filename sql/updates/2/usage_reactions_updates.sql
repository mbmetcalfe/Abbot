PRAGMA foreign_keys=off;

BEGIN TRANSACTION;

ALTER TABLE usage_reactions RENAME TO usage_reactions_orig;

DROP TABLE IF EXISTS `usage_reactions`;
CREATE TABLE `usage_reactions` (
    `user`  TEXT NOT NULL,
    `server`        TEXT NOT NULL,
    `channel`       TEXT NOT NULL,
    `messages_reacted_count`   INTEGER DEFAULT 0,
    `user_reacted_count` INTEGER DEFAULT 0,
    `message_reactions_received_count`       INTEGER DEFAULT 0,
    `reactions_received_count`       INTEGER DEFAULT 0,
    PRIMARY KEY(`user`,`server`,`channel`)
);

 
INSERT INTO usage_reactions (user, server, channel, messages_reacted_count, user_reacted_count, message_reactions_received_count, reactions_received_count)
    SELECT user, server, channel, messages_reacted_count, user_reacted_count, message_reactions_received_count, reactions_received_count FROM usage_reactions_orig;
DROP TABLE IF EXISTS `usage_reactions_orig`;

COMMIT;
 
PRAGMA foreign_keys=on;