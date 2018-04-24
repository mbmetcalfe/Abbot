BEGIN TRANSACTION;
DROP TABLE IF EXISTS `usage_reactions`;
CREATE TABLE IF NOT EXISTS `usage_reactions` (
	`user`	TEXT NOT NULL,
	`server`	TEXT NOT NULL,
	`channel`	TEXT NOT NULL,
	`user_reaction_count`	INTEGER DEFAULT 0,
	`user_messages_reacted`	INTEGER DEFAULT 0,
	`user_reactions_received`	INTEGER DEFAULT 0,
	PRIMARY KEY(`user`,`server`,`channel`)
);
DROP TABLE IF EXISTS `usage_messages`;
CREATE TABLE IF NOT EXISTS `usage_messages` (
	`user`	TEXT NOT NULL,
	`server`	TEXT NOT NULL,
	`channel`	TEXT NOT NULL,
	`word_count`	INTEGER DEFAULT 1,
	`character_count`	INTEGER,
	`max_message_length`	INTEGER DEFAULT 1,
	`last_message_timestamp`	TEXT,
	PRIMARY KEY(`user`,`server`,`channel`)
);
DROP TABLE IF EXISTS `usage_mentions`;
CREATE TABLE IF NOT EXISTS `usage_mentions` (
	`user`	TEXT NOT NULL,
	`server`	TEXT NOT NULL,
	`channel`	TEXT NOT NULL,
	`user_mentions`	INTEGER DEFAULT 0,
	`user_mentioned`	INTEGER DEFAULT 0,
	`channel_mentions`	INTEGER DEFAULT 0,
	`role_mentions`	INTEGER DEFAULT 0,
	PRIMARY KEY(`user`,`server`,`channel`)
);
DROP TABLE IF EXISTS `usage_commands`;
CREATE TABLE IF NOT EXISTS `usage_commands` (
	`user`	TEXT NOT NULL,
	`server`	TEXT NOT NULL,
	`channel`	TEXT NOT NULL,
	`command_name`	TEXT NOT NULL,
	`valid`	INTEGER DEFAULT 1,
	`count`	INTEGER DEFAULT 1,
	PRIMARY KEY(`user`,`command_name`,`server`,`channel`)
);
COMMIT;