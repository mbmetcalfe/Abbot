BEGIN TRANSACTION;

INSERT INTO usage_reactions_archive (user, server, channel, messages_reacted_count, user_reacted_count, message_reactions_received_count, reactions_received_count, year, month)
    SELECT user, server, channel, messages_reacted_count, user_reacted_count, message_reactions_received_count, reactions_received_count, strftime("%Y", date('now','-1 month')) as year, strftime("%m", date('now','-1 month')) as month from usage_reactions;

INSERT INTO usage_messages_archive (user, server, channel, word_count, character_count, max_message_length, last_message_timestamp, message_count, year, month)
    SELECT user, server, channel, word_count, character_count, max_message_length, last_message_timestamp, 1 as message_count, strftime("%Y", date('now','-1 month')) as year, strftime("%m", date('now','-1 month')) as month from usage_messages;

insert into usage_mentions_archive (user, server, channel, user_mentions, user_mentioned, channel_mentions, role_mentions, year, month)
    select user, server, channel, user_mentions, user_mentioned, channel_mentions, role_mentions, strftime("%Y", date('now','-1 month')) as year, strftime("%m", date('now','-1 month')) as month from usage_mentions;

insert into usage_commands_archive (user, server, channel, command_name, valid, count, year, month)
    select user, server, channel, command_name, valid, count, strftime("%Y", date('now','-1 month')) as year, strftime("%m", date('now','-1 month')) as month from usage_commands;

delete from usage_reactions;
delete from usage_messages;
delete from usage_mentions;
delete from usage_commands;

COMMIT;